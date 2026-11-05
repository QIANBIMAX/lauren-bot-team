"""File lock must exclude a second thread. Windows uses msvcrt, not a no-op."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from lauren_team_kit.atomic_io import file_lock


def test_file_lock_blocks_other_thread(tmp_path: Path) -> None:
    lock = tmp_path / "demo.lock"
    hold = threading.Event()
    started = threading.Event()
    second_entered = threading.Event()
    errors: list[BaseException] = []

    def first() -> None:
        try:
            with file_lock(lock):
                started.set()
                assert hold.wait(timeout=5)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            started.set()

    def second() -> None:
        try:
            with file_lock(lock, timeout_sec=2):
                second_entered.set()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    holder = threading.Thread(target=first)
    waiter = threading.Thread(target=second)
    holder.start()
    assert started.wait(timeout=5)
    waiter.start()
    time.sleep(0.3)
    assert not second_entered.is_set()
    hold.set()
    holder.join(timeout=5)
    waiter.join(timeout=5)
    assert errors == []
    assert second_entered.is_set()
    assert not holder.is_alive()
    assert not waiter.is_alive()
