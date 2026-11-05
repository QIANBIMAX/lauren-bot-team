"""Team: dual-task protocol under one team run (Nancy + Matcha).

Team edition default route is engineering_chain (Matcha → Eng → developer →
verifier). Optional fast_path is documented in pack instructions and is off
by default. This module links parent team_id + child task_ids.

Role boundaries are enforced by role whitelist via team.roles
(resolved actor → role), not by soft actor-name / note heuristics alone.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from lauren_team_kit.atomic_io import atomic_write_json
from lauren_team_kit.authz import AuthzError, Principal, authorize_eng_status_note, resolve_principal
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
    "manage_todos",
    "resolve_blocker_escalation",
    "execution_view",
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
    "set_dependencies",
    "balance_load",
)
MATCHA_MAY_NOT = (
    "emit_code_fields",  # no artifact.commit / patches in Matcha outputs
    "write_business_code",
    "mark_verify_pass",
    "execute_merge",
)
ENG_STUB_MAY = (
    "acknowledge_assignment",
    "report_placeholder_status",
    "decompose",
    "handoff_developer",
    "track_rework",
)
ENG_STUB_MAY_NOT = ("claim_real_implementation", "write_business_code")  # Eng: decompose/handoff only; never business code

_FORBIDDEN_ASSIGN_ROLES = frozenset({"code", "developer", "verifier"})
# eng_stub kept for history; eng_coordinator is the T2 semantic alias (same role).
_ALLOWED_ASSIGN_ROLES = frozenset({"eng_stub", "eng_coordinator"})
# Default max open packages per Eng (assigned/handed_off/acked/in_progress/rework).
DEFAULT_MAX_ACTIVE_PER_ENG = 2
_ACTIVE_ASSIGN_STATUSES = frozenset(
    {"assigned", "handed_off", "acked", "in_progress", "pending_verify", "rework"}
)
# Extra keyword defense (role whitelist is primary).
# Field keys always refuse authoritative result writes.
# Natural-language notes MAY describe objective status words
# (待合并 / 尚未完成 / 验证通过 as facts). Imperative / assignment
# smuggling (execute_merge, mark_verify_pass, artifact.commit=, …) still refused.
_FORBIDDEN_CONTENT_MARKERS = (
    "artifact.commit=",
    "artifact.commit",
    "verification.result=",
    "verification.result",
    "mark_verify_pass",
    "execute_merge",
    "merge_commit=",
    "merge_result=",
    "bound_commit=",
    "verify_pass",
    "请合并",
    "请验证通过",
    "标为验证通过",
    "设为验证通过",
    "写入验证通过",
    "写成验证通过",
    "执行合并",
    "标记验证通过",
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

_ALLOWED_TODO_STATUSES = frozenset({"open", "done", "escalated"})
_TODO_DONE_BASIS_EXACT = frozenset({"user_confirmed", "chief_confirmed"})
_TODO_DONE_BASIS_PREFIX = "linked_task_completed:"


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
    """Refuse authoritative result smuggling; allow objective status notes.

    Structured field keys (artifact / verification / merge …) are always refused.
    Free-text may describe status facts (e.g. 「任务待合并，尚未完成」); imperative
    or assignment phrases that try to *set* verify/merge/artifact are refused.
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
            "Team 角色不得写入禁止内容（额外词防线：命令式/赋值式 artifact·验证·合并走私）"
        )


