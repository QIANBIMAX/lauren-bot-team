"""Atomic JSON writes and cross-process file locks (T1 / Lite-C L5 / W3).

Windows locks use stdlib ``msvcrt.locking`` (Win32 ``LockFile``). POSIX uses
``fcntl.flock``. Neither path is a no-op. No third-party lock library: the
standard library already covers both hosts, and a new dependency would have
to be declared in ``pyproject.toml``.

The lock is held across load → validate → mutate → save. Replacing a file
retries a bounded number of sharing/permission errors and never truncates the
original: bytes land in a temp file first, and a failed replace deletes only
the temp. Merge locks live on the Git common dir for the target branch and
are never stolen by deleting the lock file.
"""

from __future__ import annotations

import errno
import json
import os
import re
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

_REPLACE_ATTEMPTS = 8
_REPLACE_BASE_SLEEP = 0.02


def _lock_path_for(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".lock")


def _ensure_lock_file(lock_file: Path) -> None:
    """Create a non-empty lock file so a 1-byte range lock has somewhere to sit."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.is_file() and lock_file.stat().st_size > 0:
        return
    with open(lock_file, "ab") as init:
        init.seek(0, os.SEEK_END)
        if init.tell() == 0:
            init.write(b"\0")
            init.flush()


def _acquire_windows_lock(fh: Any, timeout_sec: float) -> None:
    """Byte-range lock via stdlib ``msvcrt`` (Win32 ``LockFile``).

    Same-process threads fail the second lock until the first unlocks, so
    this also serializes in-process read-modify-write. It is not
    ``PROCESS_TERMINATE`` and it is not a no-op.
    """
    import msvcrt
    import time

    fh.seek(0)
    deadline = time.monotonic() + timeout_sec
    while True:
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"获取文件锁超时: {getattr(fh, 'name', '')}")
            time.sleep(0.05)


def _release_windows_lock(fh: Any) -> None:
    import msvcrt

    try:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def _acquire_posix_lock(fh: Any, timeout_sec: float) -> None:
    try:
        import fcntl
    except ImportError as exc:
        raise OSError("当前平台没有 fcntl，无法加文件锁") from exc
    import time

    deadline = time.monotonic() + timeout_sec
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"获取文件锁超时: {getattr(fh, 'name', '')}")
            time.sleep(0.05)


def _release_posix_lock(fh: Any) -> None:
    try:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


@contextmanager
def file_lock(lock_file: Path, *, timeout_sec: float = 60.0) -> Iterator[None]:
    """Exclusive lock for read-modify-write.

    POSIX uses ``fcntl.flock``. Windows uses ``msvcrt.locking`` on the first
    byte. Windows does not degrade to a no-op.
    """
    _ensure_lock_file(lock_file)
    fh = open(lock_file, "r+b", buffering=0)
    try:
        if sys.platform == "win32":
            _acquire_windows_lock(fh, timeout_sec)
        else:
            _acquire_posix_lock(fh, timeout_sec)
        try:
            yield
        finally:
            if sys.platform == "win32":
                _release_windows_lock(fh)
            else:
                _release_posix_lock(fh)
    finally:
        fh.close()


class AtomicReplaceError(OSError):
    """``os.replace`` stayed busy. The original file was not truncated."""


class MergeLockError(RuntimeError):
    """Merge lock could not be taken, or a caller tried to steal it."""


class JsonEdit:
    """In-lock document. Mutate ``data``; set ``save=False`` to discard."""

    def __init__(self, data: Any) -> None:
        self.data = data
        self.save = True


def _replace_is_busy(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror in (5, 32, 33):
            return True
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EBUSY, errno.ETXTBSY):
            return True
    return False


def _replace_with_retry(tmp_name: str, dest: Path) -> None:
    """Replace ``dest`` with ``tmp_name``. Busy/permission errors are retried.

    Other errors propagate. On a final busy failure the temp file is removed
    by the caller and ``dest`` is left as it was (``os.replace`` has not
    truncated it).
    """
    last: BaseException | None = None
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp_name, dest)
            return
        except OSError as exc:
            if not _replace_is_busy(exc):
                raise
            last = exc
            time.sleep(_REPLACE_BASE_SLEEP * (attempt + 1))
    raise AtomicReplaceError(
        f"替换仍被占用或无权限，已停止重试且未改写原文件: {dest}"
    ) from last


def atomic_write_text_unlocked(
    path: Path | str, text: str, *, encoding: str = "utf-8"
) -> None:
    """Temp + fsync + replace. Caller must already hold the file lock if needed.

    The original is not opened for truncation. If replace keeps failing, only
    the temp file is removed.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    p = Path(path)
    lock = _lock_path_for(p)
    with file_lock(lock):
        atomic_write_text_unlocked(p, text, encoding=encoding)


