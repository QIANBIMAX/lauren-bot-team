"""Team v0.2: dual-task protocol under one team run (Nancy + Matcha).

Lite triangle (chief/developer/verifier) remains the default path.
This module is an optional extension: parent team_id + child task_ids.

Role boundaries are enforced by role whitelist via team.roles
(resolved actor → role), not by soft actor-name / note heuristics alone.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from lauren_team_kit.protocol import (
    create_task,
    load_task,
    save_task,
    task_path_for,
)

TEAM_SCHEMA_VERSION = "lauren-team-run/0.2"

TeamRoleName = Literal[
    "nancy", "matcha", "eng_stub", "chief", "requester", "unknown"
]

# What each Team role may / may not do (documented + enforced by role whitelist).
NANCY_MAY = (
    "summarize_progress",
    "list_child_statuses",
    "escalate_blocker_to_chief",
    "record_summary",
)
NANCY_MAY_NOT = (
    "write_code",
    "set_artifact",
    "mark_verify_pass",
    "execute_merge",
    "raise_budget",
)
MATCHA_MAY = (
    "assign_eng",
    "track_assignment",
    "request_eng_status",
    "escalate_blocker_to_chief",
    "add_child_task",
)
MATCHA_MAY_NOT = (
    "emit_code_fields",  # no artifact.commit / patches in Matcha outputs
    "write_business_code",
    "mark_verify_pass",
    "execute_merge",
)
ENG_STUB_MAY = ("acknowledge_assignment", "report_placeholder_status")
ENG_STUB_MAY_NOT = ("claim_real_implementation",)  # stubs only in this slice

_FORBIDDEN_ASSIGN_ROLES = frozenset({"code", "developer", "verifier"})
# Extra keyword defense (role whitelist is primary).
_FORBIDDEN_CONTENT_MARKERS = (
    "artifact.commit",
    "artifact",
    "验证通过",
    "verify_pass",
    "mark_verify_pass",
    "execute_merge",
    "merge_commit",
    "待合并",
    "已合并",
    "合并",
)
_FORBIDDEN_FIELD_KEYS = frozenset(
    {
        "artifact",
        "artifact.commit",
        "verification",
        "verification.result",
        "merge",
        "merge_result",
        "bound_commit",
    }
)
# Back-compat aliases used by older call sites / tests wording.
_FORBIDDEN_ASSIGN_NOTE_MARKERS = _FORBIDDEN_CONTENT_MARKERS
_FORBIDDEN_SUMMARIZE_NOTE_MARKERS = _FORBIDDEN_CONTENT_MARKERS


class TeamError(ValueError):
    """Team protocol error."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lower = text.lower()
    for m in markers:
        if m.lower() in lower:
            return True
    return False


def _resolve_team_role(team: dict[str, Any], actor: str) -> TeamRoleName:
    """Map actor display name → role using team['roles'] (case-insensitive)."""
    roles = team.get("roles") or {}
    actor_l = (actor or "").strip().lower()
    if not actor_l:
        return "unknown"

    nancy = str(roles.get("nancy") or "").strip().lower()
    matcha = str(roles.get("matcha") or "").strip().lower()
    chief = str(roles.get("chief") or "").strip().lower()
    stubs = [
        str(s).strip().lower()
        for s in (roles.get("eng_stubs") or [])
        if str(s).strip()
    ]
    requester = str(team.get("requester") or "").strip().lower()

    if nancy and actor_l == nancy:
        return "nancy"
    if matcha and actor_l == matcha:
        return "matcha"
    if chief and actor_l == chief:
        return "chief"
    if actor_l in stubs:
        return "eng_stub"
    if requester and actor_l == requester:
        return "requester"
    return "unknown"


def _require_team_role(
    team: dict[str, Any],
    actor: str,
    *,
    allowed: frozenset[str] | set[str],
    op: str,
) -> TeamRoleName:
    role = _resolve_team_role(team, actor)
    if role == "unknown":
        raise TeamError(f"未知 actor（不在 team.roles）: {actor}")
    if role not in allowed:
        raise TeamError(f"{actor}（role={role}）不得 {op}")
    return role


def refuse_forbidden_payload(
    *texts: str | None,
    fields: dict[str, Any] | None = None,
) -> None:
    """Any Team role: never write artifact / verify-pass / merge payloads.

    Structured field keys are always refused; keywords are an extra defense.
    """
    if fields:
        for key, val in fields.items():
            kl = str(key).lower()
            if key in _FORBIDDEN_FIELD_KEYS or kl in _FORBIDDEN_FIELD_KEYS:
                raise TeamError(
                    f"Team 角色不得写入禁止字段: {key}（artifact/验证通过/合并类）"
                )
            if kl in {"artifact", "verification", "merge"} and val not in (
                None,
                {},
                [],
            ):
                raise TeamError(
                    f"Team 角色不得写入禁止字段: {key}（artifact/验证通过/合并类）"
                )
    blob = "\n".join(str(x) for x in texts if x)
    if blob and _contains_marker(blob, _FORBIDDEN_CONTENT_MARKERS):
        raise TeamError(
            "Team 角色不得写入禁止内容（额外词防线：artifact/验证通过/合并类）"
        )


