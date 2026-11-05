"""Executor lease, cancel, and restart reconcile (Lite-C L5).

PID liveness is platform-gated:

* POSIX keeps ``os.kill(pid, 0)``. Signal 0 checks existence and is not delivered.
* Windows never calls ``os.kill``. CPython maps every signal other than
  ``CTRL_C_EVENT`` / ``CTRL_BREAK_EVENT`` to ``TerminateProcess``, and that
  includes signal 0 (https://docs.python.org/3.12/library/os.html#os.kill).
  Liveness uses ``OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`` via the
  stdlib ``ctypes`` binding, then ``CloseHandle``. The access mask is query
  only (``0x1000``), not ``PROCESS_TERMINATE``. No extra dependency.

Cancel is not a finished cross-platform process-tree kill:

* POSIX still sends best-effort ``SIGTERM`` and does not claim the process
  was observed dead.
* Windows only records protocol ``cancel_requested``. Job Object / controlled
  process-tree cancel is a later W2 remainder and must not be described as done.
  ``cancel_os_status`` is ``windows_incomplete``.

STATUS must not claim OS-kill end-to-end verification.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Any

from lauren_team_kit.protocol import _now_iso, transition_task
from lauren_team_kit.resume import block_task
from lauren_team_kit.state_machine import IllegalTransitionError
from lauren_team_kit.worktree_ops import (
    inspect_worktree,
)


class RuntimeError_(ValueError):
    """Lease / cancel / reconcile error (named to avoid shadowing builtin)."""


# Public alias without underscore clash in imports
RuntimeGateError = RuntimeError_


def _lease(task: dict[str, Any]) -> dict[str, Any]:
    raw = task.get("executor_lease")
    return dict(raw) if isinstance(raw, dict) else {}


# PROCESS_QUERY_LIMITED_INFORMATION. Not PROCESS_TERMINATE (0x0001).
_WIN_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WIN_ERROR_ACCESS_DENIED = 5
_WIN_ERROR_INVALID_PARAMETER = 87

WINDOWS_CANCEL_INCOMPLETE = (
    "Windows 取消未完成：未实现 Job Object / 受控进程树。"
    "禁止 os.kill（CTRL_C_EVENT/CTRL_BREAK_EVENT 以外会 TerminateProcess，含 signal 0）。"
    "此处只保留协议层 cancel_requested。"
)


def _is_windows() -> bool:
    return sys.platform == "win32"


def _valid_pid(pid: object) -> bool:
    return isinstance(pid, int) and not isinstance(pid, bool) and pid > 0


def pid_alive(pid: int) -> bool | None:
    """True if the pid exists, False if it is gone, None if we cannot tell.

    Windows dispatches to :func:`_pid_alive_windows` and does not call
    ``os.kill``. POSIX keeps signal 0.
    """
    if not _valid_pid(pid):
        return None
    if _is_windows():
        return _pid_alive_windows(pid)
    return _pid_alive_posix(pid)


def _pid_alive_posix(pid: int) -> bool | None:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but not owned by us — treat as alive/unknown-safe
        return True
    except OSError:
        return None


def interpret_open_process_result(handle: int, last_error: int) -> bool | None:
    """Map an ``OpenProcess`` result to liveness.

    A non-zero handle means the process exists. The caller closes that handle.
    ``ERROR_INVALID_PARAMETER`` (87) means the pid is not an existing process.
    ``ERROR_ACCESS_DENIED`` (5) means it exists but this token cannot query it,
    matching the POSIX ``PermissionError`` choice. Any other failure is unknown.
    """
    if handle:
        return True
    if last_error == _WIN_ERROR_INVALID_PARAMETER:
        return False
    if last_error == _WIN_ERROR_ACCESS_DENIED:
        return True
    return None


def _load_kernel32():  # type: ignore[no-untyped-def]
    """Load ``kernel32`` for query-only process checks. Windows only."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _read_last_error(kernel32: object) -> int:
    """Win32 last-error after ``OpenProcess``.

    Real ``kernel32`` is a ctypes ``WinDLL(..., use_last_error=True)``;
    ``ctypes.get_last_error`` exists on Windows. Test doubles implement
    ``last_error()`` so a Linux runner can simulate the codes. Lookup is on
    the double's class so it does not call ``GetProcAddress`` and wipe the
    real last-error.
    """
    method = getattr(type(kernel32), "last_error", None)
    if callable(method):
        return int(method(kernel32))
    import ctypes

    return int(ctypes.get_last_error())


def _pid_alive_windows(pid: int) -> bool | None:
    """No-side-effect liveness via ``OpenProcess`` + ``CloseHandle``.

    Does not call ``os.kill`` and does not request terminate rights.
    """
    try:
        kernel32 = _load_kernel32()
    except OSError:
        return None
    handle = kernel32.OpenProcess(
        _WIN_PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        int(pid),
    )
    err = _read_last_error(kernel32)
    if handle:
        kernel32.CloseHandle(handle)
    return interpret_open_process_result(int(handle or 0), err)