def team_dir(root: Path | str, team_id: str) -> Path:
    from lauren_team_kit.paths import stable_dir_id

    return Path(root).resolve() / "workspace" / "runs" / stable_dir_id(team_id)


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
    atomic_write_json(path, team)


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
    """Create a Team run document + evidence layout."""
    root_p = Path(root).resolve()
    path = team_path_for(root_p, team_id)
    if path.exists() and not force:
        raise TeamError(f"已存在: {path}（加 force 覆盖）")
    now = _now_iso()
    stubs = list(eng_stubs) if eng_stubs else ["Eng-A", "Eng-B"]
    tdir = team_dir(root_p, team_id)
    from lauren_team_kit.paths import PathRuleError, assert_no_case_collision, stable_dir_id

    try:
        assert_no_case_collision(tdir.parent, stable_dir_id(team_id))
    except PathRuleError as exc:
        raise TeamError(str(exc)) from exc
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
        "routing_policy": {
            "mode": "engineering_chain",
            "fast_path_enabled": False,
            "fast_path_reason": None,
            "note": (
                "默认 engineering_chain（Matcha→Eng→Developer→Verifier）；"
                "可选 fast_path 默认关，启用须记因；幕僚长不得默认直派 developer"
            ),
        },
        "roles": {
            "nancy": nancy,
            "matcha": matcha,
            "chief": chief,
            # eng_stubs: historical field name (compat). Semantic = Eng coordinators.
            "eng_stubs": stubs,
            "eng_coordinators": list(stubs),  # T2 alias; same actors
        },
        "child_task_ids": [],
        "assignments": [],
        "dependencies": [],  # [{task_id, depends_on: [task_id, ...]}]
        "handoffs": [],
        "eng_packages": [],
        "scope_escalations": [],
        "max_active_per_eng": DEFAULT_MAX_ACTIVE_PER_ENG,
        "summaries": [],
        "blockers_escalated": [],
        "todos": [],
        "rule_receipts": [],
        "execution_view": [],
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
            "eng_coordinator_may": list(ENG_STUB_MAY),  # alias docs
            "note": (
                "Team: dual-task + Nancy/Matcha; not Full OMB GUI; "
                "Eng = decompose/handoff/rework mid-layer (never business code; ③④ not built); "
                "eng_stub field retained for history; omb multi-assist blocked/simulated; "
                "role boundaries enforced by role whitelist"
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
    parent_task_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a task linked into the team run (dual-task support).

    Only Matcha (per team.roles) may add children.

    Child tasks do NOT inherit Demo-app pytest acceptance from create_task.
    Acceptance is a neutral placeholder (must_run=false) until Eng fills real
    checks before handing off to developer. Optional top-level parent_task_id
    is supported (never nested under team — Schema additionalProperties=false).
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
            "Eng writing business code (Eng never implements)",
            "auto push",
            "fake verify pass",
        ],
    }
    # Replace Demo pytest acceptance inherited from create_task.
    # Eng must write real acceptance before developer handoff.
    task["acceptance"] = [
        {
            "id": "PENDING",
            "description": "待 Eng 拆解填写真实验收（转交 developer 前必须替换）",
            "command": "true",
            "must_run": False,
            "pass_criteria": "placeholder — Eng fills real must_run before handoff",
        }
    ]
    task = _attach_team_fields(
        task,
        team_id=team_id,
        role=role,
        parent_task_id=parent_task_id,
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
    depends_on: list[str] | None = None,
    max_active: int | None = None,
) -> dict[str, Any]:
    """Matcha assigns Eng work package + optional dependencies / load check.

    assignee_role: eng_stub (compat) or eng_coordinator (T2 alias). Stored role
    stays eng_stub for history unless explicitly eng_coordinator; both map to
    the same Eng mid-layer (never developer/verifier/code).
    """
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

    role_in = (assignee_role or "eng_stub").strip().lower().replace("-", "_")
    if role_in in _FORBIDDEN_ASSIGN_ROLES or role_in not in _ALLOWED_ASSIGN_ROLES:
        raise TeamError(
            f"Matcha 不得 emit_code_fields / 非 eng_stub|eng_coordinator 指派: assignee_role={assignee_role}"
        )
    # Prefer storing eng_stub for back-compat; record alias when eng_coordinator used
    stored_role = "eng_stub"
    role_alias = "eng_coordinator" if role_in == "eng_coordinator" else "eng_stub"

    if task_id not in (team.get("child_task_ids") or []):
        raise TeamError(f"task {task_id} 不在 team {team_id} 的 child_task_ids 中")

    stubs = list((team.get("roles") or {}).get("eng_stubs") or [])
    coords = list((team.get("roles") or {}).get("eng_coordinators") or stubs)
    allowed_actors = {str(s).strip().lower() for s in (stubs + coords) if str(s).strip()}
    if not allowed_actors or assignee.strip().lower() not in allowed_actors:
        raise TeamError(
            f"assignee 不在 eng_stubs/eng_coordinators: {assignee}（允许: {stubs}）"
        )

    # Dependency: must reference known children; reject self-dep and cycles (1-hop + DFS)
    dep_list = [d for d in (depends_on or []) if d]
    children = set(team.get("child_task_ids") or [])
    for d in dep_list:
        if d == task_id:
            raise TeamError(f"依赖冲突：任务不能依赖自己 ({task_id})")
        if d not in children:
            raise TeamError(f"依赖冲突：depends_on={d} 不在 child_task_ids")
    # Merge into team.dependencies
    existing_deps = {
        e["task_id"]: list(e.get("depends_on") or [])
        for e in (team.get("dependencies") or [])
        if isinstance(e, dict) and e.get("task_id")
    }
    if dep_list:
        existing_deps[task_id] = dep_list
    # Cycle detect
    def _has_cycle(graph: dict[str, list[str]]) -> str | None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(n: str) -> bool:
            if n in visiting:
                return True
            if n in visited:
                return False
            visiting.add(n)
            for m in graph.get(n) or []:
                if dfs(m):
                    return True
            visiting.remove(n)
            visited.add(n)
            return False

        for node in graph:
            if dfs(node):
                return node
        return None

    cyc = _has_cycle(existing_deps)
    if cyc:
        raise TeamError(f"依赖冲突：检测到环（涉及 {cyc}）")

    # Load / conflict: refuse overload
    limit = max_active if max_active is not None else int(
        team.get("max_active_per_eng") or DEFAULT_MAX_ACTIVE_PER_ENG
    )
    open_for = 0
    for a in team.get("assignments") or []:
        if not isinstance(a, dict):
            continue
        if str(a.get("assignee") or "").strip().lower() != assignee.strip().lower():
            continue
        if a.get("task_id") == task_id:
            continue  # reassignment of same task does not count twice
        st = a.get("status") or "assigned"
        if st in _ACTIVE_ASSIGN_STATUSES:
            open_for += 1
    if open_for >= limit:
        raise TeamError(
            f"负载冲突：{assignee} 已有 {open_for} 个活跃工作包（上限 {limit}）；"
            "请改派其他 Eng 或先完成/关闭已有包"
        )

    now = _now_iso()
    assignment = {
        "task_id": task_id,
        "assignee": assignee,
        "assignee_role": stored_role,
        "assignee_role_alias": role_alias,
        "by": by,
        "at": now,
        "status": "assigned",  # 已指派（尚未 Developer 接单）
        "depends_on": dep_list,
    }
    if note:
        assignment["note"] = note
    assignments = list(team.get("assignments") or [])
    # Replace prior assignment for same task_id (latest wins).
    assignments = [a for a in assignments if a.get("task_id") != task_id]
    assignments.append(assignment)
    team["assignments"] = assignments

    # Persist dependency graph
    deps_out = [
        {"task_id": tid, "depends_on": deps}
        for tid, deps in existing_deps.items()
    ]
    team["dependencies"] = deps_out

    # Mirror assignment onto child task.team.role / assignee
    cpath = task_path_for(root_p, task_id)
    if cpath.is_file():
        child = load_task(cpath)
        team_obj = dict(child.get("team") or {})
        team_obj["team_id"] = team_id
        team_obj["role"] = stored_role
        team_obj["assignee"] = assignee
        team_obj["assigned_by"] = by
        team_obj["assigned_at"] = now
        team_obj["assignment_status"] = "assigned"
        if dep_list:
            team_obj["depends_on"] = dep_list
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