def team_dir(root: Path | str, team_id: str) -> Path:
    return Path(root).resolve() / "workspace" / "runs" / team_id


def team_path_for(root: Path | str, team_id: str) -> Path:
    return team_dir(root, team_id) / "team.json"


def load_team(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TeamError(f"team JSON 必须是 object: {p}")
    return data


def save_team(path: Path | str, team: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(team, f, ensure_ascii=False, indent=2)
        f.write("\n")


def create_team(
    *,
    root: Path | str,
    team_id: str,
    title: str,
    requester: str = "user",
    nancy: str = "Nancy",
    matcha: str = "Matcha",
    chief: str = "幕僚长",
    eng_stubs: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Create a Team v0.2 run document + evidence layout."""
    root_p = Path(root).resolve()
    path = team_path_for(root_p, team_id)
    if path.exists() and not force:
        raise TeamError(f"已存在: {path}（加 force 覆盖）")
    now = _now_iso()
    stubs = list(eng_stubs) if eng_stubs else ["Eng-A", "Eng-B"]
    tdir = team_dir(root_p, team_id)
    for sub in ("nancy", "matcha", "eng", "logs", "summaries"):
        (tdir / sub).mkdir(parents=True, exist_ok=True)
    team: dict[str, Any] = {
        "schema_version": TEAM_SCHEMA_VERSION,
        "team_id": team_id,
        "title": title,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "requester": requester,
        "roles": {
            "nancy": nancy,
            "matcha": matcha,
            "chief": chief,
            "eng_stubs": stubs,
        },
        "child_task_ids": [],
        "assignments": [],
        "summaries": [],
        "blockers_escalated": [],
        "history": [
            {
                "at": now,
                "actor": requester,
                "to": "active",
                "note": "create_team",
            }
        ],
        "constraints": {
            "nancy_may": list(NANCY_MAY),
            "nancy_may_not": list(NANCY_MAY_NOT),
            "matcha_may": list(MATCHA_MAY),
            "matcha_may_not": list(MATCHA_MAY_NOT),
            "eng_stub_may": list(ENG_STUB_MAY),
            "eng_stub_may_not": list(ENG_STUB_MAY_NOT),
            "note": (
                "Team v0.2 slice: dual-task + Nancy/Matcha; not Full OMB GUI; "
                "Eng are stubs; role boundaries enforced by role whitelist"
            ),
        },
    }
    save_team(path, team)
    return team


def _attach_team_fields(
    task: dict[str, Any],
    *,
    team_id: str,
    role: str | None = None,
    parent_task_id: str | None = None,
) -> dict[str, Any]:
    task = dict(task)
    team_obj: dict[str, Any] = {"team_id": team_id}
    if role:
        team_obj["role"] = role
    task["team"] = team_obj
    if parent_task_id:
        task["parent_task_id"] = parent_task_id
    return task


def add_child_task(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    title: str,
    role: str = "worker",
    requester: str = "Matcha",
    force: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a Lite task linked into the team run (dual-task support).

    Only Matcha (per team.roles) may add children.
    """
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    if not tpath.is_file():
        raise TeamError(f"找不到 team: {tpath}")
    team = load_team(tpath)
    _require_team_role(
        team,
        requester,
        allowed={"matcha"},
        op="add_child_task",
    )
    if task_id in team.get("child_task_ids", []):
        if not force:
            raise TeamError(f"child already registered: {task_id}")
    path = task_path_for(root_p, task_id)
    if path.exists() and not force:
        raise TeamError(f"已存在 task: {path}（加 force 覆盖）")

    task = create_task(
        title=title,
        task_id=task_id,
        root=root_p,
        requester=requester,
    )
    # Narrow default scope for Team children (not C1 filter demo defaults).
    task["scope"] = {
        "goal": title,
        "in_scope": [f"Team {team_id} child task"],
        "out_of_scope": [
            "Full OMB GUI",
            "4 Eng full implementation",
            "auto push",
            "fake verify pass",
        ],
    }
    task = _attach_team_fields(
        task,
        team_id=team_id,
        role=role,
        parent_task_id=None,
    )
    save_task(path, task)

    now = _now_iso()
    children = list(team.get("child_task_ids") or [])
    if task_id not in children:
        children.append(task_id)
    team["child_task_ids"] = children
    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": requester,
            "to": team.get("status", "active"),
            "note": f"add_child:{task_id}",
        }
    )
    team["history"] = hist
    team["updated_at"] = now
    save_team(tpath, team)
    return team, task


def assign_task(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    assignee: str,
    assignee_role: str = "eng_stub",
    by: str = "Matcha",
    note: str | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Matcha assigns / tracks eng work. Role whitelist + forbidden-field hard gate."""
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(
        team,
        by,
        allowed={"matcha"},
        op="assign_task",
    )
    refuse_forbidden_payload(note, fields=fields)

    if assignee_role != "eng_stub" or assignee_role in _FORBIDDEN_ASSIGN_ROLES:
        raise TeamError(
            f"Matcha 不得 emit_code_fields / 非 eng_stub 指派: assignee_role={assignee_role}"
        )

    if task_id not in (team.get("child_task_ids") or []):
        raise TeamError(f"task {task_id} 不在 team {team_id} 的 child_task_ids 中")

    stubs = list((team.get("roles") or {}).get("eng_stubs") or [])
    stubs_l = {str(s).strip().lower() for s in stubs if str(s).strip()}
    if not stubs_l or assignee.strip().lower() not in stubs_l:
        raise TeamError(
            f"assignee 不在 eng_stubs: {assignee}（允许: {stubs}）"
        )

    now = _now_iso()
    assignment = {
        "task_id": task_id,
        "assignee": assignee,
        "assignee_role": assignee_role,
        "by": by,
        "at": now,
    }
    if note:
        assignment["note"] = note
    assignments = list(team.get("assignments") or [])
    # Replace prior assignment for same task_id (latest wins).
    assignments = [a for a in assignments if a.get("task_id") != task_id]
    assignments.append(assignment)
    team["assignments"] = assignments

    # Mirror assignment onto child task.team.role / assignee
    cpath = task_path_for(root_p, task_id)
    if cpath.is_file():
        child = load_task(cpath)
        team_obj = dict(child.get("team") or {})
        team_obj["team_id"] = team_id
        team_obj["role"] = assignee_role
        team_obj["assignee"] = assignee
        team_obj["assigned_by"] = by
        team_obj["assigned_at"] = now
        child["team"] = team_obj
        child["updated_at"] = now
        hist = list(child.get("history") or [])
        hist.append(
            {
                "at": now,
                "actor": by,
                "from": child.get("status"),
                "to": child.get("status"),
                "note": f"assign:{assignee}",
            }
        )
        child["history"] = hist
        save_task(cpath, child)

    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": by,
            "to": team.get("status", "active"),
            "note": f"assign:{task_id}->{assignee}",
        }
    )
    team["history"] = hist
    team["updated_at"] = now
    save_team(tpath, team)
    return team


def collect_child_statuses(
    *,
    root: Path | str,
    team_id: str,
) -> list[dict[str, Any]]:
    """Read-only: anyone may collect child statuses."""
    root_p = Path(root).resolve()
    team = load_team(team_path_for(root_p, team_id))
    rows: list[dict[str, Any]] = []
    assign_map = {
        a["task_id"]: a for a in (team.get("assignments") or []) if "task_id" in a
    }
    for cid in team.get("child_task_ids") or []:
        cpath = task_path_for(root_p, cid)
        if not cpath.is_file():
            rows.append({"task_id": cid, "status": "missing", "exists": False})
            continue
        child = load_task(cpath)
        a = assign_map.get(cid) or {}
        rows.append(
            {
                "task_id": cid,
                "title": child.get("title"),
                "status": child.get("status"),
                "exists": True,
                "assignee": a.get("assignee"),
                "assignee_role": a.get("assignee_role"),
                "has_artifact": bool((child.get("artifact") or {}).get("commit")),
                "verification_result": (child.get("verification") or {}).get("result"),
                "blockers": [
                    b.get("code")
                    for b in (child.get("blockers") or [])
                    if isinstance(b, dict)
                ],
            }
        )
    return rows


def summarize_team(
    *,
    root: Path | str,
    team_id: str,
    by: str = "Nancy",
    note: str | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Nancy summarizes progress. Must not mark verify pass or touch artifacts."""
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(
        team,
        by,
        allowed={"nancy"},
        op="summarize_team",
    )
    refuse_forbidden_payload(note, fields=fields)

    rows = collect_child_statuses(root=root_p, team_id=team_id)
    now = _now_iso()

    blocked = [r for r in rows if r.get("status") == "受阻" or r.get("blockers")]
    active = [
        r for r in rows if r.get("status") in ("执行中", "待执行", "待验证", "需修改")
    ]
    doneish = [r for r in rows if r.get("status") in ("已完成", "验证通过", "待合并")]

    text_lines = [
        f"Team {team_id} 进度汇总 @ {now}",
        f"children={len(rows)} active={len(active)} blocked={len(blocked)} "
        f"doneish={len(doneish)}",
    ]
    for r in rows:
        text_lines.append(
            f"- {r['task_id']}: status={r.get('status')} "
            f"assignee={r.get('assignee') or '-'} blockers={r.get('blockers') or []}"
        )
    if note:
        text_lines.append(f"note: {note}")
    text = "\n".join(text_lines)

    # Escalate blockers to chief list (Nancy may escalate, not resolve)
    escalated = list(team.get("blockers_escalated") or [])
    for r in blocked:
        entry = {
            "at": now,
            "task_id": r["task_id"],
            "blockers": r.get("blockers") or [],
            "by": by,
            "to": "chief",
        }
        if entry not in escalated:
            escalated.append(entry)
    team["blockers_escalated"] = escalated

    # Summary payload stays status/assignee/blockers/has_artifact — no code fields
    summary = {
        "at": now,
        "by": by,
        "text": text,
        "child_statuses": [
            {
                "task_id": r.get("task_id"),
                "status": r.get("status"),
                "assignee": r.get("assignee"),
                "blockers": r.get("blockers"),
                "has_artifact": r.get("has_artifact"),
            }
            for r in rows
        ],
        "counts": {
            "total": len(rows),
            "active": len(active),
            "blocked": len(blocked),
            "doneish": len(doneish),
        },
    }
    summaries = list(team.get("summaries") or [])
    summaries.append(summary)
    team["summaries"] = summaries

    # Persist Nancy summary file under team evidence
    sdir = team_dir(root_p, team_id) / "summaries"
    sdir.mkdir(parents=True, exist_ok=True)
    sfile = sdir / f"summary-{now.replace(':', '').replace('+', 'p')}.md"
    sfile.write_text(text + "\n", encoding="utf-8")
    summary["path"] = str(sfile.relative_to(root_p))

    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": by,
            "to": team.get("status", "active"),
            "note": "summarize",
        }
    )
    team["history"] = hist
    team["updated_at"] = now
    save_team(tpath, team)
    return summary


