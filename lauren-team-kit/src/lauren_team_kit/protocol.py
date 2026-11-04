"""Load / save / validate / create Lauren task JSON documents."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lauren_team_kit import SCHEMA_VERSION
from lauren_team_kit.evidence import ensure_evidence_dir, evidence_relpath
from lauren_team_kit.state_machine import (
    ALL_STATUSES,
    IllegalTransitionError,
    apply_transition,
)
from lauren_team_kit.verify_gate import (
    VerifyGateError,
    assert_verify_gate,
    evaluate_verify_gate,
)

REQUIRED_TOP = (
    "schema_version",
    "task_id",
    "title",
    "status",
    "created_at",
    "updated_at",
    "requester",
    "roles",
    "scope",
    "acceptance",
    "worktree",
    "integration",
    "merge_policy",
    "evidence_dir",
    "history",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def schema_path() -> Path:
    """Prefer contracts/ next to installed package's parents, else walk up."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "contracts" / "task-protocol.schema.json",  # src/../contracts
        here.parents[3] / "contracts" / "task-protocol.schema.json",  # kit root
    ]
    for c in candidates:
        if c.is_file():
            return c
    # editable install: kit_root/contracts
    kit_root = here.parents[2]
    alt = kit_root / "contracts" / "task-protocol.schema.json"
    if alt.is_file():
        return alt
    raise FileNotFoundError(
        "找不到 contracts/task-protocol.schema.json（相对 lauren-team-kit 根）"
    )


def task_path_for(root: Path | str, task_id: str) -> Path:
    return Path(root).resolve() / "workspace" / "runs" / task_id / "task.json"


def load_task(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"task JSON 必须是 object: {p}")
    return data


def save_task(path: Path | str, task: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
        f.write("\n")


def structural_validate(task: dict[str, Any]) -> list[str]:
    """Return list of error strings; empty means OK (structural)."""
    errors: list[str] = []
    for key in REQUIRED_TOP:
        if key not in task:
            errors.append(f"缺少必填字段: {key}")
    if task.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version 必须为 {SCHEMA_VERSION!r}，实际 {task.get('schema_version')!r}"
        )
    status = task.get("status")
    if status is not None and status not in ALL_STATUSES:
        errors.append(f"非法 status: {status!r}")
    roles = task.get("roles")
    if isinstance(roles, dict):
        for r in ("chief", "developer", "verifier"):
            if r not in roles or not isinstance(roles[r], str) or not roles[r]:
                errors.append(f"roles.{r} 必填且为非空字符串")
    elif "roles" in task:
        errors.append("roles 必须为 object")

    scope = task.get("scope")
    if isinstance(scope, dict):
        for k in ("goal", "in_scope", "out_of_scope"):
            if k not in scope:
                errors.append(f"scope.{k} 必填")
        if "in_scope" in scope and not isinstance(scope["in_scope"], list):
            errors.append("scope.in_scope 必须为 array")
        if "out_of_scope" in scope and not isinstance(scope["out_of_scope"], list):
            errors.append("scope.out_of_scope 必须为 array")
    elif "scope" in task:
        errors.append("scope 必须为 object")

    acceptance = task.get("acceptance")
    if isinstance(acceptance, list):
        if len(acceptance) < 1:
            errors.append("acceptance 至少 1 项")
        for i, item in enumerate(acceptance):
            if not isinstance(item, dict):
                errors.append(f"acceptance[{i}] 必须为 object")
                continue
            for k in ("id", "description", "command", "must_run", "pass_criteria"):
                if k not in item:
                    errors.append(f"acceptance[{i}] 缺少 {k}")
            if "must_run" in item and not isinstance(item["must_run"], bool):
                errors.append(f"acceptance[{i}].must_run 必须为 boolean")
    elif "acceptance" in task:
        errors.append("acceptance 必须为 array")

    for obj_key, req in (
        ("worktree", ("path", "branch")),
        ("integration", ("branch",)),
        ("merge_policy", ("mode",)),
    ):
        obj = task.get(obj_key)
        if isinstance(obj, dict):
            for k in req:
                if k not in obj:
                    errors.append(f"{obj_key}.{k} 必填")
            if obj_key == "merge_policy" and "mode" in obj:
                if obj["mode"] not in ("confirm", "auto"):
                    errors.append("merge_policy.mode 必须为 confirm|auto")
        elif obj_key in task:
            errors.append(f"{obj_key} 必须为 object")

    history = task.get("history")
    if isinstance(history, list):
        for i, h in enumerate(history):
            if not isinstance(h, dict):
                errors.append(f"history[{i}] 必须为 object")
                continue
            for k in ("at", "actor", "to"):
                if k not in h:
                    errors.append(f"history[{i}] 缺少 {k}")
    elif "history" in task:
        errors.append("history 必须为 array")

    # Hard gate when already 验证通过
    if status == "验证通过":
        for e in evaluate_verify_gate(task):
            if e not in errors:
                errors.append(e)

    return errors