def set_task_dependencies(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    depends_on: list[str],
    by: str = "Matcha",
) -> dict[str, Any]:
    """Matcha records/updates cross-package dependencies (cycle-checked)."""
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(team, by, allowed={"matcha"}, op="set_task_dependencies")
    children = set(team.get("child_task_ids") or [])
    if task_id not in children:
        raise TeamError(f"task {task_id} 不在 child_task_ids")
    dep_list = list(depends_on or [])
    for d in dep_list:
        if d == task_id:
            raise TeamError(f"依赖冲突：任务不能依赖自己 ({task_id})")
        if d not in children:
            raise TeamError(f"依赖冲突：depends_on={d} 不在 child_task_ids")
    graph = {
        e["task_id"]: list(e.get("depends_on") or [])
        for e in (team.get("dependencies") or [])
        if isinstance(e, dict) and e.get("task_id")
    }
    graph[task_id] = dep_list

    def _has_cycle(g: dict[str, list[str]]) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(n: str) -> bool:
            if n in visiting:
                return True
            if n in visited:
                return False
            visiting.add(n)
            for m in g.get(n) or []:
                if dfs(m):
                    return True
            visiting.remove(n)
            visited.add(n)
            return False

        return any(dfs(n) for n in g)

    if _has_cycle(graph):
        raise TeamError("依赖冲突：检测到环")
    team["dependencies"] = [
        {"task_id": tid, "depends_on": deps} for tid, deps in graph.items()
    ]
    now = _now_iso()
    # Mirror on assignment if present
    assignments = list(team.get("assignments") or [])
    for i, a in enumerate(assignments):
        if isinstance(a, dict) and a.get("task_id") == task_id:
            a = dict(a)
            a["depends_on"] = dep_list
            a["updated_at"] = now
            assignments[i] = a
    team["assignments"] = assignments
    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": by,
            "to": team.get("status", "active"),
            "note": f"set_dependencies:{task_id}->{dep_list}",
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
    """Read-only projection from authoritative task + team + handoff state.

    Does not invent a competing source of truth; fields are projections.
    """
    root_p = Path(root).resolve()
    team = load_team(team_path_for(root_p, team_id))
    rows: list[dict[str, Any]] = []
    assign_map = {
        a["task_id"]: a for a in (team.get("assignments") or []) if "task_id" in a
    }
    handoff_by_task: dict[str, dict[str, Any]] = {}
    for h in team.get("handoffs") or []:
        if not isinstance(h, dict) or not h.get("task_id"):
            continue
        tid = str(h["task_id"])
        prev = handoff_by_task.get(tid)
        # Prefer latest non-done; else latest by updated_at/at
        if prev is None:
            handoff_by_task[tid] = h
            continue
        prev_ts = str(prev.get("updated_at") or prev.get("at") or "")
        cur_ts = str(h.get("updated_at") or h.get("at") or "")
        if cur_ts >= prev_ts:
            handoff_by_task[tid] = h

    for cid in team.get("child_task_ids") or []:
        cpath = task_path_for(root_p, cid)
        if not cpath.is_file():
            rows.append(
                {
                    "task_id": cid,
                    "status": "missing",
                    "exists": False,
                    "responsible": "-",
                    "executor": "-",
                    "verifier": "-",
                    "updated_at": None,
                }
            )
            continue
        child = load_task(cpath)
        a = assign_map.get(cid) or {}
        team_obj = child.get("team") if isinstance(child.get("team"), dict) else {}
        h = handoff_by_task.get(cid) or {}
        ver = child.get("verification") if isinstance(child.get("verification"), dict) else {}
        verifier = ver.get("verifier")
        if not verifier:
            for c in reversed(list(ver.get("checks") or [])):
                if isinstance(c, dict) and c.get("recorded_by"):
                    verifier = c.get("recorded_by")
                    break
        responsible = a.get("assignee") or team_obj.get("assignee") or "-"
        executor = (
            h.get("developer")
            or team_obj.get("developer")
            or team_obj.get("executor")
            or "-"
        )
        rows.append(
            {
                "task_id": cid,
                "title": child.get("title"),
                "status": child.get("status"),
                "exists": True,
                "assignee": a.get("assignee"),
                "assignee_role": a.get("assignee_role"),
                "assignment_status": a.get("status") or team_obj.get("assignment_status"),
                "handoff_id": h.get("handoff_id") or team_obj.get("handoff_id"),
                "handoff_status": h.get("status") or team_obj.get("handoff_status"),
                "responsible": responsible if responsible else "-",
                "executor": executor if executor else "-",
                "verifier": verifier or "-",
                "updated_at": child.get("updated_at"),
                "has_artifact": bool((child.get("artifact") or {}).get("commit")),
                "verification_result": ver.get("result"),
                "blockers": [
                    b.get("code")
                    for b in (child.get("blockers") or [])
                    if isinstance(b, dict) and b.get("code")
                ],
            }
        )
    return rows