def eng_status_note(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    actor: str,
    note: str,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Eng stub may only write a placeholder status note (no artifact/verify/merge)."""
    if not note or not str(note).strip():
        raise TeamError("eng status_note 需要非空备注")
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(
        team,
        actor,
        allowed={"eng_stub"},
        op="eng_status_note",
    )
    refuse_forbidden_payload(note, fields=fields)
    if task_id not in (team.get("child_task_ids") or []):
        raise TeamError(f"task {task_id} 不在 team {team_id} 的 child_task_ids 中")

    now = _now_iso()
    entry = {
        "at": now,
        "task_id": task_id,
        "by": actor,
        "note": str(note).strip(),
        "kind": "eng_status_note",
    }
    notes = list(team.get("eng_status_notes") or [])
    notes.append(entry)
    team["eng_status_notes"] = notes

    cpath = task_path_for(root_p, task_id)
    if cpath.is_file():
        child = load_task(cpath)
        hist = list(child.get("history") or [])
        hist.append(
            {
                "at": now,
                "actor": actor,
                "from": child.get("status"),
                "to": child.get("status"),
                "note": f"eng_status_note:{note.strip()}",
            }
        )
        child["history"] = hist
        child["updated_at"] = now
        save_task(cpath, child)

    edir = team_dir(root_p, team_id) / "eng"
    edir.mkdir(parents=True, exist_ok=True)
    safe_ts = now.replace(":", "").replace("+", "p")
    (edir / f"note-{task_id}-{safe_ts}.md").write_text(
        f"# eng status note\n\n- actor: {actor}\n- task: {task_id}\n"
        f"- at: {now}\n\n{note.strip()}\n",
        encoding="utf-8",
    )

    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "to": team.get("status", "active"),
            "note": f"eng_status_note:{task_id}",
        }
    )
    team["history"] = hist
    team["updated_at"] = now
    save_team(tpath, team)
    return entry


def team_status(
    *,
    root: Path | str,
    team_id: str,
    actor: str | None = None,
) -> dict[str, Any]:
    """Status snapshot. If actor given, only Nancy/Matcha (role whitelist)."""
    root_p = Path(root).resolve()
    team = load_team(team_path_for(root_p, team_id))
    if actor is not None:
        _require_team_role(
            team,
            actor,
            allowed={"nancy", "matcha"},
            op="team_status",
        )
    rows = collect_child_statuses(root=root_p, team_id=team_id)
    return {
        "team_id": team_id,
        "title": team.get("title"),
        "status": team.get("status"),
        "roles": team.get("roles"),
        "child_task_ids": team.get("child_task_ids"),
        "assignments": team.get("assignments"),
        "children": rows,
        "summaries_count": len(team.get("summaries") or []),
        "blockers_escalated": team.get("blockers_escalated") or [],
        "constraints": team.get("constraints"),
        "eng_status_notes_count": len(team.get("eng_status_notes") or []),
    }
