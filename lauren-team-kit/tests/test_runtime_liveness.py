"""Process liveness isolation: POSIX signal 0 stays; Windows must not os.kill."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lauren_team_kit.protocol import create_task, load_task, task_path_for, transition_task
from lauren_team_kit import runtime
from lauren_team_kit.runtime import (
    WINDOWS_CANCEL_INCOMPLETE,
    _parse_proc_stat_starttime,
    _pid_alive_windows,
    acquire_lease,
    cancel_task,
    executor_still_same,
    interpret_open_process_result,
    pid_alive,
    read_process_create_time,
    request_cancel_on_lease,
)
from lauren_team_kit.worktree_ops import ensure_task_worktree


class _KernelDouble:
    def __init__(self, handle: int, error: int) -> None:
        self.handle = handle
        self.error = error
        self.opened: list[tuple[int, bool, int]] = []
        self.closed: list[int] = []

    def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
        self.opened.append((int(access), bool(inherit), int(pid)))
        return self.handle

    def last_error(self) -> int:
        return self.error

    def CloseHandle(self, handle: int) -> int:
        self.closed.append(int(handle))
        return 1


def _spawn_sleeper() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def test_liveness_helpers_used_on_windows_do_not_reference_os_kill() -> None:
    for fn in (
        pid_alive,
        _pid_alive_windows,
        runtime._windows_create_time,
        request_cancel_on_lease,
    ):
        assert "kill" not in fn.__code__.co_names, fn.__name__
    assert "_posix_sigterm" in request_cancel_on_lease.__code__.co_names
    assert "kill" in runtime._posix_sigterm.__code__.co_names


def test_sacrificial_child_stays_alive_under_liveness_probe() -> None:
    proc = _spawn_sleeper()
    try:
        assert pid_alive(proc.pid) is True
        assert proc.poll() is None
        token = read_process_create_time(proc.pid)
        assert proc.poll() is None
        if sys.platform.startswith("linux"):
            assert token is not None and token.startswith("proc:")
        elif sys.platform == "win32":
            assert token is not None and token.startswith("winft:")
        if token is not None:
            assert executor_still_same(proc.pid, token) is True
            assert proc.poll() is None
    finally:
        _stop(proc)


def test_missing_or_reused_pid_is_not_the_same_executor() -> None:
    proc = _spawn_sleeper()
    pid = proc.pid
    try:
        token = read_process_create_time(pid)
        assert pid_alive(pid) is True
    finally:
        _stop(proc)

    deadline = time.monotonic() + 3
    last: bool | None = True
    while time.monotonic() < deadline:
        if token:
            last = executor_still_same(pid, token)
        else:
            last = pid_alive(pid)
        if last is False:
            break
        time.sleep(0.05)
    assert last is False

    assert pid_alive(0) is None
    assert pid_alive(-1) is None
    # A clearly invalid pid is either gone or unknowable. It must not look alive
    # just because some other process exists.
    assert pid_alive(2_147_483_647) in (False, None)


def test_proc_stat_starttime_ignores_spaces_in_comm() -> None:
    fields = ["S", *list(map(str, range(1, 20)))]
    text = f"42 (comm (weird) name) {' '.join(fields)}"
    assert fields[19] == "19"
    assert _parse_proc_stat_starttime(text) == "proc:19"
    assert _parse_proc_stat_starttime("nope") is None


def test_pid_reuse_and_unknown_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "pid_alive", lambda pid: pid == 50)
    monkeypatch.setattr(runtime, "read_process_create_time", lambda pid: "proc:200")
    assert executor_still_same(50, "proc:100") is False
    assert executor_still_same(50, "proc:200") is True
    assert executor_still_same(49, "proc:200") is False
    assert executor_still_same(50, None) is True

    monkeypatch.setattr(runtime, "read_process_create_time", lambda pid: None)
    assert executor_still_same(50, "proc:200") is None


def test_posix_liveness_uses_signal_zero_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        seen.append((pid, sig))

    monkeypatch.setattr(runtime, "_is_windows", lambda: False)
    monkeypatch.setattr(runtime.os, "kill", fake_kill)
    assert pid_alive(12345) is True
    assert seen == [(12345, 0)]

    def missing(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(runtime.os, "kill", missing)
    assert pid_alive(12345) is False

    def denied(pid: int, sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(runtime.os, "kill", denied)
    assert pid_alive(12345) is True

    def other(pid: int, sig: int) -> None:
        raise OSError("boom")

    monkeypatch.setattr(runtime.os, "kill", other)
    assert pid_alive(12345) is None


def test_windows_open_process_is_query_only(monkeypatch: pytest.MonkeyPatch) -> None:
    kills: list[tuple[object, ...]] = []

    def boom(*args: object) -> None:
        kills.append(args)
        raise AssertionError("os.kill must not run on the Windows liveness path")

    monkeypatch.setattr(runtime.os, "kill", boom)
    monkeypatch.setattr(runtime, "_is_windows", lambda: True)
    kernel = _KernelDouble(handle=7, error=0)
    monkeypatch.setattr(runtime, "_load_kernel32", lambda: kernel)

    assert pid_alive(4321) is True
    assert kills == []
    assert kernel.opened == [(0x1000, False, 4321)]
    assert kernel.closed == [7]
    assert 0x1000 != 0x0001


def test_windows_open_process_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "_load_kernel32", lambda: _KernelDouble(0, 87))
    assert _pid_alive_windows(99) is False

    monkeypatch.setattr(runtime, "_load_kernel32", lambda: _KernelDouble(0, 5))
    assert _pid_alive_windows(99) is True

    monkeypatch.setattr(runtime, "_load_kernel32", lambda: _KernelDouble(0, 6))
    assert _pid_alive_windows(99) is None

    assert interpret_open_process_result(0, 87) is False
    assert interpret_open_process_result(0, 5) is True
    assert interpret_open_process_result(4, 87) is True
    assert interpret_open_process_result(0, 0) is None


def test_windows_cancel_does_not_kill_sacrificial_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "_is_windows", lambda: True)
    monkeypatch.setattr(runtime, "_pid_alive_windows", lambda pid: True)

    real_kill = os.kill

    def spy(pid: int, sig: int) -> None:
        if int(sig) in (0, int(signal.SIGTERM)):
            raise AssertionError(f"unsafe os.kill on Windows cancel: {(pid, sig)!r}")
        real_kill(pid, sig)

    monkeypatch.setattr(runtime.os, "kill", spy)
    proc = _spawn_sleeper()
    try:
        create_task(title="win-cancel", task_id="win-cancel", root=tmp_path)
        path = task_path_for(tmp_path, "win-cancel")
        task = load_task(path)
        task, _ = ensure_task_worktree(task, root=tmp_path)
        task = transition_task(
            task, to_status="执行中", actor="developer", role="developer", root=tmp_path
        )
        task = acquire_lease(task, holder="runner", pid=proc.pid)
        updated, report = cancel_task(
            task, actor="chief", reason="stop", signal_process=True, root=tmp_path
        )
        assert proc.poll() is None
        assert updated["status"] == "已取消"
        assert updated["cancel"]["os_kill_verified"] is False
        assert updated["cancel"]["cancel_os_status"] == "windows_incomplete"
        assert "Job Object" in updated["cancel"]["note"]
        assert WINDOWS_CANCEL_INCOMPLETE in updated["cancel"]["note"]
        lease = report["lease"]
        assert lease["signal_sent"] is False
        assert lease["cancel_os_status"] == "windows_incomplete"
        assert lease["pid_alive_before"] is True
        assert "TerminateProcess" in lease["cancel_note"]
    finally:
        _stop(proc)


def test_windows_cancel_without_signal_flag_still_refuses_os_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "_is_windows", lambda: True)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("os.kill on Windows cancel")

    monkeypatch.setattr(runtime.os, "kill", boom)
    task = {
        "executor_lease": {
            "holder": "h",
            "status": "active",
            "pid": 123,
            "cancel_requested": False,
        }
    }
    monkeypatch.setattr(runtime, "_pid_alive_windows", lambda pid: False)
    updated, report = request_cancel_on_lease(task, signal_process=True)
    assert updated["executor_lease"]["cancel_requested"] is True
    assert report["signal_sent"] is False
    assert report["cancel_os_status"] == "windows_incomplete"
    assert report["pid_alive_before"] is False