def build_execution_view(
    *,
    root: Path | str,
    team_id: str,
) -> list[dict[str, Any]]:
    """Projection for Nancy progress book: responsibility / executor / verifier."""
    rows = collect_child_statuses(root=root, team_id=team_id)
    view: list[dict[str, Any]] = []
    for r in rows:
        view.append(
            {
                "task_id": r.get("task_id"),
                "title": r.get("title"),
                "status": r.get("status"),
                "responsible": r.get("responsible") or "-",
                "executor": r.get("executor") or "-",
                "verifier": r.get("verifier") or "-",
                "updated_at": r.get("updated_at"),
                "blockers": r.get("blockers") or [],
                "handoff_id": r.get("handoff_id"),
                "assignment_status": r.get("assignment_status"),
                "handoff_status": r.get("handoff_status"),
                "source": "projection:task+team+handoff",
            }
        )
    return view


def _escalation_reason_code(entry: dict[str, Any]) -> str:
    rc = entry.get("reason_code")
    if rc:
        return str(rc)
    blockers = entry.get("blockers") or []
    if blockers:
        return str(blockers[0])
    return ""


def _escalation_lifecycle(entry: dict[str, Any]) -> str:
    life = entry.get("status") or entry.get("lifecycle") or "open"
    return str(life)