def jsonschema_validate(task: dict[str, Any]) -> list[str]:
    """If jsonschema is installed, run full schema validation; else []."""
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError:
        return []
    try:
        schema = json.loads(schema_path().read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        return [str(e)]
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(x) for x in err.path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(task), key=lambda e: list(e.path))
    ]


def validate_task(
    task: dict[str, Any],
    *,
    strict_verify: bool = False,
) -> list[str]:
    errors = structural_validate(task)
    # Prefer structural first; still append jsonschema if available
    js_errors = jsonschema_validate(task)
    # Avoid duplicates of obvious required-field noise when structural already failed
    if not errors:
        errors.extend(js_errors)
    elif js_errors:
        # still surface schema extras
        for e in js_errors:
            if e not in errors:
                errors.append(e)
    if strict_verify and task.get("status") != "验证通过":
        for e in evaluate_verify_gate(task):
            if e not in errors:
                errors.append(e)
    return errors


def create_task(
    *,
    title: str,
    task_id: str,
    root: Path | str,
    requester: str = "user",
    chief: str = "幕僚长",
    developer: str = "开发助手",
    verifier: str = "验证助手",
    goal: str | None = None,
) -> dict[str, Any]:
    root_p = Path(root).resolve()
    now = _now_iso()
    ev_rel = evidence_relpath(task_id)
    ensure_evidence_dir(root_p, task_id)
    task: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "title": title,
        "status": "待执行",
        "created_at": now,
        "updated_at": now,
        "requester": requester,
        "roles": {
            "chief": chief,
            "developer": developer,
            "verifier": verifier,
        },
        "scope": {
            "goal": goal or title,
            "in_scope": ["demo-app 筛选切片验收"],
            "out_of_scope": ["C2/C3", "OMB 真机导入", "公开远程仓"],
        },
        "acceptance": [
            {
                "id": "A1",
                "description": "demo-app 筛选 pytest 通过",
                "command": "cd demo-app && .venv/bin/python -m pytest -q",
                "must_run": True,
                "pass_criteria": "exit_code==0",
            }
        ],
        "worktree": {
            "path": f"workspace/runs/{task_id}/worktree",
            "branch": f"task/{task_id}",
        },
        "integration": {"branch": "demo/integration"},
        "merge_policy": {"mode": "confirm"},
        "evidence_dir": ev_rel,
        "history": [
            {
                "at": now,
                "actor": requester,
                "to": "待执行",
                "note": "create",
            }
        ],
    }
    path = task_path_for(root_p, task_id)
    save_task(path, task)
    return task


def transition_task(
    task: dict[str, Any],
    *,
    to_status: str,
    actor: str,
    note: str | None = None,
) -> dict[str, Any]:
    from_status = task.get("status", "")
    try:
        apply_transition(str(from_status), to_status)
    except IllegalTransitionError:
        raise
    if to_status == "验证通过":
        assert_verify_gate(task)
    now = _now_iso()
    entry: dict[str, Any] = {
        "at": now,
        "actor": actor,
        "from": from_status,
        "to": to_status,
    }
    if note:
        entry["note"] = note
    task = dict(task)
    hist = list(task.get("history") or [])
    hist.append(entry)
    task["history"] = hist
    task["status"] = to_status
    task["updated_at"] = now
    return task



def record_check(
    task: dict[str, Any],
    *,
    acceptance_id: str,
    executed: bool,
    exit_code: int | None = None,
    bound_commit: str | None = None,
    artifact_commit: str | None = None,
    result: str | None = None,
    log_path: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Upsert verification.checks + optional result/commits so verify-gate can pass."""
    task = dict(task)
    now = _now_iso()
    verification = dict(task.get("verification") or {})
    checks = list(verification.get("checks") or [])
    found = False
    entry: dict[str, Any] = {
        "acceptance_id": acceptance_id,
        "executed": executed,
    }
    if exit_code is not None:
        entry["exit_code"] = exit_code
    if log_path:
        entry["log_path"] = log_path
    if notes:
        entry["notes"] = notes
    for i, c in enumerate(checks):
        if isinstance(c, dict) and c.get("acceptance_id") == acceptance_id:
            merged = dict(c)
            merged.update(entry)
            checks[i] = merged
            found = True
            break
    if not found:
        checks.append(entry)
    verification["checks"] = checks
    verification["ran_at"] = now
    if result is not None:
        verification["result"] = result
    if bound_commit is not None:
        verification["bound_commit"] = bound_commit
    task["verification"] = verification

    if artifact_commit is not None:
        artifact = dict(task.get("artifact") or {})
        artifact["commit"] = artifact_commit
        task["artifact"] = artifact

    task["updated_at"] = now
    return task


def resolve_task_file(
    *,
    task_file: str | None,
    task_id: str | None,
    root: str | None,
) -> Path:
    if task_file:
        return Path(task_file).resolve()
    if not task_id or not root:
        raise ValueError("需要 --task-file，或同时提供 --task-id 与 --root")
    return task_path_for(root, task_id)