def atomic_write_json_unlocked(path: Path | str, data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text_unlocked(path, text)


def atomic_write_json(path: Path | str, data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


@contextmanager
def locked_json_session(
    path: Path | str,
    *,
    timeout_sec: float = 60.0,
    default: Any | None = None,
    validator: Callable[[Any], None] | None = None,
) -> Iterator[JsonEdit]:
    """Hold one cross-process lock across load → validate → mutate → save.

    ``validator`` runs on the loaded document and again on the mutated
    document. A validator or caller exception skips the save, so the original
    bytes stay in place. This is one file, not a multi-file transaction.
    """
    p = Path(path)
    lock = _lock_path_for(p)
    with file_lock(lock, timeout_sec=timeout_sec):
        if p.is_file():
            with p.open(encoding="utf-8") as handle:
                current = json.load(handle)
        else:
            if default is None:
                raise FileNotFoundError(f"JSON 不存在: {p}")
            current = default
        if validator is not None:
            validator(current)
        edit = JsonEdit(current)
        try:
            yield edit
        except BaseException:
            raise
        else:
            if not edit.save:
                return
            if validator is not None:
                validator(edit.data)
            atomic_write_json_unlocked(p, edit.data)


def update_json_file(
    path: Path | str,
    mutator: Callable[[Any], Any],
    *,
    timeout_sec: float = 60.0,
    default: Any | None = None,
    validator: Callable[[Any], None] | None = None,
) -> Any:
    """Read-modify-write under one lock so concurrent updaters do not clobber.

    ``mutator`` receives the loaded object (or ``default`` if missing) and must
    return the object to persist. Optional ``validator`` runs before and after
    the mutation; failure leaves the file unchanged.
    """
    with locked_json_session(
        path,
        timeout_sec=timeout_sec,
        default=default,
        validator=validator,
    ) as edit:
        edit.data = mutator(edit.data)
        return edit.data


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def begin_recoverable_commit(journal: Path | str) -> str:
    """Start a recoverable multi-file commit id.

    Each file is still saved by its own atomic replace. The journal only
    records which files were noted and whether ``finish_recoverable_commit``
    ran. It is not a transaction: a crash can leave an open id with a subset
    of files already replaced. ``reconcile_recoverable_commits`` lists those.
    """
    commit_id = uuid.uuid4().hex

    def _mut(current: Any) -> Any:
        doc = current if isinstance(current, dict) else {"commits": []}
        commits = list(doc.get("commits") or [])
        commits.append(
            {
                "id": commit_id,
                "status": "open",
                "files": [],
                "started_at": _now_iso(),
                "finished_at": None,
            }
        )
        doc["commits"] = commits
        return doc

    update_json_file(journal, _mut, default={"commits": []})
    return commit_id


def note_recoverable_file(journal: Path | str, commit_id: str, file_path: str) -> None:
    def _mut(current: Any) -> Any:
        doc = current if isinstance(current, dict) else {"commits": []}
        found = False
        for row in doc.get("commits") or []:
            if isinstance(row, dict) and row.get("id") == commit_id:
                files = list(row.get("files") or [])
                files.append(str(file_path))
                row["files"] = files
                found = True
        if not found:
            raise KeyError(f"找不到可恢复提交: {commit_id}")
        return doc

    update_json_file(journal, _mut, default={"commits": []})


def finish_recoverable_commit(journal: Path | str, commit_id: str) -> None:
    def _mut(current: Any) -> Any:
        doc = current if isinstance(current, dict) else {"commits": []}
        found = False
        for row in doc.get("commits") or []:
            if isinstance(row, dict) and row.get("id") == commit_id:
                row["status"] = "complete"
                row["finished_at"] = _now_iso()
                found = True
        if not found:
            raise KeyError(f"找不到可恢复提交: {commit_id}")
        return doc

    update_json_file(journal, _mut, default={"commits": []})


def reconcile_recoverable_commits(journal: Path | str) -> list[dict[str, Any]]:
    """Return journal rows that are not ``complete``. Missing journal → []."""
    path = Path(journal)
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        doc = json.load(handle)
    rows = doc.get("commits") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return []
    return [
        row
        for row in rows
        if isinstance(row, dict) and row.get("status") != "complete"
    ]


def merge_lock_path(worktree: Path | str, integration_branch: str) -> Path:
    """Lock path shared by every worktree of this Git common dir + branch.

    The file lives inside the common dir (usually ``<repo>/.git``), not inside
    an individual worktree, so two worktrees cannot each hold a private lock
    for the same integration branch.
    """
    from lauren_team_kit.git_diag import git_common_dir

    common = git_common_dir(worktree)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", integration_branch).strip("_") or "branch"
    return common / f"lauren-merge-{safe}.lock"


def refuse_break_merge_lock(lock: Path | str | None = None) -> None:
    """There is no force-unlock. Deleting a live merge lock is refused."""
    extra = f": {lock}" if lock else ""
    raise MergeLockError("禁止通过删除锁文件抢占正在运行的合并" + extra)


@contextmanager
def integration_merge_lock(
    worktree: Path | str,
    integration_branch: str,
    *,
    timeout_sec: float = 120.0,
) -> Iterator[Path]:
    """Serialize merges for one Git common dir and one integration branch.

    Does not delete the lock file on entry, on timeout, or on exit. A timeout
    raises ``TimeoutError`` and leaves the holder untouched.
    """
    lock = merge_lock_path(worktree, integration_branch)
    with file_lock(lock, timeout_sec=timeout_sec):
        yield lock


def hold_lock_until(lock_path: str, start_path: str, release_path: str) -> None:
    """Test helper: hold ``lock_path`` until ``release_path`` appears."""
    lock = Path(lock_path)
    with file_lock(lock, timeout_sec=30):
        Path(start_path).write_text("held", encoding="utf-8")
        deadline = time.monotonic() + 20
        while not Path(release_path).exists():
            if time.monotonic() > deadline:
                return
            time.sleep(0.05)


def bump_json_counter(path: str, times: int) -> None:
    """Test helper: add ``times`` under the cross-process RMW lock."""
    target = Path(path)
    for _ in range(times):
        update_json_file(
            target,
            lambda cur: {"n": int((cur or {}).get("n", 0)) + 1},
            default={"n": 0},
        )