def _open_escalation_keys(escalated: list[Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for e in escalated:
        if not isinstance(e, dict):
            continue
        if _escalation_lifecycle(e) != "open":
            continue
        tid = str(e.get("task_id") or "")
        rc = _escalation_reason_code(e)
        if tid and rc:
            keys.add((tid, rc))
    return keys


def _sync_blocker_escalations(
    team: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    by: str,
    now: str,
) -> list[dict[str, Any]]:
    """Dedup open escalations by (task_id, reason_code); auto-resolve cleared ones."""
    escalated = [dict(e) for e in (team.get("blockers_escalated") or []) if isinstance(e, dict)]
    # Normalize legacy entries
    for e in escalated:
        if "reason_code" not in e:
            e["reason_code"] = _escalation_reason_code(e)
        if "status" not in e and "lifecycle" not in e:
            e["status"] = "open"
            e["lifecycle"] = "open"
        elif "lifecycle" not in e:
            e["lifecycle"] = e.get("status") or "open"
        elif "status" not in e:
            e["status"] = e.get("lifecycle") or "open"

    current_codes: dict[str, set[str]] = {}
    currently_blocked: set[str] = set()
    for r in rows:
        tid = str(r.get("task_id") or "")
        codes = {str(c) for c in (r.get("blockers") or []) if c}
        status = r.get("status")
        if status == "受阻" or codes:
            currently_blocked.add(tid)
            current_codes[tid] = codes or {"UNSPECIFIED_BLOCKER"}
        else:
            current_codes[tid] = set()

    # Auto-resolve: open entry whose task no longer has that reason / not blocked
    for e in escalated:
        if _escalation_lifecycle(e) != "open":
            continue
        tid = str(e.get("task_id") or "")
        rc = _escalation_reason_code(e)
        still = rc in current_codes.get(tid, set()) and tid in currently_blocked
        if not still:
            e["status"] = "resolved"
            e["lifecycle"] = "resolved"
            e["resolved_at"] = now
            e["resolved_by"] = by
            e["resolve_note"] = "auto:blocker_cleared_or_unblocked"

    open_keys = _open_escalation_keys(escalated)
    for r in rows:
        tid = str(r.get("task_id") or "")
        if tid not in currently_blocked:
            continue
        for rc in sorted(current_codes.get(tid) or []):
            if (tid, rc) in open_keys:
                continue
            escalated.append(
                {
                    "at": now,
                    "task_id": tid,
                    "reason_code": rc,
                    "blockers": [rc],
                    "by": by,
                    "to": "chief",
                    "status": "open",
                    "lifecycle": "open",
                }
            )
            open_keys.add((tid, rc))
    return escalated


def resolve_team_blocker(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    by: str = "Nancy",
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Nancy marks escalated blocker(s) resolved; resolved ones no longer alarm."""
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(
        team,
        by,
        allowed={"nancy", "matcha", "chief"},
        op="resolve_team_blocker",
    )
    refuse_forbidden_payload(note)
    now = _now_iso()
    escalated = [dict(e) for e in (team.get("blockers_escalated") or []) if isinstance(e, dict)]
    resolved_ids = 0
    for e in escalated:
        if str(e.get("task_id") or "") != task_id:
            continue
        if _escalation_lifecycle(e) != "open":
            continue
        rc = _escalation_reason_code(e)
        if reason_code and rc != reason_code:
            continue
        e["status"] = "resolved"
        e["lifecycle"] = "resolved"
        e["resolved_at"] = now
        e["resolved_by"] = by
        if note:
            e["resolve_note"] = str(note).strip()
        resolved_ids += 1
    if resolved_ids == 0:
        raise TeamError(
            f"无 open 阻塞可解除: task_id={task_id} reason_code={reason_code or '*'}"
        )
    team["blockers_escalated"] = escalated
    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": by,
            "to": team.get("status", "active"),
            "note": f"resolve_blocker:{task_id}:{reason_code or '*'}",
        }
    )
    team["history"] = hist
    team["updated_at"] = now
    # Refresh projection after resolve
    team["execution_view"] = build_execution_view(root=root_p, team_id=team_id)
    save_team(tpath, team)
    return {
        "task_id": task_id,
        "reason_code": reason_code,
        "resolved_count": resolved_ids,
        "blockers_escalated": escalated,
    }


def _validate_done_basis(done_basis: str | None) -> str:
    if not done_basis or not str(done_basis).strip():
        raise TeamError(
            "勾销待办须提供 done_basis（user_confirmed / chief_confirmed / "
            "linked_task_completed:<id>）；禁止仅因工程任务名推定完成"
        )
    basis = str(done_basis).strip()
    if basis in _TODO_DONE_BASIS_EXACT:
        return basis
    if basis.startswith(_TODO_DONE_BASIS_PREFIX) and len(basis) > len(_TODO_DONE_BASIS_PREFIX):
        return basis
    raise TeamError(
        f"非法 done_basis={basis!r}；允许 user_confirmed / chief_confirmed / "
        f"linked_task_completed:<id>"
    )


def add_team_todo(
    *,
    root: Path | str,
    team_id: str,
    text: str,
    by: str = "Nancy",
    source: str = "nancy",
    owner: str | None = None,
    linked_task_id: str | None = None,
    todo_id: str | None = None,
) -> dict[str, Any]:
    """Nancy persists a structured todo into team.json (survives restart)."""
    if not text or not str(text).strip():
        raise TeamError("todo text 不能为空")
    refuse_forbidden_payload(text)
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(
        team,
        by,
        allowed={"nancy"},
        op="add_team_todo",
    )
    now = _now_iso()
    todos = [dict(t) for t in (team.get("todos") or []) if isinstance(t, dict)]
    if todo_id:
        tid = str(todo_id).strip()
        if any(t.get("todo_id") == tid for t in todos):
            raise TeamError(f"todo_id 已存在: {tid}")
    else:
        n = 1
        existing = {str(t.get("todo_id") or "") for t in todos}
        while f"todo-{n:03d}" in existing:
            n += 1
        tid = f"todo-{n:03d}"
    entry = {
        "todo_id": tid,
        "text": str(text).strip(),
        "source": source or "nancy",
        "status": "open",
        "owner": owner or by,
        "linked_task_id": linked_task_id,
        "evidence": None,
        "done_basis": None,
        "created_at": now,
        "updated_at": now,
    }
    todos.append(entry)
    team["todos"] = todos
    team["execution_view"] = build_execution_view(root=root_p, team_id=team_id)
    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": by,
            "to": team.get("status", "active"),
            "note": f"todo_add:{tid}",
        }
    )
    team["history"] = hist
    team["updated_at"] = now
    save_team(tpath, team)
    return entry


def complete_team_todo(
    *,
    root: Path | str,
    team_id: str,
    todo_id: str,
    by: str = "Nancy",
    done_basis: str | None = None,
    evidence: str | None = None,
    status: str = "done",
) -> dict[str, Any]:
    """Mark todo done/escalated; done requires explicit done_basis evidence."""
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    _require_team_role(
        team,
        by,
        allowed={"nancy"},
        op="complete_team_todo",
    )
    st = (status or "done").strip().lower()
    if st not in _ALLOWED_TODO_STATUSES:
        raise TeamError(f"非法 todo status={status!r}")
    todos = [dict(t) for t in (team.get("todos") or []) if isinstance(t, dict)]
    target = None
    for t in todos:
        if t.get("todo_id") == todo_id:
            target = t
            break
    if target is None:
        raise TeamError(f"找不到 todo: {todo_id}")
    now = _now_iso()
    if st == "done":
        basis = _validate_done_basis(done_basis)
        target["done_basis"] = basis
        if evidence:
            target["evidence"] = evidence
        elif not target.get("evidence"):
            target["evidence"] = basis
    elif st == "escalated":
        refuse_forbidden_payload(evidence)
        if evidence:
            target["evidence"] = evidence
    target["status"] = st
    target["updated_at"] = now
    team["todos"] = todos
    team["execution_view"] = build_execution_view(root=root_p, team_id=team_id)
    hist = list(team.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": by,
            "to": team.get("status", "active"),
            "note": f"todo_{st}:{todo_id}",
        }
    )
    team["history"] = hist
    team["updated_at"] = now
    save_team(tpath, team)
    return target


def list_team_todos(
    *,
    root: Path | str,
    team_id: str,
    by: str | None = "Nancy",
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List persisted todos. Nancy (and optional read with by=None for tools)."""
    root_p = Path(root).resolve()
    tpath = team_path_for(root_p, team_id)
    team = load_team(tpath)
    if by is not None:
        _require_team_role(
            team,
            by,
            allowed={"nancy", "matcha", "chief"},
            op="list_team_todos",
        )
    todos = [dict(t) for t in (team.get("todos") or []) if isinstance(t, dict)]
    if status:
        todos = [t for t in todos if t.get("status") == status]
    return todos


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
    verified = [r for r in rows if r.get("status") == "验证通过"]
    pending_merge = [r for r in rows if r.get("status") == "待合并"]
    completed = [r for r in rows if r.get("status") == "已完成"]

    text_lines = [
        f"Team {team_id} 进度汇总 @ {now}",
        (
            f"children={len(rows)} active={len(active)} blocked={len(blocked)} "
            f"verified={len(verified)} pending_merge={len(pending_merge)} "
            f"completed={len(completed)}"
        ),
        "说明：待合并=尚未完成（不得与已完成混报）；verified/pending_merge/completed 分列",
    ]
    for r in rows:
        text_lines.append(
            f"- {r['task_id']}: status={r.get('status')} "
            f"responsible={r.get('responsible') or '-'} "
            f"executor={r.get('executor') or '-'} "
            f"verifier={r.get('verifier') or '-'} "
            f"blockers={r.get('blockers') or []} "
            f"updated_at={r.get('updated_at') or '-'}"
        )
        if r.get("status") == "待合并":
            text_lines.append(f"  · {r['task_id']} 待合并=尚未完成")
    if note:
        text_lines.append(f"note: {note}")
    open_todos = [
        t for t in (team.get("todos") or [])
        if isinstance(t, dict) and t.get("status") == "open"
    ]
    if open_todos:
        text_lines.append(f"open_todos={len(open_todos)}")
    text = "\n".join(text_lines)

    escalated = _sync_blocker_escalations(team, rows, by=by, now=now)
    team["blockers_escalated"] = escalated
    open_escalations = [
        e for e in escalated if isinstance(e, dict) and _escalation_lifecycle(e) == "open"
    ]

    view = build_execution_view(root=root_p, team_id=team_id)
    team["execution_view"] = view

    # Summary payload — no code fields; stage counts split (no doneish bucket)
    summary = {
        "at": now,
        "by": by,
        "text": text,
        "child_statuses": [
            {
                "task_id": r.get("task_id"),
                "status": r.get("status"),
                "assignee": r.get("assignee"),
                "responsible": r.get("responsible"),
                "executor": r.get("executor"),
                "verifier": r.get("verifier"),
                "blockers": r.get("blockers"),
                "has_artifact": r.get("has_artifact"),
                "updated_at": r.get("updated_at"),
            }
            for r in rows
        ],
        "execution_view": view,
        "counts": {
            "total": len(rows),
            "active": len(active),
            "blocked": len(blocked),
            "verified": len(verified),
            "pending_merge": len(pending_merge),
            "completed": len(completed),
            "open_blocker_escalations": len(open_escalations),
            "open_todos": len(open_todos),
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
    # Ensure todos key exists for older team.json
    if "todos" not in team:
        team["todos"] = []
    save_team(tpath, team)
    return summary


def _current_assignee(team: dict[str, Any], task_id: str, root: Path) -> str | None:
    for a in team.get("assignments") or []:
        if isinstance(a, dict) and a.get("task_id") == task_id and a.get("assignee"):
            return str(a["assignee"])
    cpath = task_path_for(root, task_id)
    if cpath.is_file():
        child = load_task(cpath)
        team_obj = child.get("team") if isinstance(child.get("team"), dict) else {}
        if team_obj.get("assignee"):
            return str(team_obj["assignee"])
    return None


def eng_status_note(
    *,
    root: Path | str,
    team_id: str,
    task_id: str,
    actor: str,
    note: str,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Eng mid-layer may write a status note (no artifact/verify/merge).

    Only the current assignee of the task may write an operational note (T1 / R2).
    For structured decompose/handoff use eng_decompose / eng_handoff_developer (T2).
    """
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
    assignee = _current_assignee(team, task_id, root_p)
    try:
        prin = resolve_principal(actor=actor, role="eng_stub")
        authorize_eng_status_note(principal=prin, task_id=task_id, assignee=assignee)
    except AuthzError as e:
        raise TeamError(str(e)) from e

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
    view = build_execution_view(root=root_p, team_id=team_id)
    return {
        "team_id": team_id,
        "title": team.get("title"),
        "status": team.get("status"),
        "routing_policy": team.get("routing_policy"),
        "roles": team.get("roles"),
        "child_task_ids": team.get("child_task_ids"),
        "assignments": team.get("assignments"),
        "dependencies": team.get("dependencies") or [],
        "handoffs": team.get("handoffs") or [],
        "children": rows,
        "execution_view": view,
        "todos": list(team.get("todos") or []),
        "summaries_count": len(team.get("summaries") or []),
        "blockers_escalated": team.get("blockers_escalated") or [],
        "scope_escalations": team.get("scope_escalations") or [],
        "constraints": team.get("constraints"),
        "eng_status_notes_count": len(team.get("eng_status_notes") or []),
    }
