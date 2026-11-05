"""T2: Eng decompose → Developer handoff → ack → local/simulated execute.

OMB multi-assistant delegation is not wired: omb_delegate() returns
omb_delegation=blocked / mode=simulated. Do not claim real OMB handoff.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from lauren_team_kit.authz import AuthzError, resolve_principal
from lauren_team_kit.protocol import load_task, save_task, task_path_for
from lauren_team_kit.team import (
    TeamError,
    _current_assignee,
    _require_team_role,
    load_team,
    refuse_forbidden_payload,
    save_team,
    team_dir,
    team_path_for,
)

HandoffStatus = Literal[
    "proposed",
    "acked",
    "in_progress",
    "pending_verify",
    "rework",
    "done",
    "blocked",
]

HANDOFF_STATUSES: frozenset[str] = frozenset(
    {
        "proposed",
        "acked",
        "in_progress",
        "pending_verify",
        "rework",
        "done",
        "blocked",
    }
)

# Statuses that mean developer has been handed a live package (not merely assigned Eng).
ACTIVE_HANDOFF_FOR_EXEC: frozenset[str] = frozenset(
    {"acked", "in_progress", "pending_verify", "rework"}
)

DEFAULT_RULES_VERSION = "lauren-team-rules/0.1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def get_routing_policy(team: dict[str, Any]) -> dict[str, Any]:
    """Return routing_policy with defaults (engineering_chain, fast_path off)."""
    rp = team.get("routing_policy")
    if not isinstance(rp, dict):
        return {
            "mode": "engineering_chain",
            "fast_path_enabled": False,
            "fast_path_reason": None,
        }
    mode = str(rp.get("mode") or "engineering_chain")
    return {
        "mode": mode,
        "fast_path_enabled": bool(rp.get("fast_path_enabled")),
        "fast_path_reason": rp.get("fast_path_reason"),
    }


def list_handoffs(team: dict[str, Any]) -> list[dict[str, Any]]:
    rows = team.get("handoffs") or []
    return [h for h in rows if isinstance(h, dict)]


def find_handoff(
    team: dict[str, Any],
    *,
    handoff_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any] | None:
    rows = list_handoffs(team)
    if handoff_id:
        for h in rows:
            if h.get("handoff_id") == handoff_id:
                return h
        return None
    if task_id:
        # Latest for task_id
        matches = [h for h in rows if h.get("task_id") == task_id]
        return matches[-1] if matches else None
    return None


def _replace_handoff(team: dict[str, Any], handoff: dict[str, Any]) -> None:
    hid = handoff.get("handoff_id")
    rows = list_handoffs(team)
    out: list[dict[str, Any]] = []
    replaced = False
    for h in rows:
        if h.get("handoff_id") == hid:
            out.append(handoff)
            replaced = True
        else:
            out.append(h)
    if not replaced:
        out.append(handoff)
    team["handoffs"] = out


def _assert_eng_assignee(
    team: dict[str, Any],
    *,
    root: Path,
    task_id: str,
    actor: str,
    op: str,
) -> None:
    _require_team_role(team, actor, allowed={"eng_stub"}, op=op)
    assignee = _current_assignee(team, task_id, root)
    if not assignee or actor.strip().lower() != str(assignee).strip().lower():
        raise TeamError(
            f"{actor} 不是任务 {task_id} 的当前 Eng 负责人"
            f"（assignee={assignee}）；不得 {op}"
        )


def eng_decompose(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    actor: str,
    goal: str,
    in_scope: list[str],
    out_of_scope: list[str] | None = None,
    acceptance: list[dict[str, Any]],
    worktree: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Eng writes real acceptance + decomposition package (replaces placeholder)."""
    if not acceptance:
        raise TeamError("eng_decompose 需要非空 acceptance（替换占位验收）")
    for a in acceptance:
        if not isinstance(a, dict) or not a.get("id"):
            raise TeamError("acceptance 每项须为带 id 的对象")
        if a.get("must_run") is False and str(a.get("id")).upper() == "PENDING":
            raise TeamError("不得保留 PENDING 占位验收；请填写真实验收")
        # At least one must_run True for a real handoff package
    if not any(bool(a.get("must_run")) for a in acceptance if isinstance(a, dict)):
        raise TeamError("eng_decompose 至少一条 acceptance.must_run=true")

    refuse_forbidden_payload(notes, fields=None)
    # Soft refuse code-looking payloads in notes
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    if task_id not in (team.get("child_task_ids") or []):
        raise TeamError(f"task {task_id} 不在 team {team_id} 的 child_task_ids 中")
    _assert_eng_assignee(
        team, root=root_p, task_id=task_id, actor=actor, op="eng_decompose"
    )

    cpath = task_path_for(root_p, task_id)
    if not cpath.is_file():
        raise TeamError(f"找不到 task: {cpath}")
    child = load_task(cpath)
    now = _now_iso()

    child["scope"] = {
        "goal": goal,
        "in_scope": list(in_scope),
        "out_of_scope": list(out_of_scope or [])
        + [
            "Eng writing business code",
            "fake verify pass",
            "auto push",
        ],
    }
    # Dedup out_of_scope
    seen: set[str] = set()
    oo: list[str] = []
    for x in child["scope"]["out_of_scope"]:
        if x not in seen:
            seen.add(x)
            oo.append(x)
    child["scope"]["out_of_scope"] = oo
    child["acceptance"] = acceptance
    if worktree:
        wt = dict(child.get("worktree") or {})
        wt["path"] = worktree
        child["worktree"] = wt

    decomp = {
        "at": now,
        "by": actor,
        "goal": goal,
        "in_scope": list(in_scope),
        "acceptance_ids": [a["id"] for a in acceptance],
        "worktree": worktree,
        "notes": notes,
    }
    team_obj = dict(child.get("team") or {})
    team_obj["decomposition"] = decomp
    team_obj["decompose_status"] = "ready"
    child["team"] = team_obj
    hist = list(child.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "role": "eng_stub",
            "from": child.get("status"),
            "to": child.get("status"),
            "note": "eng_decompose",
        }
    )
    child["history"] = hist
    child["updated_at"] = now
    save_task(cpath, child)

    # Mirror on team
    packages = list(team.get("eng_packages") or [])
    packages = [p for p in packages if p.get("task_id") != task_id]
    packages.append({"task_id": task_id, **decomp})
    team["eng_packages"] = packages
    th = list(team.get("history") or [])
    th.append(
        {
            "at": now,
            "actor": actor,
            "to": team.get("status", "active"),
            "note": f"eng_decompose:{task_id}",
        }
    )
    team["history"] = th
    team["updated_at"] = now
    save_team(tpath, team)

    edir = team_dir(root_p, team_id) / "eng"
    edir.mkdir(parents=True, exist_ok=True)
    (edir / f"decompose-{task_id}.json").write_text(
        json.dumps(decomp, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return decomp


def eng_handoff_developer(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    actor: str,
    developer: str = "developer",
    worktree: str | None = None,
    rules_version: str | None = None,
    parent_task_id: str | None = None,
    note: str | None = None,
    mode: str = "local",
) -> dict[str, Any]:
    """Create a structured handoff from Eng to Developer (status=proposed)."""
    refuse_forbidden_payload(note)
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    if task_id not in (team.get("child_task_ids") or []):
        raise TeamError(f"task {task_id} 不在 team {team_id} 的 child_task_ids 中")
    _assert_eng_assignee(
        team, root=root_p, task_id=task_id, actor=actor, op="eng_handoff_developer"
    )

    cpath = task_path_for(root_p, task_id)
    child = load_task(cpath)
    team_obj = child.get("team") if isinstance(child.get("team"), dict) else {}
    if team_obj.get("decompose_status") != "ready":
        raise TeamError(
            f"任务 {task_id} 尚未 eng_decompose（decompose_status!=ready）；"
            "禁止空包 handoff"
        )
    acc = child.get("acceptance") or []
    if not any(isinstance(a, dict) and a.get("must_run") for a in acc):
        raise TeamError("handoff 前须有 must_run 真实验收")

    # Close prior open handoffs for this task
    now = _now_iso()
    for h in list_handoffs(team):
        if h.get("task_id") == task_id and h.get("status") in (
            "proposed",
            "acked",
            "in_progress",
            "pending_verify",
            "rework",
        ):
            h = dict(h)
            h["status"] = "blocked"
            h["blocked_reason"] = "superseded_by_new_handoff"
            h["updated_at"] = now
            _replace_handoff(team, h)

    hid = _new_id("ho")
    parent = parent_task_id or child.get("parent_task_id")
    wt = worktree or (child.get("worktree") or {}).get("path")
    handoff: dict[str, Any] = {
        "handoff_id": hid,
        "team_id": team_id,
        "task_id": task_id,
        "parent_task_id": parent,
        "eng": actor,
        "developer": developer,
        "acceptance_ref": {
            "ids": [a["id"] for a in acc if isinstance(a, dict) and a.get("id")],
            "summary": [
                {
                    "id": a.get("id"),
                    "must_run": a.get("must_run"),
                    "description": a.get("description"),
                }
                for a in acc
                if isinstance(a, dict)
            ],
        },
        "worktree": wt,
        "rules_version": rules_version or DEFAULT_RULES_VERSION,
        "ack": None,
        "status": "proposed",
        "mode": mode,  # local | simulated | omb (omb still blocked until bridge)
        "omb_delegation": None,
        "created_at": now,
        "updated_at": now,
    }
    if note:
        handoff["note"] = note

    _replace_handoff(team, handoff)

    # Assignment status: assigned → handed_off (Eng→Dev proposed)
    assignments = list(team.get("assignments") or [])
    for i, a in enumerate(assignments):
        if isinstance(a, dict) and a.get("task_id") == task_id:
            a = dict(a)
            a["status"] = "handed_off"
            a["handoff_id"] = hid
            a["updated_at"] = now
            assignments[i] = a
    team["assignments"] = assignments

    team_obj = dict(child.get("team") or {})
    team_obj["handoff_id"] = hid
    team_obj["handoff_status"] = "proposed"
    child["team"] = team_obj
    hist = list(child.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "role": "eng_stub",
            "from": child.get("status"),
            "to": child.get("status"),
            "note": f"eng_handoff:{hid}->{developer}",
        }
    )
    child["history"] = hist
    child["updated_at"] = now
    save_task(cpath, child)

    th = list(team.get("history") or [])
    th.append(
        {
            "at": now,
            "actor": actor,
            "to": team.get("status", "active"),
            "note": f"eng_handoff:{task_id}:{hid}",
        }
    )
    team["history"] = th
    team["updated_at"] = now
    save_team(tpath, team)
    return handoff


def ack_handoff(
    *,
    root: Path | str,
    team_id: str,
    handoff_id: str,
    actor: str,
    run_id: str | None = None,
    role: str | None = "developer",
) -> dict[str, Any]:
    """Developer acknowledges handoff (proposed → acked)."""
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    handoff = find_handoff(team, handoff_id=handoff_id)
    if not handoff:
        raise TeamError(f"找不到 handoff: {handoff_id}")
    if handoff.get("status") not in ("proposed", "rework"):
        raise TeamError(
            f"handoff {handoff_id} 状态={handoff.get('status')}，仅 proposed/rework 可 ack"
        )
    prin = resolve_principal(actor=actor, role=role)
    if prin.role != "developer":
        raise TeamError(
            f"{actor}（role={prin.role}）不得 ack_handoff；须 developer"
        )
    expected = str(handoff.get("developer") or "developer").strip().lower()
    # Allow actor "developer" / display name match
    if actor.strip().lower() not in {expected, "developer", "开发助手"}:
        # Still OK if role is developer and handoff.developer is generic
        if expected not in {"developer", "开发助手"} and actor.strip().lower() != expected:
            raise TeamError(
                f"{actor} 不是本 handoff 指定的 developer（{handoff.get('developer')}）"
            )

    now = _now_iso()
    handoff = dict(handoff)
    handoff["ack"] = {
        "at": now,
        "actor": prin.actor,
        "run_id": run_id or _new_id("run"),
    }
    handoff["status"] = "acked"
    handoff["updated_at"] = now
    _replace_handoff(team, handoff)

    # Assignment: acked
    assignments = list(team.get("assignments") or [])
    for i, a in enumerate(assignments):
        if isinstance(a, dict) and a.get("task_id") == handoff.get("task_id"):
            a = dict(a)
            a["status"] = "acked"
            a["updated_at"] = now
            assignments[i] = a
    team["assignments"] = assignments

    task_id = str(handoff["task_id"])
    cpath = task_path_for(root_p, task_id)
    if cpath.is_file():
        child = load_task(cpath)
        team_obj = dict(child.get("team") or {})
        team_obj["handoff_status"] = "acked"
        team_obj["developer_ack"] = handoff["ack"]
        child["team"] = team_obj
        hist = list(child.get("history") or [])
        hist.append(
            {
                "at": now,
                "actor": prin.actor,
                "role": "developer",
                "from": child.get("status"),
                "to": child.get("status"),
                "note": f"ack_handoff:{handoff_id}",
            }
        )
        child["history"] = hist
        child["updated_at"] = now
        save_task(cpath, child)

    th = list(team.get("history") or [])
    th.append(
        {
            "at": now,
            "actor": prin.actor,
            "to": team.get("status", "active"),
            "note": f"ack_handoff:{handoff_id}",
        }
    )
    team["history"] = th
    team["updated_at"] = now
    save_team(tpath, team)
    return handoff


def assert_handoff_ready(
    *,
    root: Path | str | None = None,
    team: dict[str, Any] | None = None,
    team_id: str | None = None,
    task_id: str,
    require_acked: bool = True,
) -> dict[str, Any]:
    """Raise if engineering_chain task lacks a ready handoff for real execution."""
    if team is None:
        if root is None or team_id is None:
            raise TeamError("assert_handoff_ready 需要 team 或 root+team_id")
        team = load_team(team_path_for(root, team_id))
    rp = get_routing_policy(team)
    if rp["mode"] == "fast_path" and rp["fast_path_enabled"]:
        return {"ok": True, "bypassed": "fast_path", "routing": rp}
    if rp["mode"] != "engineering_chain":
        return {"ok": True, "bypassed": f"mode={rp['mode']}", "routing": rp}

    handoff = find_handoff(team, task_id=task_id)
    if not handoff:
        raise TeamError(
            f"engineering_chain：任务 {task_id} 无 handoff；"
            "须 Eng 拆解并 eng_handoff_developer 后，Developer ack 才能真执行"
        )
    st = handoff.get("status")
    if require_acked and st not in ACTIVE_HANDOFF_FOR_EXEC:
        raise TeamError(
            f"engineering_chain：handoff {handoff.get('handoff_id')} "
            f"状态={st}（须 acked/in_progress/pending_verify/rework）；"
            "未接单不得宣称已委派 Developer / 进入真执行"
        )
    if not handoff.get("ack") and require_acked:
        raise TeamError(
            f"engineering_chain：handoff {handoff.get('handoff_id')} 尚无 Developer ack"
        )
    return {"ok": True, "handoff": handoff, "routing": rp}


def mark_handoff_status(
    *,
    root: Path | str,
    team_id: str,
    handoff_id: str,
    status: str,
    actor: str,
    note: str | None = None,
) -> dict[str, Any]:
    if status not in HANDOFF_STATUSES:
        raise TeamError(f"非法 handoff status: {status}")
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    handoff = find_handoff(team, handoff_id=handoff_id)
    if not handoff:
        raise TeamError(f"找不到 handoff: {handoff_id}")
    now = _now_iso()
    handoff = dict(handoff)
    handoff["status"] = status
    handoff["updated_at"] = now
    if note:
        handoff["status_note"] = note
    _replace_handoff(team, handoff)

    assignments = list(team.get("assignments") or [])
    for i, a in enumerate(assignments):
        if isinstance(a, dict) and a.get("task_id") == handoff.get("task_id"):
            a = dict(a)
            # Map handoff status onto assignment.status for Nancy views
            a["status"] = {
                "proposed": "handed_off",
                "acked": "acked",
                "in_progress": "in_progress",
                "pending_verify": "pending_verify",
                "rework": "rework",
                "done": "done",
                "blocked": "blocked",
            }.get(status, status)
            a["updated_at"] = now
            assignments[i] = a
    team["assignments"] = assignments

    task_id = str(handoff["task_id"])
    cpath = task_path_for(root_p, task_id)
    if cpath.is_file():
        child = load_task(cpath)
        team_obj = dict(child.get("team") or {})
        team_obj["handoff_status"] = status
        child["team"] = team_obj
        hist = list(child.get("history") or [])
        hist.append(
            {
                "at": now,
                "actor": actor,
                "from": child.get("status"),
                "to": child.get("status"),
                "note": f"handoff_status:{handoff_id}:{status}",
            }
        )
        child["history"] = hist
        child["updated_at"] = now
        save_task(cpath, child)

    th = list(team.get("history") or [])
    th.append(
        {
            "at": now,
            "actor": actor,
            "to": team.get("status", "active"),
            "note": f"handoff_status:{handoff_id}:{status}",
        }
    )
    team["history"] = th
    team["updated_at"] = now
    save_team(tpath, team)
    return handoff


def start_rework(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    actor: str,
    reason: str,
    developer: str | None = None,
) -> dict[str, Any]:
    """Verification failed → handoff back to original Eng (status=rework).

    Same or new developer may be scheduled by Eng via a follow-up handoff.
    Scope/dependency changes should call escalate_scope_change instead.
    """
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    handoff = find_handoff(team, task_id=task_id)
    if not handoff:
        raise TeamError(f"任务 {task_id} 无 handoff，无法 rework")
    # Eng assignee or verifier/chief may open rework
    role_try = None
    try:
        _require_team_role(team, actor, allowed={"eng_stub"}, op="start_rework")
        _assert_eng_assignee(
            team, root=root_p, task_id=task_id, actor=actor, op="start_rework"
        )
        role_try = "eng"
    except TeamError:
        prin = resolve_principal(actor=actor, role=None)
        if prin.role not in ("verifier", "chief"):
            raise TeamError(
                f"{actor} 不得 start_rework；须原 Eng / verifier / chief"
            ) from None
        role_try = prin.role

    now = _now_iso()
    handoff = dict(handoff)
    handoff["status"] = "rework"
    handoff["rework"] = {
        "at": now,
        "by": actor,
        "reason": reason,
        "developer": developer or handoff.get("developer"),
        "opened_by_role": role_try,
    }
    handoff["updated_at"] = now
    # Clear ack so Developer must re-ack the repair package after Eng re-handoffs
    # Keep ack history under rework_history
    hist_rw = list(handoff.get("rework_history") or [])
    hist_rw.append({"at": now, "prior_ack": handoff.get("ack"), "reason": reason})
    handoff["rework_history"] = hist_rw
    _replace_handoff(team, handoff)

    assignments = list(team.get("assignments") or [])
    for i, a in enumerate(assignments):
        if isinstance(a, dict) and a.get("task_id") == task_id:
            a = dict(a)
            a["status"] = "rework"
            a["updated_at"] = now
            assignments[i] = a
    team["assignments"] = assignments

    cpath = task_path_for(root_p, task_id)
    if cpath.is_file():
        child = load_task(cpath)
        team_obj = dict(child.get("team") or {})
        team_obj["handoff_status"] = "rework"
        child["team"] = team_obj
        child["updated_at"] = now
        hist = list(child.get("history") or [])
        hist.append(
            {
                "at": now,
                "actor": actor,
                "from": child.get("status"),
                "to": child.get("status"),
                "note": f"start_rework:{reason}",
            }
        )
        child["history"] = hist
        save_task(cpath, child)

    th = list(team.get("history") or [])
    th.append(
        {
            "at": now,
            "actor": actor,
            "to": team.get("status", "active"),
            "note": f"start_rework:{task_id}",
        }
    )
    team["history"] = th
    team["updated_at"] = now
    save_team(tpath, team)
    return handoff


def escalate_scope_change(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    actor: str,
    reason: str,
    to: str = "matcha",
) -> dict[str, Any]:
    """Scope/dependency change → escalate to Matcha (or chief). Not for simple rework."""
    if to not in ("matcha", "chief"):
        raise TeamError("escalate_scope_change 目标仅 matcha|chief")
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(
        team,
        actor,
        allowed={"eng_stub", "matcha", "nancy", "chief"},
        op="escalate_scope_change",
    )
    now = _now_iso()
    entry = {
        "at": now,
        "task_id": task_id,
        "by": actor,
        "to": to,
        "kind": "scope_change",
        "reason": reason,
    }
    esc = list(team.get("scope_escalations") or [])
    esc.append(entry)
    team["scope_escalations"] = esc
    # Also mirror to blockers_escalated for Nancy visibility (dedup open keys)
    be = [dict(e) for e in (team.get("blockers_escalated") or []) if isinstance(e, dict)]
    open_keys = set()
    for e in be:
        life = e.get("status") or e.get("lifecycle") or "open"
        if life != "open":
            continue
        rc = e.get("reason_code") or ((e.get("blockers") or [None])[0])
        if e.get("task_id") and rc:
            open_keys.add((str(e["task_id"]), str(rc)))
    key = (task_id, "SCOPE_CHANGE")
    if key not in open_keys:
        be.append(
            {
                "at": now,
                "task_id": task_id,
                "reason_code": "SCOPE_CHANGE",
                "blockers": ["SCOPE_CHANGE"],
                "by": actor,
                "to": to,
                "reason": reason,
                "status": "open",
                "lifecycle": "open",
            }
        )
    team["blockers_escalated"] = be
    th = list(team.get("history") or [])
    th.append(
        {
            "at": now,
            "actor": actor,
            "to": team.get("status", "active"),
            "note": f"escalate_scope_change:{task_id}->{to}",
        }
    )
    team["history"] = th
    team["updated_at"] = now
    save_team(tpath, team)
    return entry


def omb_delegate(
    *,
    root: Path | str | None = None,
    team_id: str | None = None,
    handoff_id: str | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    """Attempt real OMB multi-assistant delegation.

    Currently **blocked**: no multi-assistant bridge in kit. Always returns
    omb_delegation=blocked, mode=simulated. Callers must not claim real OMB success.
    """
    result = {
        "ok": False,
        "omb_delegation": "blocked",
        "mode": "simulated",
        "reason": (
            "kit 无真实多助手 OMB 委派桥；单助手分角色演示须标 mode=simulated / "
            "omb_delegation=blocked，禁止冒充真实委派已通"
        ),
        "actor": actor,
        "handoff_id": handoff_id,
        "team_id": team_id,
        "at": _now_iso(),
    }
    if root is not None and team_id is not None and handoff_id is not None:
        tpath = team_path_for(root, team_id)
        if tpath.is_file():
            team = load_team(tpath)
            handoff = find_handoff(team, handoff_id=handoff_id)
            if handoff:
                handoff = dict(handoff)
                handoff["omb_delegation"] = "blocked"
                handoff["mode"] = "simulated"
                handoff["omb_result"] = result
                handoff["updated_at"] = result["at"]
                _replace_handoff(team, handoff)
                team["updated_at"] = result["at"]
                save_team(tpath, team)
    return result


def route_guard_check(
    task: dict[str, Any],
    *,
    root: Path | str | None,
    actor: str,
    role: str | None,
    op: str,
) -> None:
    """Refuse chief/developer true-exec bypass under engineering_chain without handoff.

    Lite / non-team tasks: no-op.
    fast_path (explicitly enabled): allow with note that reason must exist on team.
    """
    team_obj = task.get("team") if isinstance(task.get("team"), dict) else None
    if not team_obj or not team_obj.get("team_id"):
        return  # Lite / standalone
    if root is None:
        # Cannot load team — skip rather than false-positive allow for chief bypass
        # when root missing; CLI always passes root via task path parent walk.
        return
    team_id = str(team_obj["team_id"])
    tpath = team_path_for(root, team_id)
    if not tpath.is_file():
        return
    team = load_team(tpath)
    rp = get_routing_policy(team)
    if rp["mode"] == "fast_path" and rp["fast_path_enabled"]:
        if not rp.get("fast_path_reason"):
            raise AuthzError(
                "fast_path 已启用但未记录 reason；须在 team.routing_policy.fast_path_reason 写明"
            )
        return

    prin = resolve_principal(actor=actor, role=role)
    task_id = str(task.get("task_id") or "")

    # Chief must not skip Matcha/Eng and drive developer artifacts under chain
    if prin.role == "chief" and op in ("set_artifact", "developer_execute"):
        raise AuthzError(
            f"engineering_chain：幕僚长/chief 不得绕过 Matcha/Eng 直派或代写 "
            f"developer 产物（op={op}）；请走 Matcha→Eng→handoff，或显式启用 fast_path"
        )

    if op in ("set_artifact", "developer_execute", "enter_executing"):
        try:
            assert_handoff_ready(
                team=team, task_id=task_id, require_acked=True
            )
        except TeamError as e:
            raise AuthzError(str(e)) from e


def record_local_developer_commit(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    handoff_id: str,
    commit: str,
    actor: str = "developer",
) -> dict[str, Any]:
    """Record that a local/mock developer produced a commit (does not write artifact).

    Caller should then set_artifact_commit + mark handoff in_progress/pending_verify.
    """
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    handoff = find_handoff(team, handoff_id=handoff_id)
    if not handoff:
        raise TeamError(f"找不到 handoff: {handoff_id}")
    if handoff.get("task_id") != task_id:
        raise TeamError("handoff.task_id 与参数 task_id 不一致")
    assert_handoff_ready(team=team, task_id=task_id, require_acked=True)
    now = _now_iso()
    handoff = dict(handoff)
    commits = list(handoff.get("developer_commits") or [])
    commits.append({"at": now, "commit": commit, "actor": actor, "mode": handoff.get("mode") or "local"})
    handoff["developer_commits"] = commits
    if handoff.get("status") == "acked":
        handoff["status"] = "in_progress"
    handoff["updated_at"] = now
    _replace_handoff(team, handoff)
    team["updated_at"] = now
    save_team(tpath, team)
    return handoff
