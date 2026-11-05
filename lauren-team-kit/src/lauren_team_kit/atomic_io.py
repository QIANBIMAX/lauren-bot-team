"""Atomic JSON writes and cross-process file locks (T1 / Lite-C L5)."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


def _lock_path_for(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".lock")


@contextmanager
def file_lock(lock_file: Path, *, timeout_sec: float = 60.0) -> Iterator[None]:
    """Exclusive advisory lock via fcntl (POSIX). Best-effort on other platforms."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_file, "a+", encoding="utf-8")
    try:
        try:
            import fcntl
            import time

            deadline = time.monotonic() + timeout_sec
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"获取文件锁超时: {lock_file}")
                    time.sleep(0.05)
        except ImportError:
            # Windows / no fcntl: no-op coordination (single-process still atomic via replace)
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        fh.close()


def atomic_write_text_unlocked(
    path: Path | str, text: str, *, encoding: str = "utf-8"
) -> None:
    """Temp + fsync + replace. Caller must already hold the file lock if needed."""
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
        os.replace(tmp_name, p)
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


def update_json_file(
    path: Path | str,
    mutator: Callable[[Any], Any],
    *,
    timeout_sec: float = 60.0,
    default: Any | None = None,
) -> Any:
    """Read-modify-write under one lock so concurrent updaters do not clobber.

    ``mutator`` receives the loaded object (or ``default`` if missing) and must
    return the object to persist.
    """
    p = Path(path)
    lock = _lock_path_for(p)
    with file_lock(lock, timeout_sec=timeout_sec):
        if p.is_file():
            with p.open(encoding="utf-8") as f:
                current = json.load(f)
        else:
            if default is None:
                raise FileNotFoundError(f"JSON 不存在: {p}")
            current = default
        updated = mutator(current)
        atomic_write_json_unlocked(p, updated)
        return updated


@contextmanager
def integration_merge_lock(
    worktree: Path | str,
    integration_branch: str,
    *,
    timeout_sec: float = 120.0,
) -> Iterator[Path]:
    """Serialize merges per (repo worktree + integration branch)."""
    repo = Path(worktree).resolve()
    safe = integration_branch.replace("/", "_").replace("\\", "_")
    lock = repo / f".lauren-merge-{safe}.lock"
    with file_lock(lock, timeout_sec=timeout_sec):
        yield lock
