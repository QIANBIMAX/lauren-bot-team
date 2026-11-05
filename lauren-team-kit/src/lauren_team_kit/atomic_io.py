"""Atomic JSON writes and cross-process file locks (T1)."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


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


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path_for(p)
    with file_lock(lock):
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


def atomic_write_json(path: Path | str, data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


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
