"""Executor lease, cancel, and restart reconcile (Lite-C L5).

Honest boundary: PID liveness is best-effort via ``os.kill(pid, 0)``.
True OS-level process kill / GUI restart is NOT claimed verified here;
cancel sets ``cancel_requested`` and releases the lease so callers stop,
and records evidence. STATUS must not claim OS-kill E2E.
"""

from __future__ import annotations

import os
import signal
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


def pid_alive(pid: int) -> bool | None:
    """True if process exists, False if gone, None if cannot check."""
    if pid <= 0:
        return None
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


def request_cancel_on_lease(
    task: dict[str, Any],
    *,
    signal_process: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Flip cancel_requested; best-effort SIGTERM if pid known.

    Does NOT claim the OS process was observed dead.
    """
    task = dict(task)
    lease = _lease(task)
    report: dict[str, Any] = {
        "cancel_requested": True,
        "signal_sent": False,
        "pid": None,
        "pid_alive_before": None,
        "boundary": "protocol_lease_plus_best_effort_signal",
    }
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
        if isinstance(pid, int):
            report["pid"] = pid
            alive = pid_alive(pid)
            report["pid_alive_before"] = alive
            if signal_process and alive is True:
                try:
                    os.kill(pid, signal.SIGTERM)
                    report["signal_sent"] = True
                    report["signal"] = "SIGTERM"
                except OSError as e:
                    report["signal_error"] = str(e)
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
    cancel_ev = {
        "at": _now_iso(),
        "actor": actor,
        "reason": reason or "user_cancel",
        "lease": lease_rep,
        "os_kill_verified": False,
        "note": "协议层取消+租约；未宣称 OS 级杀进程验收",
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
