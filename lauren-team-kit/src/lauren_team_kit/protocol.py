"""Load / save / validate / create Lauren task JSON documents."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lauren_team_kit import SCHEMA_VERSION
from lauren_team_kit.atomic_io import atomic_write_json, update_json_file
from lauren_team_kit.paths import stable_dir_id
from lauren_team_kit.authz import (
    AuthzError,
    Principal,
    authorize_record_check,
    authorize_set_artifact,
    authorize_transition,
    resolve_principal,
)
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
    """Task file under the stable directory id, not the raw external id."""
    return Path(root).resolve() / "workspace" / "runs" / stable_dir_id(task_id) / "task.json"


def load_task(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"task JSON 必须是 object: {p}")
    return data


def save_task(path: Path | str, task: dict[str, Any]) -> None:
    """Atomically write task JSON (temp + replace) under a per-file lock."""
    atomic_write_json(path, task)


def update_task(
    path: Path | str,
    mutator,
    *,
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    """Load → mutate → save under one lock (Lite-C L5 concurrent-safe RMW)."""

    def _wrap(current: Any) -> Any:
        if not isinstance(current, dict):
            raise ValueError(f"task JSON 必须是 object: {path}")
        updated = mutator(current)
        if not isinstance(updated, dict):
            raise ValueError("update_task mutator 必须返回 dict")
        return updated

    return update_json_file(path, _wrap, timeout_sec=timeout_sec)


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
            exec_obj = item.get("exec")
            if exec_obj is not None:
                if not isinstance(exec_obj, dict):
                    errors.append(f"acceptance[{i}].exec 必须为 object")
                else:
                    kind = exec_obj.get("kind")
                    if kind not in ("argv", "shell"):
                        errors.append(f"acceptance[{i}].exec.kind 必须为 argv|shell")
                    if kind == "argv":
                        argv = exec_obj.get("argv")
                        if (
                            not isinstance(argv, list)
                            or not argv
                            or not all(isinstance(part, str) for part in argv)
                        ):
                            errors.append(f"acceptance[{i}].exec.argv 必须为非空字符串数组")
                    timeout = exec_obj.get("timeout_sec")
                    if timeout is not None and (
                        isinstance(timeout, bool)
                        or not isinstance(timeout, (int, float))
                        or timeout <= 0
                    ):
                        errors.append(f"acceptance[{i}].exec.timeout_sec 必须为正数")
                    env = exec_obj.get("env")
                    if env is not None and (
                        not isinstance(env, dict)
                        or not all(
                            isinstance(key, str) and isinstance(value, str)
                            for key, value in env.items()
                        )
                    ):
                        errors.append(f"acceptance[{i}].exec.env 的值必须为字符串")
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


def jsonschema_validate(
    task: dict[str, Any],
    *,
    require: bool = True,
) -> list[str]:
    """Run full schema validation.

    Lite-C L6: missing jsonschema dependency is an explicit error when
    ``require=True`` (default) — never silently skip strict schema checks.
    """
    try:
        import jsonschema  # noqa: F401
        from jsonschema import Draft202012Validator
    except ImportError:
        if require:
            return [
                "缺少 jsonschema 依赖；无法做 Schema 校验。"
                "请 pip install 'lauren-team-kit[schema]' 或 'lauren-team-kit[dev]'"
            ]
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
    require_jsonschema: bool = True,
) -> list[str]:
    errors = structural_validate(task)
    # Prefer structural first; still append jsonschema (required by default)
    js_errors = jsonschema_validate(task, require=require_jsonschema)
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
                "command": "python -m pytest -q",
                "exec": {
                    "kind": "argv",
                    "argv": ["{python}", "-m", "pytest", "-q"],
                    "cwd": "demo-app",
                    "timeout_sec": 180,
                },
                "must_run": True,
                "pass_criteria": "exit_code==0",
            }
        ],
        "worktree": {
            "path": f"workspace/runs/{stable_dir_id(task_id)}/worktree",
            "branch": f"task/{stable_dir_id(task_id)}",
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
    role: str | None = None,
    profile: str | None = None,
    principal: Principal | None = None,
    trust_level: str | None = None,
    skip_authz: bool = False,
    root: Path | str | None = None,
    skip_route_guard: bool = False,
) -> dict[str, Any]:
    """Apply a legal status transition after role authorization (T1).

    skip_authz is reserved for kit-internal repair paths; callers must not use it
    to bypass Nancy/Eng boundaries from CLI.
    Under Team engineering_chain, entering 执行中 as developer (or chief driving
    developer execute) requires an acked handoff (T2).
    """
    if not skip_authz:
        prin = resolve_principal(
            actor=actor,
            role=role,
            profile=profile,
            trust_level=trust_level,  # type: ignore[arg-type]
            principal=principal,
        )
        authorize_transition(prin, to_status)
        actor_name = prin.actor
        role_name = prin.role
    else:
        actor_name = actor
        role_name = role or "system"
        prin = None

    # T2 route guard: true developer execution under engineering_chain
    if (
        not skip_authz
        and not skip_route_guard
        and to_status == "执行中"
        and role_name in ("developer", "chief")
    ):
        from lauren_team_kit.handoff import route_guard_check

        op = "developer_execute" if role_name == "chief" else "enter_executing"
        route_guard_check(
            task,
            root=root,
            actor=actor_name,
            role=role_name,
            op=op,
        )

    from_status = task.get("status", "")
    try:
        apply_transition(str(from_status), to_status)
    except IllegalTransitionError:
        raise
    # Lite-C L5: entering 执行中 requires a real controlled worktree when root known
    if to_status == "执行中" and root is not None:
        from lauren_team_kit.worktree_ops import (
            WorktreeError,
            ensure_task_worktree,
            inspect_worktree,
        )

        insp = inspect_worktree(root, task)
        if not insp.get("ok"):
            try:
                task, _wt_rep = ensure_task_worktree(task, root=root)
            except WorktreeError as e:
                raise IllegalTransitionError(
                    f"进入执行中前工作区未就绪: {e}"
                ) from e
            insp = inspect_worktree(root, task)
            if not insp.get("ok"):
                raise IllegalTransitionError(
                    "进入执行中前工作区校验失败: "
                    + "; ".join(insp.get("errors") or ["unknown"])
                )
    if to_status == "验证通过":
        assert_verify_gate(task)
    now = _now_iso()
    entry: dict[str, Any] = {
        "at": now,
        "actor": actor_name,
        "role": role_name,
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



def set_artifact_commit(
    task: dict[str, Any],
    *,
    commit: str,
    actor: str = "developer",
    role: str | None = "developer",
    profile: str | None = None,
    principal: Principal | None = None,
    root: Path | str | None = None,
    skip_route_guard: bool = False,
) -> dict[str, Any]:
    """Developer writes artifact.commit (never combined with trusted verify).

    Under Team engineering_chain, chief cannot bypass Matcha/Eng; developer
    needs an acked handoff (T2 route_guard). Pass skip_route_guard only for
    kit-internal repair.
    """
    prin = resolve_principal(
        actor=actor, role=role, profile=profile, principal=principal
    )
    authorize_set_artifact(prin)
    if not skip_route_guard:
        from lauren_team_kit.handoff import route_guard_check

        route_guard_check(
            task,
            root=root,
            actor=prin.actor,
            role=prin.role,
            op="set_artifact",
        )
    if not isinstance(commit, str) or not commit.strip():
        raise AuthzError("artifact.commit 必须为非空字符串")
    task = dict(task)
    now = _now_iso()
    artifact = dict(task.get("artifact") or {})
    artifact["commit"] = commit.strip()
    artifact["set_by"] = prin.actor
    artifact["set_role"] = prin.role
    artifact["set_at"] = now
    task["artifact"] = artifact
    task["updated_at"] = now
    hist = list(task.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": prin.actor,
            "role": prin.role,
            "from": task.get("status"),
            "to": task.get("status"),
            "note": f"set_artifact:{commit.strip()[:12]}",
        }
    )
    task["history"] = hist
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
    actor: str | None = None,
    role: str | None = None,
    profile: str | None = None,
    principal: Principal | None = None,
    trust_level: str | None = None,
    diagnostic: bool = False,
    new_round: bool = True,
    exec_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upsert verification.checks with trust + round binding (T1).

    Trusted automatic acceptance requires verifier channel; otherwise the entry
    is stamped diagnostic/imported_evidence and verify-gate ignores it.
    Writing artifact_commit here together with trusted pass fields is refused —
    use set_artifact_commit as developer first.
    """
    if principal is None and actor is None:
        raise AuthzError(
            "record_check 需要 actor 或 principal；"
            "非 verifier 请传 diagnostic=True（不计入自动验收）"
        )
    prin = resolve_principal(
        actor=actor,
        role=role,
        profile=profile,
        trust_level=("diagnostic" if diagnostic else trust_level),  # type: ignore[arg-type]
        principal=principal,
    )

    wants_artifact = artifact_commit is not None
    # Aiming at gate / authoritative verification fields
    wants_trusted_pass = (not diagnostic) and (
        result in ("pass", "fail", "inconclusive")
        or executed is True
        or bound_commit is not None
    )

    trust_stamp = authorize_record_check(
        prin,
        diagnostic=diagnostic or prin.trust_level == "diagnostic",
        wants_trusted_pass=wants_trusted_pass,
        wants_artifact=wants_artifact,
    )

    if wants_artifact and trust_stamp == "verified_run":
        raise AuthzError(
            "可信 record_check 不得同时写 artifact.commit；先 set_artifact_commit"
        )
    if wants_artifact:
        authorize_set_artifact(prin)

    task = dict(task)
    now = _now_iso()
    verification = dict(task.get("verification") or {})

    if trust_stamp == "verified_run":
        if new_round or not verification.get("round_id"):
            round_id = str(uuid.uuid4())
            verification["round_id"] = round_id
        else:
            round_id = str(verification.get("round_id"))
        # Drop prior-round trusted checks from the active list (keep diagnostic history)
        prior = list(verification.get("checks") or [])
        archived = list(verification.get("archived_checks") or [])
        keep: list[Any] = []
        for c in prior:
            if not isinstance(c, dict):
                continue
            if c.get("trust") == "verified_run" and c.get("round_id") != round_id:
                archived.append(c)
            else:
                keep.append(c)
        verification["archived_checks"] = archived
        checks = keep
    else:
        round_id = verification.get("round_id")
        checks = list(verification.get("checks") or [])

    entry: dict[str, Any] = {
        "acceptance_id": acceptance_id,
        "executed": executed,
        "trust": trust_stamp,
        "recorded_by": prin.actor,
        "recorded_role": prin.role,
    }
    if round_id:
        entry["round_id"] = round_id
    if exit_code is not None:
        entry["exit_code"] = exit_code
    if log_path:
        entry["log_path"] = log_path
    if notes:
        entry["notes"] = notes
    if trust_stamp != "verified_run":
        entry["notes"] = (
            (notes + " | " if notes else "")
            + f"[{trust_stamp}; not counted by verify-gate]"
        )
    if exec_meta:
        for key in (
            "outcome",
            "argv",
            "cwd",
            "interpreter",
            "command_type",
            "started_at",
            "finished_at",
            "stdout_tail",
            "stderr_tail",
            "acceptance_fingerprint",
        ):
            if key in exec_meta and exec_meta[key] is not None:
                entry[key] = exec_meta[key]
        fingerprint = exec_meta.get("acceptance_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            verification["acceptance_fingerprint"] = fingerprint

    found = False
    for i, c in enumerate(checks):
        if isinstance(c, dict) and c.get("acceptance_id") == acceptance_id:
            # Replace same acceptance in current round / diagnostic upsert
            if trust_stamp == "verified_run" and c.get("round_id") not in (None, round_id):
                continue
            merged = dict(c)
            merged.update(entry)
            checks[i] = merged
            found = True
            break
    if not found:
        checks.append(entry)
    verification["checks"] = checks
    verification["ran_at"] = now

    if trust_stamp == "verified_run":
        if result is not None:
            verification["result"] = result
        if bound_commit is not None:
            verification["bound_commit"] = bound_commit
        verification["trust"] = "verified_run"
        verification["verifier"] = prin.actor
    else:
        # Diagnostic must not elevate overall result to pass for the gate
        if result is not None and result != "pass":
            verification["result"] = result
        elif result == "pass":
            # Keep a side field; authoritative result unchanged unless already set
            verification["diagnostic_result"] = "pass"
            # Do not set verification.result=pass from diagnostic
        if bound_commit is not None and trust_stamp != "verified_run":
            verification["diagnostic_bound_commit"] = bound_commit

    task["verification"] = verification

    if artifact_commit is not None and trust_stamp != "verified_run":
        # Allowed only for developer diagnostic path that isn't trusted verify —
        # still refuse nancy etc. via authorize_set_artifact above.
        artifact = dict(task.get("artifact") or {})
        artifact["commit"] = artifact_commit
        artifact["set_by"] = prin.actor
        artifact["set_role"] = prin.role
        artifact["trust"] = "untrusted_via_record_check"
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