def _parse_proc_stat_starttime(text: str) -> str | None:
    """Return ``proc:<starttime>`` from a ``/proc/<pid>/stat`` body.

    ``comm`` may contain spaces and parentheses, so the clock-tick starttime
    is field 22 counted after the last ``)``.
    """
    rparen = text.rfind(")")
    if rparen < 0:
        return None
    fields = text[rparen + 1 :].split()
    if len(fields) <= 19:
        return None
    token = fields[19]
    if not token.isdigit():
        return None
    return f"proc:{token}"


def _posix_create_time(pid: int) -> str | None:
    path = Path(f"/proc/{int(pid)}/stat")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_proc_stat_starttime(text)


def _windows_create_time(pid: int) -> str | None:
    """Creation FILETIME via ``GetProcessTimes`` after a query-only open.

    Returns None when the process is gone or the time cannot be read.
    The token is ``winft:<100ns ticks>`` and is only a reuse discriminator.
    """
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    try:
        kernel32 = _load_kernel32()
    except OSError:
        return None
    kernel32.GetProcessTimes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(
        _WIN_PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        int(pid),
    )
    if not handle:
        return None
    created = FILETIME()
    exited = FILETIME()
    kernel_t = FILETIME()
    user_t = FILETIME()
    try:
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel_t),
            ctypes.byref(user_t),
        )
        if not ok:
            return None
        ticks = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        return f"winft:{ticks}"
    finally:
        kernel32.CloseHandle(handle)


def read_process_create_time(pid: int) -> str | None:
    """Opaque creation token, or None if missing / unreadable.

    POSIX uses ``/proc/<pid>/stat`` starttime when procfs exists (Linux).
    Windows uses ``GetProcessTimes``. macOS has no procfs here, so the token
    stays None until a later slice records another identity source.
    """
    if not _valid_pid(pid):
        return None
    if _is_windows():
        return _windows_create_time(pid)
    return _posix_create_time(pid)


def executor_still_same(pid: int, expected_create_time: str | None) -> bool | None:
    """Whether ``pid`` is still the same executor, accounting for PID reuse.

    * False: process is gone, or both creation tokens are known and differ.
    * True: process exists and no token was supplied (existence only), or the
      token matches. A missing expected token does **not** prove identity.
    * None: existence is unknown, or a token was required but could not be read.
      Callers must not treat None as permission to kill.
    """
    alive = pid_alive(pid)
    if alive is False:
        return False
    if alive is None:
        return None
    if not expected_create_time:
        return True
    current = read_process_create_time(pid)
    if current is None:
        return None
    return current == expected_create_time


