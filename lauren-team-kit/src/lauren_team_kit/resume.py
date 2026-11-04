"""Block (受阻) and resume helpers — Lite L3 interrupt recovery."""

from __future__ import annotations

from typing import Any

from lauren_team_kit.protocol import _now_iso, transition_task
from lauren_team_kit.state_machine import IllegalTransitionError

# Statuses that may enter 受阻 via block_task.
BLOCKABLE_STATUSES = frozenset({"待执行", "执行中", "待验证", "需修改"})

# Legal resume_point values (and 受阻 → targets except 已取消).
RESUME_POINTS = frozenset({"待执行", "执行中", "待验证"})


class BlockResumeError(ValueError):
    """Illegal block/resume request (missing point, wrong status, etc.)."""


def _artifact_commit(task: dict[str, Any]) -> str | None:
    art = task.get("artifact")
    if isinstance(art, dict):
        c = art.get("commit")
        if isinstance(c, str) and c.strip():
            return c.strip()
    return None


def block_task(
    task: dict[str, Any],
    *,
    code: str,
    message: str,
    recovery_hint: str,
    resume_point: str,
    actor: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Move task to 受阻, append blockers[], set resume fields.

    Allowed only from 待执行 / 执行中 / 待验证.
    """
    status = str(task.get("status") or "")
    if status not in BLOCKABLE_STATUSES:
        raise BlockResumeError(
            f"block 仅允许从 {', '.join(sorted(BLOCKABLE_STATUSES))}；当前={status!r}"
        )
    if resume_point not in RESUME_POINTS:
        raise BlockResumeError(
            f"非法 resume_point: {resume_point!r}；允许: "
            f"{', '.join(sorted(RESUME_POINTS))}"
        )

    now = _now_iso()
    art_at = _artifact_commit(task)
    blocker = {
        "code": code,
        "message": message,
        "recovery_hint": recovery_hint,
    }
    resume: dict[str, Any] = {
        "resume_point": resume_point,
        "interrupted_at": now,
        "reason": reason or message,
    }
    if art_at is not None:
        resume["artifact_commit_at_interrupt"] = art_at

    task = dict(task)
    blockers = list(task.get("blockers") or [])
    blockers.append(blocker)
    task["blockers"] = blockers
    task["resume"] = resume

    note = (
        f"block code={code}; resume_point={resume_point}; "
        f"hint={recovery_hint}"
    )
    return transition_task(task, to_status="受阻", actor=actor, note=note)


def resume_task(
    task: dict[str, Any],
    *,
    actor: str,
    to_status: str | None = None,
    clear_blocker_code: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Leave 受阻 toward stored (or overridden) resume_point.

    Idempotent when status is already not 受阻.
    Reports already_have_artifact when artifact.commit matches interrupt SHA
    (do not instruct a re-commit in that case).
    """
    status = str(task.get("status") or "")
    resume = task.get("resume") if isinstance(task.get("resume"), dict) else {}
    interrupt_sha = resume.get("artifact_commit_at_interrupt")
    if isinstance(interrupt_sha, str):
        interrupt_sha = interrupt_sha.strip() or None
    else:
        interrupt_sha = None
    current_sha = _artifact_commit(task)

    already_have = bool(
        current_sha is not None
        and interrupt_sha is not None
        and current_sha == interrupt_sha
    )
    # Only ask for re-commit when we had a SHA at interrupt and it no longer matches.
    # No interrupt SHA ⇒ nothing to "re"-commit (first commit is normal work).
    recommit_needed = bool(
        interrupt_sha is not None and not already_have
    )

    report: dict[str, Any] = {
        "action": "resume",
        "from_status": status,
        "already_have_artifact": already_have,
        "artifact_commit": current_sha,
        "artifact_commit_at_interrupt": interrupt_sha,
        "recommit_needed": recommit_needed,
    }
    if already_have:
        report["note"] = "artifact.commit 已等于中断时 SHA，勿重复提交"

    if status != "受阻":
        report["action"] = "noop_not_blocked"
        report["to_status"] = status
        report["idempotent"] = True
        return dict(task), report

    target = to_status or resume.get("resume_point")
    if not target:
        raise BlockResumeError(
            "resume 需要 --to 或 task.resume.resume_point；当前均缺失"
        )
    if target not in RESUME_POINTS:
        raise BlockResumeError(
            f"非法恢复目标: {target!r}；允许: {', '.join(sorted(RESUME_POINTS))}"
        )

    task = dict(task)
    if clear_blocker_code:
        blockers = [
            b
            for b in (task.get("blockers") or [])
            if not (isinstance(b, dict) and b.get("code") == clear_blocker_code)
        ]
        task["blockers"] = blockers

    note = f"resume → {target}"
    if already_have:
        note += "; already_have_artifact=true"
    try:
        updated = transition_task(task, to_status=str(target), actor=actor, note=note)
    except IllegalTransitionError as e:
        raise BlockResumeError(str(e)) from e

    report["to_status"] = target
    report["idempotent"] = False
    report["action"] = "resumed"
    return updated, report