def acquire_lease(
    task: dict[str, Any],
    *,
    holder: str,
    pid: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Mark task as having an active executor lease (protocol-level)."""
    task = dict(task)
    now = _now_iso()
    lease = {
        "holder": holder,
        "status": "active",
        "acquired_at": now,
        "heartbeat_at": now,
        "cancel_requested": False,
    }
    if pid is not None:
        lease["pid"] = int(pid)
    if note:
        lease["note"] = note
    task["executor_lease"] = lease
    task["updated_at"] = now
    return task


def heartbeat_lease(task: dict[str, Any]) -> dict[str, Any]:
    task = dict(task)
    lease = _lease(task)
    if not lease:
        raise RuntimeGateError("无 executor_lease 可心跳")
    lease = dict(lease)
    lease["heartbeat_at"] = _now_iso()
    task["executor_lease"] = lease
    task["updated_at"] = lease["heartbeat_at"]
    return task


def release_lease(
    task: dict[str, Any],
    *,
    reason: str = "released",
) -> dict[str, Any]:
    task = dict(task)
    lease = _lease(task)
    if not lease:
        return task
    now = _now_iso()
    lease = dict(lease)
    lease["status"] = "released"
    lease["released_at"] = now
    lease["release_reason"] = reason
    task["executor_lease"] = lease
    task["updated_at"] = now
    return task


def _posix_sigterm(pid: int) -> dict[str, Any]:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return {
            "signal_sent": False,
            "signal": "SIGTERM",
            "signal_error": str(exc),
            "cancel_os_status": "posix_error",
        }
    return {
        "signal_sent": True,
        "signal": "SIGTERM",
        "cancel_os_status": "posix_signaled",
    }


def request_cancel_on_lease(
    task: dict[str, Any],
    *,
    signal_process: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Flip cancel_requested.

    POSIX: best-effort SIGTERM when the pid looks alive. Does NOT claim the
    process was observed dead.

    Windows: never calls ``os.kill``. Marks ``windows_incomplete`` because
    controlled process-tree cancel is not implemented.
    """
    task = dict(task)
    lease = _lease(task)
    windows = _is_windows()
    report: dict[str, Any] = {
        "cancel_requested": True,
        "signal_sent": False,
        "pid": None,
        "pid_alive_before": None,
        "boundary": (
            "protocol_lease_windows_cancel_incomplete"
            if windows
            else "protocol_lease_plus_best_effort_signal"
        ),
        "cancel_os_status": "windows_incomplete" if windows else "posix_not_sent",
    }
    if windows:
        report["cancel_note"] = WINDOWS_CANCEL_INCOMPLETE
    now = _now_iso()
    if not lease:
        lease = {
            "holder": "unknown",
            "status": "cancelled",
            "acquired_at": now,
            "cancel_requested": True,
            "note": "cancel without prior lease",
        }
    else:
        lease = dict(lease)
        lease["cancel_requested"] = True
        lease["status"] = "cancel_requested"
        lease["cancel_requested_at"] = now
        pid = lease.get("pid")
        if _valid_pid(pid):
            report["pid"] = pid
            alive = pid_alive(pid)
            report["pid_alive_before"] = alive
            # Windows must not fall through to SIGTERM / os.kill.
            if (not windows) and signal_process and alive is True:
                report.update(_posix_sigterm(int(pid)))
    task["executor_lease"] = lease
    task["updated_at"] = now
    return task, report


def cancel_task(
    task: dict[str, Any],
    *,
    actor: str,
    reason: str | None = None,
    signal_process: bool = True,
    root: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Transition to 已取消, request stop on lease, release lease, keep evidence.

    Allowed from non-terminal statuses that the state machine permits → 已取消.
    """
    status = str(task.get("status") or "")
    report: dict[str, Any] = {
        "action": "cancel",
        "from_status": status,
        "reason": reason or "user_cancel",
    }
    task, lease_rep = request_cancel_on_lease(task, signal_process=signal_process)
    report["lease"] = lease_rep
    note = f"cancel: {reason or 'user_cancel'}"
    try:
        updated = transition_task(
            task, to_status="已取消", actor=actor, note=note, skip_route_guard=True
        )
    except IllegalTransitionError as e:
        raise RuntimeGateError(str(e)) from e
    updated = release_lease(updated, reason="cancelled")
    # Append cancel evidence blob on task for audit
    note = "协议层取消+租约；未宣称 OS 级杀进程验收"
    if lease_rep.get("cancel_os_status") == "windows_incomplete":
        note = note + "；" + WINDOWS_CANCEL_INCOMPLETE
    cancel_ev = {
        "at": _now_iso(),
        "actor": actor,
        "reason": reason or "user_cancel",
        "lease": lease_rep,
        "os_kill_verified": False,
        "cancel_os_status": lease_rep.get("cancel_os_status"),
        "note": note,
    }
    updated = dict(updated)
    updated["cancel"] = cancel_ev
    report["to_status"] = "已取消"
    report["os_kill_verified"] = False
    if root is not None:
        # Optional: record worktree inspect at cancel time
        try:
            report["worktree_at_cancel"] = inspect_worktree(root, updated)
        except Exception as e:  # pragma: no cover - defensive
            report["worktree_at_cancel_error"] = str(e)
    return updated, report


def reconcile_for_resume(
    task: dict[str, Any],
    *,
    root: Path | str,
) -> dict[str, Any]:
    """Check lease + Git reality before leaving 受阻.

    Returns report with ``safe_to_resume`` bool and optional ``block_reason``.
    Unknown executor liveness → not safe (caller should stay/enter 受阻).
    """
    report: dict[str, Any] = {
        "safe_to_resume": True,
        "block_reason": None,
        "code": None,
        "lease": None,
        "worktree": None,
        "already_have_artifact": False,
        "recommit_needed": False,
    }
    lease = _lease(task)
    report["lease"] = lease or None

    if lease.get("cancel_requested"):
        report["safe_to_resume"] = False
        report["code"] = "CANCEL_REQUESTED"
        report["block_reason"] = "已请求取消；不得 resume 继续执行"
        return report

    if lease.get("status") == "active":
        pid = lease.get("pid")
        if isinstance(pid, int):
            alive = pid_alive(pid)
            report["pid_alive"] = alive
            if alive is True:
                report["safe_to_resume"] = False
                report["code"] = "EXECUTOR_STILL_RUNNING"
                report["block_reason"] = (
                    f"executor_lease.pid={pid} 仍存活；结果未知，禁止盲目重复执行"
                )
                return report
            if alive is None:
                report["safe_to_resume"] = False
                report["code"] = "EXECUTOR_STATE_UNKNOWN"
                report["block_reason"] = (
                    f"无法确认 pid={pid} 是否存活；结果未知 → 受阻"
                )
                return report
            # dead → stale lease ok to resume after marking
            report["lease_stale"] = True
        else:
            # Active lease without pid: protocol-only; allow resume but flag
            report["lease_without_pid"] = True

    # Git / worktree reconcile
    try:
        insp = inspect_worktree(root, task)
        report["worktree"] = insp
    except Exception as e:
        report["safe_to_resume"] = False
        report["code"] = "WORKTREE_INSPECT_FAILED"
        report["block_reason"] = str(e)
        return report

    # If path claimed created but missing → block
    wt = task.get("worktree") if isinstance(task.get("worktree"), dict) else {}
    if wt.get("created") and not (insp.get("exists") and insp.get("is_git")):
        report["safe_to_resume"] = False
        report["code"] = "WORKTREE_MISSING"
        report["block_reason"] = "协议标记已创建 worktree，但目录/仓库缺失"
        return report

    # Artifact vs HEAD
    art = None
    artifact = task.get("artifact")
    if isinstance(artifact, dict):
        c = artifact.get("commit")
        if isinstance(c, str) and c.strip():
            art = c.strip()
    head = insp.get("head")
    resume = task.get("resume") if isinstance(task.get("resume"), dict) else {}
    interrupt_sha = resume.get("artifact_commit_at_interrupt")
    if isinstance(interrupt_sha, str):
        interrupt_sha = interrupt_sha.strip() or None
    else:
        interrupt_sha = None

    if art and interrupt_sha and art == interrupt_sha:
        report["already_have_artifact"] = True
        report["recommit_needed"] = False
    elif interrupt_sha and art != interrupt_sha:
        report["recommit_needed"] = True

    # Dirty tree with active claim of completed artifact at HEAD mismatch → unknown
    if insp.get("exists") and insp.get("is_git") and insp.get("dirty"):
        if art and head and art != head:
            report["safe_to_resume"] = False
            report["code"] = "DIRTY_HEAD_MISMATCH"
            report["block_reason"] = (
                "工作区脏且 HEAD ≠ artifact.commit；结果未知，须人工对账后再 resume"
            )
            return report
        report["dirty_ok_for_executing"] = True

    if insp.get("errors") and wt.get("created"):
        # Branch mismatch etc.
        report["safe_to_resume"] = False
        report["code"] = "WORKTREE_INVALID"
        report["block_reason"] = "; ".join(insp["errors"])
        return report

    return report


def resume_with_reconcile(
    task: dict[str, Any],
    *,
    root: Path | str,
    actor: str,
    to_status: str | None = None,
    clear_blocker_code: str | None = None,
    auto_block: bool = True,
    skip_reconcile: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconcile then resume_task. On unsafe → stay/enter 受阻, no silent execute."""
    from lauren_team_kit.resume import resume_task

    report: dict[str, Any] = {"reconcile": None, "resume": None}
    if not skip_reconcile:
        rec = reconcile_for_resume(task, root=root)
        report["reconcile"] = rec
        if not rec.get("safe_to_resume"):
            status = str(task.get("status") or "")
            if status == "受阻":
                # Stay blocked; append blocker if new code
                task = dict(task)
                blockers = list(task.get("blockers") or [])
                code = rec.get("code") or "RECONCILE_UNKNOWN"
                if not any(
                    isinstance(b, dict) and b.get("code") == code for b in blockers
                ):
                    blockers.append(
                        {
                            "code": code,
                            "message": rec.get("block_reason") or "对账失败",
                            "recovery_hint": "人工确认进程/工作区后清除 blocker 再 resume",
                        }
                    )
                    task["blockers"] = blockers
                report["action"] = "reconcile_blocked"
                report["to_status"] = "受阻"
                return task, report
            # Not yet 受阻 — force block
            blocked = block_task(
                task,
                code=str(rec.get("code") or "RECONCILE_UNKNOWN"),
                message=str(rec.get("block_reason") or "对账失败"),
                recovery_hint="人工确认进程/工作区后清除 blocker 再 resume",
                resume_point=to_status
                or (
                    (task.get("resume") or {}).get("resume_point")
                    if isinstance(task.get("resume"), dict)
                    else None
                )
                or "执行中",
                actor=actor,
                reason=str(rec.get("block_reason") or "对账失败"),
            )
            report["action"] = "reconcile_blocked"
            report["to_status"] = "受阻"
            return blocked, report

    updated, resume_rep = resume_task(
        task,
        actor=actor,
        to_status=to_status,
        clear_blocker_code=clear_blocker_code,
        auto_block=auto_block,
    )
    report["resume"] = resume_rep
    report["action"] = resume_rep.get("action")
    report["to_status"] = resume_rep.get("to_status") or updated.get("status")
    return updated, report
