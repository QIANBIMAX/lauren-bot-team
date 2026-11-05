"""CLI for lauren-team-kit: create, transition, block, resume, validate, …"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lauren_team_kit import __version__
from lauren_team_kit.evidence import ensure_evidence_dir
from lauren_team_kit.authz import AuthzError
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    record_check,
    resolve_task_file,
    save_task,
    set_artifact_commit,
    transition_task,
    validate_task,
)
from lauren_team_kit.resume import (
    RESUME_POINTS,
    BlockResumeError,
    block_task,
    resume_task,
)
from lauren_team_kit.doctor import collect_report, exit_code, format_report
from lauren_team_kit.runtime import (
    RuntimeGateError,
    acquire_lease,
    cancel_task,
    resume_with_reconcile,
)
from lauren_team_kit.worktree_ops import WorktreeError, ensure_task_worktree
from lauren_team_kit.budget import (
    BudgetError,
    evaluate_budget,
    record_tokens,
    set_budget,
    transition_with_budget,
)
from lauren_team_kit.lessons import (
    LessonError,
    add_candidate,
    evaluate_recurrence,
    list_store,
    load_from_store,
    publish_candidate,
    record_recurrence,
    record_rule_load,
    record_rule_receive,
    review_candidate,
)
from lauren_team_kit.state_machine import IllegalTransitionError, allowed_targets
from lauren_team_kit.rule_check import run_rule
from lauren_team_kit.merge_precheck import evaluate_merge_precheck
from lauren_team_kit.merge import (
    EXIT_AWAIT_CONFIRM,
    execute_merge,
    init_integration_branch,
    plan_merge,
)
from lauren_team_kit.verify_gate import VerifyGateError, gate_report
from lauren_team_kit.team import (
    TeamError,
    add_child_task,
    add_team_todo,
    assign_task,
    complete_team_todo,
    create_team,
    eng_status_note,
    list_team_todos,
    load_team,
    resolve_team_blocker,
    save_team,
    set_task_dependencies,
    summarize_team,
    team_path_for,
    team_status,
)
from lauren_team_kit.handoff import (
    ack_handoff,
    eng_decompose,
    eng_handoff_developer,
    escalate_scope_change,
    mark_handoff_status,
    omb_delegate,
    record_local_developer_commit,
    start_rework,
)


def _add_task_selectors(p: argparse.ArgumentParser) -> None:
    p.add_argument("--task-id", help="任务 id（配合 --root）")
    p.add_argument(
        "--root",
        help="交付根目录（含 workspace/runs/）",
    )
    p.add_argument("--task-file", help="直接指定 task.json 路径")


def _resolve_or_exit(args: argparse.Namespace) -> Path | int:
    try:
        path = resolve_task_file(
            task_file=getattr(args, "task_file", None),
            task_id=getattr(args, "task_id", None),
            root=getattr(args, "root", None),
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    return path



def _root_from_args(args: argparse.Namespace, task_path: Path | None = None) -> Path | None:
    """Prefer --root; else infer from .../workspace/runs/<id>/task.json."""
    r = getattr(args, "root", None)
    if r:
        return Path(r).resolve()
    if task_path is not None:
        # task.json → task_id → runs → workspace → root
        try:
            if task_path.name == "task.json" and task_path.parents[2].name == "workspace":
                return task_path.parents[3]
        except IndexError:
            return None
    return None

def cmd_create(args: argparse.Namespace) -> int:
    if not args.root:
        print("create 需要 --root", file=sys.stderr)
        return 2
    if not args.task_id:
        print("create 需要 --task-id", file=sys.stderr)
        return 2
    if not args.title:
        print("create 需要 --title", file=sys.stderr)
        return 2
    path = resolve_task_file(task_file=None, task_id=args.task_id, root=args.root)
    if path.exists() and not args.force:
        print(f"已存在: {path}（加 --force 覆盖）", file=sys.stderr)
        return 1
    task = create_task(
        title=args.title,
        task_id=args.task_id,
        root=args.root,
        requester=args.requester,
    )
    path = resolve_task_file(task_file=None, task_id=args.task_id, root=args.root)
    print(f"created {path}")
    print(f"status={task['status']} evidence_dir={task['evidence_dir']}")
    return 0


def cmd_transition(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    prev = task.get("status")
    auto_block = not getattr(args, "no_budget_block", False)
    try:
        updated, budget_report = transition_with_budget(
            task,
            to_status=args.to,
            actor=args.actor,
            note=args.note,
            auto_block=auto_block,
            role=getattr(args, "role", None),
            profile=getattr(args, "profile", None),
            root=_root_from_args(args, path),
        )
    except IllegalTransitionError as e:
        print(str(e), file=sys.stderr)
        return 1
    except VerifyGateError as e:
        print(str(e), file=sys.stderr)
        return 1
    except BudgetError as e:
        print(str(e), file=sys.stderr)
        return 1
    except AuthzError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    if budget_report and budget_report.get("action") == "blocked":
        print(json.dumps({
            "action": "budget_blocked",
            "path": str(path),
            "from": prev,
            "status": updated.get("status"),
            "budget": budget_report,
            "blockers": updated.get("blockers"),
            "resume": updated.get("resume"),
        }, ensure_ascii=False, indent=2))
        print(
            f"budget-blocked {path}: {prev} → 受阻 "
            f"({(budget_report.get('violations') or [{}])[0].get('code')})"
        )
        return 1
    print(f"transitioned {path}: {prev} → {updated.get('status')} (actor={args.actor})")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    errors = validate_task(task, strict_verify=bool(args.strict_verify))
    if errors:
        print(f"INVALID {path}", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"VALID {path} status={task.get('status')}")
    return 0


def cmd_init_evidence(args: argparse.Namespace) -> int:
    if args.task_file:
        task = load_task(args.task_file)
        task_id = task["task_id"]
        base = Path(args.task_file).resolve().parent
        root = base.parent.parent.parent
        ensure_evidence_dir(root, task_id)
        print(f"evidence ok: {base}")
        return 0
    if not args.task_id or not args.root:
        print("init-evidence 需要 --task-id/--root 或 --task-file", file=sys.stderr)
        return 2
    base = ensure_evidence_dir(args.root, args.task_id)
    print(f"evidence ok: {base}")
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    """Lightweight checks: task file exists, validates, show allowed next statuses."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    errors = validate_task(task)
    status = task.get("status", "")
    nexts = sorted(allowed_targets(str(status)))
    report = {
        "task_file": str(path),
        "task_id": task.get("task_id"),
        "status": status,
        "valid": not errors,
        "errors": errors,
        "allowed_next": nexts,
        "evidence_dir": task.get("evidence_dir"),
    }
    ok = not errors
    if getattr(args, "rules", None):
        base = Path(args.root).resolve() if args.root else Path.cwd()
        against = _abs(base, args.against or "demo-app")
        rr = [run_rule(_rule_path(base, r), against, args.impl) for r in args.rules]
        report["rule_checks"] = rr
        ok = ok and all(r["ok"] for r in rr)
    report["ok"] = ok
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def _abs(base: Path, p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else (base / q)


def _rule_path(base: Path, r: str) -> Path:
    for cand in (_abs(base, r), base / "lauren-team-kit" / r, Path(__file__).resolve().parents[2] / r):
        if cand.is_file():
            return cand
    return _abs(base, r)


def cmd_check_rule(args: argparse.Namespace) -> int:
    base = Path(args.root).resolve() if args.root else Path.cwd()
    rp = _rule_path(base, args.rule)
    if not rp.is_file():
        print(f"找不到规则: {rp}", file=sys.stderr)
        return 2
    rep = run_rule(rp, _abs(base, args.against), args.impl)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if rep["ok"]:
        print("PASS check-rule")
        return 0
    print(f"FAIL check-rule (impl={rep['impl']})", file=sys.stderr)
    return 1


def cmd_verify_gate(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    report = gate_report(task)
    report["task_file"] = str(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["ok"]:
        print("PASS verify-gate")
        return 0
    print("FAIL verify-gate", file=sys.stderr)
    for e in report["errors"]:
        print(f"  - {e}", file=sys.stderr)
    return 1


def cmd_merge_precheck(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    root = Path(args.root).resolve() if getattr(args, "root", None) else None
    report = evaluate_merge_precheck(task, root=root, task_file=path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["ok"]:
        print("PASS merge-precheck")
        return 0
    print("FAIL merge-precheck", file=sys.stderr)
    for item in report.get("checklist") or []:
        if not item.get("ok"):
            print(f"  - {item.get('item')}: {item.get('detail')}", file=sys.stderr)
    return 1




def cmd_init_integration(args: argparse.Namespace) -> int:
    """Create demo/integration (or named) branch from an explicit baseline."""
    report = init_integration_branch(
        args.worktree,
        baseline=args.baseline,
        branch=args.branch,
        force=bool(args.force),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("ok"):
        print("PASS init-integration" if report.get("created") or report.get("already_exists") else "OK init-integration")
        return 0
    print("FAIL init-integration", file=sys.stderr)
    if report.get("error"):
        print(f"  - {report['error']}", file=sys.stderr)
    return 1


def cmd_merge(args: argparse.Namespace) -> int:
    """Confirm-gated local merge into integration branch (never push)."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    root = Path(args.root).resolve() if getattr(args, "root", None) else None
    if not getattr(args, "confirm", False):
        # Still print plan when awaiting confirm
        plan = plan_merge(task, root=root, task_file=path)
        mp = task.get("merge_policy") if isinstance(task.get("merge_policy"), dict) else {}
        if mp.get("mode") != "auto":
            print(json.dumps({"action": "await_confirm", "plan": plan}, ensure_ascii=False, indent=2))
            print(
                "AWAIT confirm：未改 git。加 --confirm 才真正 merge（mode=auto 可免确认）。",
                file=sys.stderr,
            )
            return EXIT_AWAIT_CONFIRM

    post_paths = list(args.post_check_path) if getattr(args, "post_check_path", None) else None
    result, updated = execute_merge(
        task,
        root=root,
        task_file=path,
        confirm=True,
        actor=args.actor,
        post_check_paths=post_paths,
    )
    if result.get("action") in (
        "merged",
        "already_merged",
        "conflict",
        "post_check_failed",
        "transition_failed_after_merge",
    ):
        save_task(path, updated)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    action = result.get("action")
    if result.get("ok"):
        print(f"PASS merge ({action})")
        return 0
    if result.get("exit_code") == EXIT_AWAIT_CONFIRM:
        print("AWAIT confirm", file=sys.stderr)
        return EXIT_AWAIT_CONFIRM
    print(f"FAIL merge ({action})", file=sys.stderr)
    if result.get("message"):
        print(f"  - {result['message']}", file=sys.stderr)
    return int(result.get("exit_code") or 1)



def _parse_bool(s: str) -> bool:
    v = s.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"无法解析布尔值: {s!r}")



def cmd_block(args: argparse.Namespace) -> int:
    """Mark task 受阻 with blockers + resume anchor (Lite L3)."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    if args.resume_point not in RESUME_POINTS:
        print(
            f"非法 --resume-point: {args.resume_point!r}；允许: "
            f"{', '.join(sorted(RESUME_POINTS))}",
            file=sys.stderr,
        )
        return 2
    task = load_task(path)
    prev = task.get("status")
    try:
        updated = block_task(
            task,
            code=args.code,
            message=args.message,
            recovery_hint=args.recovery_hint or "",
            resume_point=args.resume_point,
            actor=args.actor,
            reason=args.message,
        )
    except BlockResumeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except IllegalTransitionError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    report = {
        "action": "blocked",
        "task_file": str(path),
        "from_status": prev,
        "status": updated.get("status"),
        "resume": updated.get("resume"),
        "blockers": updated.get("blockers"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"blocked {path}: {prev} → 受阻 (resume_point={args.resume_point})")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Leave 受阻 toward stored or overridden resume_point (Lite L3/L5).

    Lite-C: run lease/Git reconcile first; unknown → stay 受阻, no silent re-exec.
    Resume → 执行中 still passes L4 budget hard gate.
    """
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    auto_block = not getattr(args, "no_budget_block", False)
    root = _root_from_args(args, path)
    skip_rec = bool(getattr(args, "skip_reconcile", False))
    try:
        if root is not None and not skip_rec:
            updated, report = resume_with_reconcile(
                task,
                root=root,
                actor=args.actor,
                to_status=getattr(args, "to", None),
                clear_blocker_code=getattr(args, "clear_blocker_code", None),
                auto_block=auto_block,
            )
        else:
            updated, report = resume_task(
                task,
                actor=args.actor,
                to_status=getattr(args, "to", None),
                clear_blocker_code=getattr(args, "clear_blocker_code", None),
                auto_block=auto_block,
            )
    except BlockResumeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except RuntimeGateError as e:
        print(str(e), file=sys.stderr)
        return 1

    action = report.get("action")
    if action in ("resumed", "budget_blocked", "reconcile_blocked") or report.get("resume", {}).get("action") in (
        "resumed",
        "budget_blocked",
    ):
        save_task(path, updated)
    # flatten nested resume report for printing
    flat = report.get("resume") if isinstance(report.get("resume"), dict) else report
    print(json.dumps({"path": str(path), **{k: report.get(k) for k in ("action", "to_status", "reconcile")}, "resume": flat}, ensure_ascii=False, indent=2))
    print(
        f"resume {path}: {report.get('from_status') or flat.get('from_status')} → {updated.get('status')} "
        f"action={report.get('action') or flat.get('action')}"
    )
    if (report.get("action") == "reconcile_blocked") or (
        flat.get("action") == "budget_blocked"
    ):
        return 1
    return 0



def cmd_record_check(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    diagnostic = bool(getattr(args, "diagnostic", False))
    try:
        # Optional: developer sets artifact first when --artifact-commit given
        # together with trusted verify — refused inside record_check; split here
        # if actor is verifier and artifact provided without --allow-combined (never).
        art = args.artifact_commit
        if art and not diagnostic:
            # Prefer explicit split: set artifact as developer then record as verifier
            # Only if --set-artifact-as developer role is used; else let record_check refuse.
            pass
        updated = record_check(
            task,
            acceptance_id=args.acceptance_id,
            executed=args.executed,
            exit_code=args.exit_code,
            bound_commit=args.bound_commit,
            artifact_commit=args.artifact_commit,
            result=args.result,
            log_path=args.log_path,
            notes=args.notes,
            actor=args.actor,
            role=getattr(args, "role", None),
            profile=getattr(args, "profile", None),
            diagnostic=diagnostic,
        )
    except AuthzError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    ver = updated.get("verification") or {}
    trust = None
    checks = ver.get("checks") or []
    if checks:
        trust = checks[-1].get("trust")
    print(
        f"recorded check acceptance_id={args.acceptance_id} "
        f"executed={args.executed} result={ver.get('result')} "
        f"trust={trust} round_id={ver.get('round_id')}"
    )
    return 0


def cmd_set_artifact(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    try:
        updated = set_artifact_commit(
            task,
            commit=args.commit,
            actor=args.actor,
            role=getattr(args, "role", None) or "developer",
            profile=getattr(args, "profile", None),
            root=_root_from_args(args, path),
        )
    except AuthzError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(f"set-artifact {path}: commit={args.commit}")
    return 0


def cmd_set_budget(args: argparse.Namespace) -> int:
    """Lite L4: set budget hard limits on a task."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    try:
        updated = set_budget(
            task,
            max_attempts=args.max_attempts,
            max_duration_sec=args.max_duration_sec,
            max_tokens=args.max_tokens,
            actor=args.actor,
            allow_raise=bool(getattr(args, "allow_raise", False)),
        )
    except BudgetError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    report = {
        "action": "set_budget",
        "path": str(path),
        "budget": updated.get("budget"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"set-budget {path}: {updated.get('budget')}")
    return 0


def cmd_check_budget(args: argparse.Namespace) -> int:
    """Lite L4: evaluate budget without mutating."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    report = evaluate_budget(task, pending_attempt=bool(args.pending_attempt))
    report["path"] = str(path)
    report["task_id"] = task.get("task_id")
    report["status"] = task.get("status")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def cmd_record_tokens(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    try:
        updated = record_tokens(task, tokens=args.tokens, actor=args.actor)
    except BudgetError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({
        "action": "record_tokens",
        "budget": updated.get("budget"),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_lesson_add(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    rule_body = None
    if args.rule_file:
        rule_body = Path(args.rule_file).read_text(encoding="utf-8")
    elif args.rule_body is not None:
        rule_body = args.rule_body
    scope = None
    if getattr(args, "scope_json", None):
        try:
            scope = json.loads(args.scope_json)
        except json.JSONDecodeError as e:
            print(f"--scope-json 无效: {e}", file=sys.stderr)
            return 2
    elif getattr(args, "applies_to", None):
        scope = args.applies_to
    probe = None
    if getattr(args, "probe_json", None):
        try:
            probe = json.loads(args.probe_json)
        except json.JSONDecodeError as e:
            print(f"--probe-json 无效: {e}", file=sys.stderr)
            return 2
    elif getattr(args, "probe", None):
        probe = args.probe
    try:
        updated = add_candidate(
            task,
            lesson_id=args.id,
            summary=args.summary,
            actor=args.actor,
            rule_body=rule_body,
            proposed_rule_path=args.rule_path,
            tags=args.tag,
            scope=scope,
            applies_to=getattr(args, "applies_to", None),
            probe=probe,
            probe_ref=getattr(args, "probe_ref", None),
        )
    except LessonError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({
        "action": "lesson_add_candidate",
        "id": args.id,
        "candidates": updated.get("lessons", {}).get("candidates"),
    }, ensure_ascii=False, indent=2))
    print(f"lesson-add {args.id} on {path}")
    return 0


def cmd_lesson_review(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    approved = args.verdict == "approve"
    probe_result = None
    evidence = None
    if getattr(args, "probe_result_json", None):
        try:
            probe_result = json.loads(args.probe_result_json)
        except json.JSONDecodeError as e:
            print(f"--probe-result-json 无效: {e}", file=sys.stderr)
            return 2
    if getattr(args, "evidence_json", None):
        try:
            evidence = json.loads(args.evidence_json)
        except json.JSONDecodeError as e:
            print(f"--evidence-json 无效: {e}", file=sys.stderr)
            return 2
    try:
        updated = review_candidate(
            task,
            args.id,
            approved=approved,
            actor=args.actor,
            notes=args.notes,
            probe_result=probe_result,
            evidence=evidence,
        )
    except LessonError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({
        "action": "lesson_review",
        "id": args.id,
        "verdict": args.verdict,
        "lessons": updated.get("lessons"),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_lesson_publish(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    if not args.root:
        print("lesson-publish 需要 --root（写入 lessons/store）", file=sys.stderr)
        return 2
    task = load_task(path)
    try:
        updated, record = publish_candidate(
            task,
            args.id,
            root=args.root,
            actor=args.actor,
            write_rule=not args.no_write_rule,
        )
    except LessonError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({
        "action": "lesson_publish",
        "record": record,
        "published": updated.get("lessons", {}).get("published"),
    }, ensure_ascii=False, indent=2))
    print(f"lesson-publish {args.id} → {record.get('store_path')}")
    return 0


def cmd_lesson_list(args: argparse.Namespace) -> int:
    if args.root and not (args.task_id or args.task_file):
        items = list_store(args.root)
        print(json.dumps({"store": items, "count": len(items)}, ensure_ascii=False, indent=2))
        return 0
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    print(json.dumps({
        "task_id": task.get("task_id"),
        "lessons": task.get("lessons") or {},
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_lesson_show(args: argparse.Namespace) -> int:
    if not args.root:
        print("lesson-show 需要 --root", file=sys.stderr)
        return 2
    try:
        doc = load_from_store(args.root, args.id)
    except LessonError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0




def cmd_lesson_rule_load(args: argparse.Namespace) -> int:
    """Eng 开发包加载回执：写入 team 或 task 的 rule_receipts。"""
    if args.team_id:
        if not args.root:
            print("lesson-rule-load --team-id 需要 --root", file=sys.stderr)
            return 2
        tpath = team_path_for(args.root, args.team_id)
        if not tpath.is_file():
            print(f"找不到 team: {tpath}", file=sys.stderr)
            return 1
        host = load_team(tpath)
        try:
            updated = record_rule_load(
                host,
                eng=args.eng,
                lesson_id=args.id,
                rules_version=args.rules_version,
                actor=args.actor,
            )
        except LessonError as e:
            print(str(e), file=sys.stderr)
            return 1
        save_team(tpath, updated)
        print(json.dumps({
            "action": "lesson_rule_load",
            "host": "team",
            "team_id": args.team_id,
            "receipts": updated.get("rule_receipts"),
        }, ensure_ascii=False, indent=2))
        return 0
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    try:
        updated = record_rule_load(
            task,
            eng=args.eng,
            lesson_id=args.id,
            rules_version=args.rules_version,
            actor=args.actor,
        )
    except LessonError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({
        "action": "lesson_rule_load",
        "host": "task",
        "task_id": updated.get("task_id"),
        "receipts": updated.get("rule_receipts"),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_lesson_rule_receive(args: argparse.Namespace) -> int:
    """Developer 接收回执。"""
    if args.team_id:
        if not args.root:
            print("lesson-rule-receive --team-id 需要 --root", file=sys.stderr)
            return 2
        tpath = team_path_for(args.root, args.team_id)
        if not tpath.is_file():
            print(f"找不到 team: {tpath}", file=sys.stderr)
            return 1
        host = load_team(tpath)
        try:
            updated = record_rule_receive(
                host,
                developer=args.developer,
                lesson_id=args.id,
                rules_version=args.rules_version,
                actor=args.actor,
                handoff_id=args.handoff_id,
            )
        except LessonError as e:
            print(str(e), file=sys.stderr)
            return 1
        save_team(tpath, updated)
        print(json.dumps({
            "action": "lesson_rule_receive",
            "host": "team",
            "team_id": args.team_id,
            "receipts": updated.get("rule_receipts"),
        }, ensure_ascii=False, indent=2))
        return 0
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    try:
        updated = record_rule_receive(
            task,
            developer=args.developer,
            lesson_id=args.id,
            rules_version=args.rules_version,
            actor=args.actor,
            handoff_id=args.handoff_id,
        )
    except LessonError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({
        "action": "lesson_rule_receive",
        "host": "task",
        "task_id": updated.get("task_id"),
        "receipts": updated.get("rule_receipts"),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_lesson_recurrence(args: argparse.Namespace) -> int:
    """对已发布经验跑/记防复发探针结果。"""
    if not args.root:
        print("lesson-recurrence 需要 --root", file=sys.stderr)
        return 2
    try:
        probe_result = json.loads(args.probe_result_json)
    except json.JSONDecodeError as e:
        print(f"--probe-result-json 无效: {e}", file=sys.stderr)
        return 2
    try:
        result = evaluate_recurrence(args.root, args.id, probe_result=probe_result)
    except LessonError as e:
        print(str(e), file=sys.stderr)
        return 1
    # optional persist on task/team
    if args.team_id:
        tpath = team_path_for(args.root, args.team_id)
        host = load_team(tpath)
        host = record_recurrence(host, result, actor=args.actor)
        save_team(tpath, host)
    elif args.task_id or args.task_file:
        path = _resolve_or_exit(args)
        if isinstance(path, int):
            return path
        task = load_task(path)
        task = record_recurrence(task, result, actor=args.actor)
        save_task(path, task)
    print(json.dumps({"action": "lesson_recurrence", "result": result}, ensure_ascii=False, indent=2))
    return 0 if result.get("recurrence_blocked") or result.get("probe_passed") else 0


def cmd_team_create(args: argparse.Namespace) -> int:
    try:
        team = create_team(
            root=args.root,
            team_id=args.team_id,
            title=args.title,
            requester=args.requester,
            force=args.force,
            eng_stubs=args.eng_stub or None,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    path = team_path_for(args.root, args.team_id)
    print(f"created_team {path}")
    print(json.dumps({"team_id": team["team_id"], "status": team["status"], "roles": team["roles"]}, ensure_ascii=False))
    return 0


def cmd_team_add_task(args: argparse.Namespace) -> int:
    try:
        team, task = add_child_task(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            title=args.title,
            role=args.role,
            requester=args.actor,
            force=args.force,
            parent_task_id=args.parent_task_id,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"added_child team={team['team_id']} task={task['task_id']} status={task['status']}")
    print(json.dumps({
        "team_id": team["team_id"],
        "child_task_ids": team["child_task_ids"],
        "task_team": task.get("team"),
    }, ensure_ascii=False))
    return 0


def cmd_team_assign(args: argparse.Namespace) -> int:
    try:
        team = assign_task(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            assignee=args.assignee,
            assignee_role=args.assignee_role,
            by=args.actor,
            note=args.note,
            depends_on=getattr(args, "depends_on", None) or None,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    last = (team.get("assignments") or [])[-1] if team.get("assignments") else {}
    print(f"assigned {args.task_id} -> {args.assignee} ({args.assignee_role}) by {args.actor}")
    print(json.dumps(last, ensure_ascii=False))
    return 0


def cmd_team_summarize(args: argparse.Namespace) -> int:
    try:
        summary = summarize_team(
            root=args.root,
            team_id=args.team_id,
            by=args.actor,
            note=args.note,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(summary["text"])
    print(json.dumps({
        "by": summary["by"],
        "counts": summary["counts"],
        "path": summary.get("path"),
        "child_statuses": summary["child_statuses"],
    }, ensure_ascii=False))
    return 0


def cmd_team_status(args: argparse.Namespace) -> int:
    try:
        st = team_status(
            root=args.root,
            team_id=args.team_id,
            actor=getattr(args, "actor", None),
        )
    except (TeamError, FileNotFoundError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def cmd_team_todo_add(args: argparse.Namespace) -> int:
    try:
        entry = add_team_todo(
            root=args.root,
            team_id=args.team_id,
            text=args.text,
            by=args.actor,
            source=args.source,
            owner=args.owner,
            linked_task_id=args.linked_task_id,
            todo_id=args.todo_id,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def cmd_team_todo_done(args: argparse.Namespace) -> int:
    try:
        entry = complete_team_todo(
            root=args.root,
            team_id=args.team_id,
            todo_id=args.todo_id,
            by=args.actor,
            done_basis=args.done_basis,
            evidence=args.evidence,
            status=args.status,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def cmd_team_todo_list(args: argparse.Namespace) -> int:
    try:
        todos = list_team_todos(
            root=args.root,
            team_id=args.team_id,
            by=args.actor,
            status=args.status,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(todos, ensure_ascii=False, indent=2))
    return 0


def cmd_team_blocker_resolve(args: argparse.Namespace) -> int:
    try:
        result = resolve_team_blocker(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            by=args.actor,
            reason_code=args.reason_code,
            note=args.note,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps({
        "task_id": result["task_id"],
        "reason_code": result.get("reason_code"),
        "resolved_count": result["resolved_count"],
    }, ensure_ascii=False))
    return 0


def cmd_team_eng_note(args: argparse.Namespace) -> int:
    try:
        entry = eng_status_note(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            actor=args.actor,
            note=args.note,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"eng_status_note task={args.task_id} by={args.actor}")
    print(json.dumps(entry, ensure_ascii=False))
    return 0



def cmd_team_eng_decompose(args: argparse.Namespace) -> int:
    """Eng writes real acceptance + decomposition package."""
    import json as _json
    acceptance = _json.loads(args.acceptance_json)
    if not isinstance(acceptance, list):
        print("acceptance-json 须为 JSON 数组", file=sys.stderr)
        return 2
    in_scope = list(args.in_scope or [])
    out_of_scope = list(args.out_of_scope or [])
    try:
        decomp = eng_decompose(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            actor=args.actor,
            goal=args.goal,
            in_scope=in_scope,
            out_of_scope=out_of_scope,
            acceptance=acceptance,
            worktree=args.worktree,
            notes=args.note,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"eng_decompose task={args.task_id} by={args.actor}")
    print(json.dumps(decomp, ensure_ascii=False, indent=2))
    return 0


def cmd_team_handoff(args: argparse.Namespace) -> int:
    try:
        handoff = eng_handoff_developer(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            actor=args.actor,
            developer=args.developer,
            worktree=args.worktree,
            rules_version=args.rules_version,
            parent_task_id=args.parent_task_id,
            note=args.note,
            mode=args.mode,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"handoff {handoff['handoff_id']} task={args.task_id} -> {args.developer}")
    print(json.dumps(handoff, ensure_ascii=False, indent=2))
    return 0


def cmd_team_ack_handoff(args: argparse.Namespace) -> int:
    try:
        handoff = ack_handoff(
            root=args.root,
            team_id=args.team_id,
            handoff_id=args.handoff_id,
            actor=args.actor,
            run_id=args.run_id,
            role=getattr(args, "role", None) or "developer",
        )
    except (TeamError, AuthzError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"acked {args.handoff_id} by={args.actor}")
    print(json.dumps(handoff, ensure_ascii=False, indent=2))
    return 0


def cmd_team_handoff_status(args: argparse.Namespace) -> int:
    try:
        handoff = mark_handoff_status(
            root=args.root,
            team_id=args.team_id,
            handoff_id=args.handoff_id,
            status=args.status,
            actor=args.actor,
            note=args.note,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(handoff, ensure_ascii=False, indent=2))
    return 0


def cmd_team_rework(args: argparse.Namespace) -> int:
    try:
        handoff = start_rework(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            actor=args.actor,
            reason=args.reason,
            developer=args.developer,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"rework task={args.task_id}")
    print(json.dumps(handoff, ensure_ascii=False, indent=2))
    return 0


def cmd_team_escalate_scope(args: argparse.Namespace) -> int:
    try:
        entry = escalate_scope_change(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            actor=args.actor,
            reason=args.reason,
            to=args.to,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


def cmd_team_omb_delegate(args: argparse.Namespace) -> int:
    result = omb_delegate(
        root=args.root,
        team_id=args.team_id,
        handoff_id=args.handoff_id,
        actor=args.actor,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Always non-zero-ish? Keep 0 but clearly blocked so scripts can assert fields.
    return 0


def cmd_team_record_commit(args: argparse.Namespace) -> int:
    try:
        handoff = record_local_developer_commit(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            handoff_id=args.handoff_id,
            commit=args.commit,
            actor=args.actor,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(handoff, ensure_ascii=False, indent=2))
    return 0


def cmd_team_set_deps(args: argparse.Namespace) -> int:
    try:
        team = set_task_dependencies(
            root=args.root,
            team_id=args.team_id,
            task_id=args.task_id,
            depends_on=list(args.depends_on or []),
            by=args.actor,
        )
    except TeamError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps({"dependencies": team.get("dependencies")}, ensure_ascii=False, indent=2))
    return 0



def cmd_prepare_worktree(args: argparse.Namespace) -> int:
    """Create/verify a real git worktree under the controlled runs path (Lite-C L5)."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    root = _root_from_args(args, path)
    if root is None:
        print("prepare-worktree 需要 --root（或标准 workspace/runs 布局）", file=sys.stderr)
        return 2
    task = load_task(path)
    try:
        updated, report = ensure_task_worktree(
            task,
            root=root,
            base_repo=getattr(args, "base_repo", None),
            bootstrap_base=not bool(getattr(args, "no_bootstrap", False)),
        )
    except WorktreeError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({"path": str(path), "worktree": updated.get("worktree"), "report": report}, ensure_ascii=False, indent=2))
    print(f"prepare-worktree {path}: action={report.get('action')}")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    """Cancel task: 已取消 + lease cancel_requested (+ best-effort SIGTERM). Lite-C L5."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    root = _root_from_args(args, path)
    try:
        updated, report = cancel_task(
            task,
            actor=args.actor,
            reason=getattr(args, "reason", None),
            signal_process=not bool(getattr(args, "no_signal", False)),
            root=root,
        )
    except RuntimeGateError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(json.dumps({"path": str(path), **report, "cancel": updated.get("cancel")}, ensure_ascii=False, indent=2))
    print(f"cancelled {path}: {report.get('from_status')} → 已取消")
    return 0


def cmd_acquire_lease(args: argparse.Namespace) -> int:
    """Record an active executor lease (protocol-level; Lite-C)."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
    pid = getattr(args, "pid", None)
    updated = acquire_lease(
        task, holder=args.holder, pid=pid, note=getattr(args, "note", None)
    )
    save_task(path, updated)
    print(json.dumps(updated.get("executor_lease"), ensure_ascii=False, indent=2))
    return 0



def cmd_run_acceptance(args: argparse.Namespace) -> int:
    """Run every must_run check in one round. Shell strings are not split."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    root = _root_from_args(args, path)
    if root is None:
        print("run-acceptance 需要 --root（cwd 与相对路径以此为基准）", file=sys.stderr)
        return 2
    from lauren_team_kit.exec_run import run_must_run_round

    task = load_task(path)
    try:
        updated, summary = run_must_run_round(task, base=root)
    except AuthzError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    bound = getattr(args, "bound_commit", None)
    if bound:
        verification = dict(updated.get("verification") or {})
        verification["bound_commit"] = bound
        updated["verification"] = verification
    save_task(path, updated)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    print(f"run-acceptance ok={summary.get('ok')} round_id={summary.get('round_id')}")
    return 0 if summary.get("ok") else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    """Print a machine-readable environment report. Does not mutate git or raise privileges."""
    report = collect_report(root=getattr(args, "root", None))
    sys.stdout.write(format_report(report))
    return exit_code(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lauren-team-kit",
        description="Lauren 任务协议 CLI（create / transition / validate / …）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser(
        "doctor",
        help="环境诊断 JSON（不写 git 配置、不提权、不探测 OMB）",
    )
    p_doc.add_argument(
        "--root",
        default=None,
        help="额外检查该交付根是否可写",
    )
    p_doc.set_defaults(func=cmd_doctor)

    p_create = sub.add_parser("create", help="创建任务 JSON + 证据目录")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--task-id", required=True)
    p_create.add_argument("--root", required=True)
    p_create.add_argument("--requester", default="user")
    p_create.add_argument("--force", action="store_true")
    p_create.set_defaults(func=cmd_create)

    p_tr = sub.add_parser("transition", help="合法状态迁移并写 history")
    _add_task_selectors(p_tr)
    p_tr.add_argument("--to", required=True, help="目标状态")
    p_tr.add_argument("--actor", required=True, help="操作者（如 chief/developer）")
    p_tr.add_argument(
        "--role",
        default=None,
        help="可信角色映射：chief|developer|verifier|nancy|matcha|eng_stub|merge_bot",
    )
    p_tr.add_argument("--profile", default=None, help="同 --role（别名）")
    p_tr.add_argument("--note", default=None)
    p_tr.add_argument(
        "--no-budget-block",
        action="store_true",
        help="预算超额时抛错而不自动受阻（默认自动 block→受阻）",
    )
    p_tr.set_defaults(func=cmd_transition)

    p_val = sub.add_parser("validate", help="校验 task.json")
    _add_task_selectors(p_val)
    p_val.add_argument(
        "--strict-verify",
        action="store_true",
        help="无论当前状态，均跑 must_run×checks 硬门",
    )
    p_val.set_defaults(func=cmd_validate)

    p_ev = sub.add_parser("init-evidence", help="幂等创建证据目录")
    _add_task_selectors(p_ev)
    p_ev.set_defaults(func=cmd_init_evidence)

    p_pf = sub.add_parser("preflight", help="校验 + 列出允许的下一状态")
    _add_task_selectors(p_pf)
    p_pf.add_argument("--rules", action="append", default=None, help="附加规则探针（可多次）")
    p_pf.add_argument("--against", default=None, help="demo 根（默认 ROOT/demo-app）")
    p_pf.add_argument("--impl", default=None, choices=["fixed", "buggy"])

    p_cr = sub.add_parser("check-rule", help="对 demo 根跑规则验收探针")
    p_cr.add_argument("--rule", required=True)
    p_cr.add_argument("--against", required=True)
    p_cr.add_argument("--root", default=None)
    p_cr.add_argument("--impl", default=None, choices=["fixed", "buggy"])
    p_cr.set_defaults(func=cmd_check_rule)
    p_pf.set_defaults(func=cmd_preflight)

    p_vg = sub.add_parser("verify-gate", help="评估 must_run×checks 硬门（不改状态）")
    _add_task_selectors(p_vg)
    p_vg.set_defaults(func=cmd_verify_gate)

    p_ra = sub.add_parser(
        "run-acceptance",
        help="同一轮执行全部 must_run（argv/cwd/env/timeout；旧 shell 字符串不拆词）",
    )
    _add_task_selectors(p_ra)
    p_ra.add_argument(
        "--bound-commit",
        default=None,
        help="可选：写入 verification.bound_commit（不代替 set-artifact）",
    )
    p_ra.set_defaults(func=cmd_run_acceptance)

    p_mp = sub.add_parser("merge-precheck", help="合并前本地 Git 预检（不执行 merge）")
    _add_task_selectors(p_mp)
    p_mp.set_defaults(func=cmd_merge_precheck)

    p_rc = sub.add_parser(
        "record-check",
        help="写入 verification.checks（verifier 可信；--diagnostic 仅诊断）",
    )
    _add_task_selectors(p_rc)
    p_rc.add_argument("--acceptance-id", required=True)
    p_rc.add_argument("--executed", type=_parse_bool, required=True)
    p_rc.add_argument("--exit-code", type=int, default=None)
    p_rc.add_argument("--bound-commit", default=None)
    p_rc.add_argument(
        "--artifact-commit",
        default=None,
        help="勿与可信验收同用；请改用 set-artifact",
    )
    p_rc.add_argument("--result", default=None, choices=["pass", "fail", "inconclusive"])
    p_rc.add_argument("--log-path", default=None)
    p_rc.add_argument("--notes", default=None)
    p_rc.add_argument("--actor", required=True, help="执行身份（须与 --role 匹配）")
    p_rc.add_argument("--role", default=None, help="chief|developer|verifier|…")
    p_rc.add_argument("--profile", default=None)
    p_rc.add_argument(
        "--diagnostic",
        action="store_true",
        help="标记为 diagnostic/imported_evidence，不计入 verify-gate",
    )
    p_rc.set_defaults(func=cmd_record_check)

    p_sa = sub.add_parser("set-artifact", help="开发者写入 artifact.commit（与验收分离）")
    _add_task_selectors(p_sa)
    p_sa.add_argument("--commit", required=True)
    p_sa.add_argument("--actor", default="developer")
    p_sa.add_argument("--role", default="developer")
    p_sa.add_argument("--profile", default=None)
    p_sa.set_defaults(func=cmd_set_artifact)


    p_ii = sub.add_parser(
        "init-integration",
        help="从明确基线创建本地 demo/integration（不猜测脏工作区；默认不覆盖）",
    )
    p_ii.add_argument("--worktree", required=True, help="git 工作区路径（Demo 仓库）")
    p_ii.add_argument(
        "--baseline",
        required=True,
        help="干净基线 commit/分支/标签（如 main 的完整 SHA）",
    )
    p_ii.add_argument(
        "--branch",
        default="demo/integration",
        help="集成分支名（默认 demo/integration）",
    )
    p_ii.add_argument(
        "--force",
        action="store_true",
        help="若分支已存在则强制移到基线（危险）",
    )
    p_ii.set_defaults(func=cmd_init_integration)

    p_mg = sub.add_parser(
        "merge",
        help="确认后合入本地集成分支（默认需 --confirm；永不 push）",
    )
    _add_task_selectors(p_mg)
    p_mg.add_argument(
        "--confirm",
        action="store_true",
        help="真正执行 merge；缺省且 mode=confirm 时只打印计划并 exit 3",
    )
    p_mg.add_argument("--actor", default="merge", help="写入 history 的 actor")
    p_mg.add_argument(
        "--post-check-path",
        action="append",
        default=None,
        help="合并后须存在的相对 worktree 路径（可多次）",
    )
    p_mg.set_defaults(func=cmd_merge)


    p_blk = sub.add_parser(
        "block",
        help="标记受阻：写 blockers + resume 锚点（Lite L3）",
    )
    _add_task_selectors(p_blk)
    p_blk.add_argument("--code", required=True, help="受阻代码，如 MISSING_DEP / UNWRITABLE")
    p_blk.add_argument("--message", required=True, help="受阻说明")
    p_blk.add_argument(
        "--recovery-hint",
        default="",
        help="恢复提示（缺依赖/权限等）",
    )
    p_blk.add_argument(
        "--resume-point",
        required=True,
        choices=sorted(RESUME_POINTS),
        help="恢复后应回到的状态",
    )
    p_blk.add_argument("--actor", default="chief", help="写入 history 的 actor")
    p_blk.set_defaults(func=cmd_block)

    p_rs = sub.add_parser(
        "resume",
        help="从受阻恢复到 resume_point（可用 --to 覆盖；Lite L3）",
    )
    _add_task_selectors(p_rs)
    p_rs.add_argument(
        "--to",
        default=None,
        choices=sorted(RESUME_POINTS),
        help="覆盖存储的 resume_point（须合法）",
    )
    p_rs.add_argument("--actor", default="chief", help="写入 history 的 actor")
    p_rs.add_argument(
        "--clear-blocker-code",
        default=None,
        help="恢复时按 code 清除对应 blockers 项",
    )
    p_rs.add_argument(
        "--no-budget-block",
        action="store_true",
        help="恢复到执行中时预算违规直接拒绝（不追加 blockers）",
    )
    p_rs.add_argument(
        "--skip-reconcile",
        action="store_true",
        help="跳过 Lite-C 租约/Git 对账（仅排障；默认对账）",
    )
    p_rs.set_defaults(func=cmd_resume)

    # ---- Lite L4 budget ----
    p_sb = sub.add_parser("set-budget", help="设置预算硬门（Lite L4）")
    _add_task_selectors(p_sb)
    p_sb.add_argument("--max-attempts", type=int, default=None)
    p_sb.add_argument("--max-duration-sec", type=int, default=None)
    p_sb.add_argument("--max-tokens", type=int, default=None)
    p_sb.add_argument(
        "--allow-raise",
        action="store_true",
        help="允许抬高已有 max_*（须幕僚长确认）",
    )
    p_sb.add_argument("--actor", default="chief")
    p_sb.set_defaults(func=cmd_set_budget)

    p_cb = sub.add_parser("check-budget", help="评估预算（不改状态；Lite L4）")
    _add_task_selectors(p_cb)
    p_cb.add_argument(
        "--pending-attempt",
        action="store_true",
        help="按即将进入执行中（attempts+1）评估",
    )
    p_cb.set_defaults(func=cmd_check_budget)

    p_rt = sub.add_parser("record-tokens", help="累加 tokens_used（Lite L4）")
    _add_task_selectors(p_rt)
    p_rt.add_argument("--tokens", type=int, required=True)
    p_rt.add_argument("--actor", default="developer")
    p_rt.set_defaults(func=cmd_record_tokens)

    # ---- Lite L5 lessons ----
    p_la = sub.add_parser("lesson-add", help="提名经验候选（Lite L5 / T4 scope+probe）")
    _add_task_selectors(p_la)
    p_la.add_argument("--id", required=True, help="lesson id")
    p_la.add_argument("--summary", required=True)
    p_la.add_argument("--rule-body", default=None, help="规则正文（可选）")
    p_la.add_argument("--rule-file", default=None, help="从文件读规则正文")
    p_la.add_argument("--rule-path", default=None, help="拟发布规则相对路径")
    p_la.add_argument("--tag", action="append", default=None)
    p_la.add_argument("--actor", default="developer")
    p_la.add_argument("--scope-json", default=None, help='适用范围 JSON，如 {"task_kind":"fix"}')
    p_la.add_argument("--applies-to", default=None, help="适用范围简写（task_kind 字符串）")
    p_la.add_argument("--probe", default=None, help="探针描述/命令（非空）")
    p_la.add_argument("--probe-ref", default=None, help="探针引用 id")
    p_la.add_argument("--probe-json", default=None, help="探针 JSON（ref/description/expected）")
    p_la.set_defaults(func=cmd_lesson_add)

    p_lr = sub.add_parser("lesson-review", help="审核经验候选 approve|reject（T4：approve 须探针证据）")
    _add_task_selectors(p_lr)
    p_lr.add_argument("--id", required=True)
    p_lr.add_argument("--verdict", required=True, choices=["approve", "reject"])
    p_lr.add_argument("--notes", default=None)
    p_lr.add_argument("--actor", default="verifier")
    p_lr.add_argument(
        "--probe-result-json",
        default=None,
        help='批准必填：{"probe_id":"...","passed":true,"stdout_summary":"...","at":"..."}',
    )
    p_lr.add_argument("--evidence-json", default=None, help="等同 --probe-result-json")
    p_lr.set_defaults(func=cmd_lesson_review)

    p_lp = sub.add_parser("lesson-publish", help="发布已批准经验到 store（Lite L5 / T4 版本一致）")
    _add_task_selectors(p_lp)
    p_lp.add_argument("--id", required=True)
    p_lp.add_argument("--actor", default="chief")
    p_lp.add_argument(
        "--no-write-rule",
        action="store_true",
        help="只写 store，不落 rules/*.md",
    )
    p_lp.set_defaults(func=cmd_lesson_publish)

    p_ll = sub.add_parser("lesson-list", help="列出 task 内 lessons 或 store（Lite L5）")
    _add_task_selectors(p_ll)
    p_ll.set_defaults(func=cmd_lesson_list)

    p_ls = sub.add_parser("lesson-show", help="读取 store 中已发布经验（Lite L5）")
    p_ls.add_argument("--root", required=True)
    p_ls.add_argument("--id", required=True)
    p_ls.set_defaults(func=cmd_lesson_show)

    p_lrl = sub.add_parser("lesson-rule-load", help="Eng 加载规则回执（T4）")
    _add_task_selectors(p_lrl)
    p_lrl.add_argument("--team-id", default=None)
    p_lrl.add_argument("--id", required=True, help="lesson id")
    p_lrl.add_argument("--eng", required=True)
    p_lrl.add_argument("--rules-version", required=True)
    p_lrl.add_argument("--actor", default="Eng-A")
    p_lrl.set_defaults(func=cmd_lesson_rule_load)

    p_lrr = sub.add_parser("lesson-rule-receive", help="Developer 接收规则回执（T4）")
    _add_task_selectors(p_lrr)
    p_lrr.add_argument("--team-id", default=None)
    p_lrr.add_argument("--id", required=True, help="lesson id")
    p_lrr.add_argument("--developer", required=True)
    p_lrr.add_argument("--rules-version", required=True)
    p_lrr.add_argument("--handoff-id", default=None)
    p_lrr.add_argument("--actor", default="developer")
    p_lrr.set_defaults(func=cmd_lesson_rule_receive)

    p_lrec = sub.add_parser("lesson-recurrence", help="已发布经验防复发探针记录（T4）")
    _add_task_selectors(p_lrec)
    p_lrec.add_argument("--team-id", default=None)
    p_lrec.add_argument("--id", required=True, help="lesson id")
    p_lrec.add_argument("--probe-result-json", required=True)
    p_lrec.add_argument("--actor", default="verifier")
    p_lrec.set_defaults(func=cmd_lesson_recurrence)


    # ---- Team dual-task ----
    p_tc = sub.add_parser("team-create", help="创建 Team run（Nancy/Matcha）")
    p_tc.add_argument("--root", required=True)
    p_tc.add_argument("--team-id", required=True)
    p_tc.add_argument("--title", required=True)
    p_tc.add_argument("--requester", default="user")
    p_tc.add_argument("--eng-stub", action="append", default=None, help="Eng 协调者名（字段名 eng_stubs 兼容保留；可多次）")
    p_tc.add_argument("--force", action="store_true")
    p_tc.set_defaults(func=cmd_team_create)

    p_ta = sub.add_parser("team-add-task", help="在 Team 下新增子任务（双任务）")
    p_ta.add_argument("--root", required=True)
    p_ta.add_argument("--team-id", required=True)
    p_ta.add_argument("--task-id", required=True)
    p_ta.add_argument("--title", required=True)
    p_ta.add_argument("--role", default="worker")
    p_ta.add_argument("--actor", default="Matcha")
    p_ta.add_argument(
        "--parent-task-id",
        default=None,
        help="可选顶层 parent_task_id（勿塞进 team 对象）",
    )
    p_ta.add_argument("--force", action="store_true")
    p_ta.set_defaults(func=cmd_team_add_task)

    p_as = sub.add_parser("team-assign", help="Matcha 指派 Eng 工作包（可带依赖/负载检查）")
    p_as.add_argument("--root", required=True)
    p_as.add_argument("--team-id", required=True)
    p_as.add_argument("--task-id", required=True)
    p_as.add_argument("--assignee", required=True)
    p_as.add_argument("--assignee-role", default="eng_stub")
    p_as.add_argument("--actor", default="Matcha")
    p_as.add_argument("--note", default=None)
    p_as.add_argument(
        "--depends-on",
        action="append",
        default=None,
        help="跨工作包依赖 task_id（可多次）",
    )
    p_as.set_defaults(func=cmd_team_assign)

    p_su = sub.add_parser("team-summarize", help="Nancy 汇总双任务进度")
    p_su.add_argument("--root", required=True)
    p_su.add_argument("--team-id", required=True)
    p_su.add_argument("--actor", default="Nancy")
    p_su.add_argument("--note", default=None)
    p_su.set_defaults(func=cmd_team_summarize)

    p_ts = sub.add_parser("team-status", help="打印 Team 状态 JSON")
    p_ts.add_argument("--root", required=True)
    p_ts.add_argument("--team-id", required=True)
    p_ts.add_argument(
        "--actor",
        default=None,
        help="可选；若提供则按角色白名单硬拦（Nancy/Matcha 可 status）",
    )
    p_ts.set_defaults(func=cmd_team_status)

    p_en = sub.add_parser("team-eng-note", help="Eng 写状态备注（硬拦；结构化拆解用 team-eng-decompose）")
    p_en.add_argument("--root", required=True)
    p_en.add_argument("--team-id", required=True)
    p_en.add_argument("--task-id", required=True)
    p_en.add_argument("--actor", required=True, help="必须是 eng_stubs 之一")
    p_en.add_argument("--note", required=True)
    p_en.set_defaults(func=cmd_team_eng_note)

    # ---- Team T2 handoff / decompose ----
    p_ed = sub.add_parser("team-eng-decompose", help="Eng 写入拆解包并替换占位验收（T2）")
    p_ed.add_argument("--root", required=True)
    p_ed.add_argument("--team-id", required=True)
    p_ed.add_argument("--task-id", required=True)
    p_ed.add_argument("--actor", required=True)
    p_ed.add_argument("--goal", required=True)
    p_ed.add_argument("--in-scope", action="append", default=None)
    p_ed.add_argument("--out-of-scope", action="append", default=None)
    p_ed.add_argument("--acceptance-json", required=True)
    p_ed.add_argument("--worktree", default=None)
    p_ed.add_argument("--note", default=None)
    p_ed.set_defaults(func=cmd_team_eng_decompose)

    p_ho = sub.add_parser("team-handoff", help="Eng→Developer 持久化 handoff（T2）")
    p_ho.add_argument("--root", required=True)
    p_ho.add_argument("--team-id", required=True)
    p_ho.add_argument("--task-id", required=True)
    p_ho.add_argument("--actor", required=True)
    p_ho.add_argument("--developer", default="developer")
    p_ho.add_argument("--worktree", default=None)
    p_ho.add_argument("--rules-version", default=None)
    p_ho.add_argument("--parent-task-id", default=None)
    p_ho.add_argument("--note", default=None)
    p_ho.add_argument("--mode", default="local", choices=["local", "simulated", "omb"])
    p_ho.set_defaults(func=cmd_team_handoff)

    p_ak = sub.add_parser("team-ack-handoff", help="Developer 接单回执（T2）")
    p_ak.add_argument("--root", required=True)
    p_ak.add_argument("--team-id", required=True)
    p_ak.add_argument("--handoff-id", required=True)
    p_ak.add_argument("--actor", default="developer")
    p_ak.add_argument("--role", default="developer")
    p_ak.add_argument("--run-id", default=None)
    p_ak.set_defaults(func=cmd_team_ack_handoff)

    p_hs = sub.add_parser("team-handoff-status", help="更新 handoff 状态（T2）")
    p_hs.add_argument("--root", required=True)
    p_hs.add_argument("--team-id", required=True)
    p_hs.add_argument("--handoff-id", required=True)
    p_hs.add_argument(
        "--status",
        required=True,
        choices=["proposed", "acked", "in_progress", "pending_verify", "rework", "done", "blocked"],
    )
    p_hs.add_argument("--actor", required=True)
    p_hs.add_argument("--note", default=None)
    p_hs.set_defaults(func=cmd_team_handoff_status)

    p_rw = sub.add_parser("team-rework", help="验证失败回流原 Eng（T2）")
    p_rw.add_argument("--root", required=True)
    p_rw.add_argument("--team-id", required=True)
    p_rw.add_argument("--task-id", required=True)
    p_rw.add_argument("--actor", required=True)
    p_rw.add_argument("--reason", required=True)
    p_rw.add_argument("--developer", default=None)
    p_rw.set_defaults(func=cmd_team_rework)

    p_es = sub.add_parser("team-escalate-scope", help="范围/依赖变更升级 Matcha/chief（T2）")
    p_es.add_argument("--root", required=True)
    p_es.add_argument("--team-id", required=True)
    p_es.add_argument("--task-id", required=True)
    p_es.add_argument("--actor", required=True)
    p_es.add_argument("--reason", required=True)
    p_es.add_argument("--to", default="matcha", choices=["matcha", "chief"])
    p_es.set_defaults(func=cmd_team_escalate_scope)

    p_od = sub.add_parser("team-omb-delegate", help="尝试 OMB 多助手委派（当前恒 blocked/simulated）（T2）")
    p_od.add_argument("--root", required=True)
    p_od.add_argument("--team-id", required=True)
    p_od.add_argument("--handoff-id", required=True)
    p_od.add_argument("--actor", default="system")
    p_od.set_defaults(func=cmd_team_omb_delegate)

    p_rcm = sub.add_parser("team-record-commit", help="记录本地/mock Developer commit 到 handoff（T2）")
    p_rcm.add_argument("--root", required=True)
    p_rcm.add_argument("--team-id", required=True)
    p_rcm.add_argument("--task-id", required=True)
    p_rcm.add_argument("--handoff-id", required=True)
    p_rcm.add_argument("--commit", required=True)
    p_rcm.add_argument("--actor", default="developer")
    p_rcm.set_defaults(func=cmd_team_record_commit)

    p_sd = sub.add_parser("team-set-deps", help="Matcha 设置跨工作包依赖（T2）")
    p_sd.add_argument("--root", required=True)
    p_sd.add_argument("--team-id", required=True)
    p_sd.add_argument("--task-id", required=True)
    p_sd.add_argument("--depends-on", action="append", default=None)
    p_sd.add_argument("--actor", default="Matcha")
    p_sd.set_defaults(func=cmd_team_set_deps)

    # ---- Team T3 Nancy todos / blocker resolve ----
    p_tadd = sub.add_parser("team-todo-add", help="Nancy 持久化待办（T3；写入 team.json）")
    p_tadd.add_argument("--root", required=True)
    p_tadd.add_argument("--team-id", required=True)
    p_tadd.add_argument("--text", required=True)
    p_tadd.add_argument("--actor", default="Nancy")
    p_tadd.add_argument("--source", default="nancy")
    p_tadd.add_argument("--owner", default=None)
    p_tadd.add_argument("--linked-task-id", default=None)
    p_tadd.add_argument("--todo-id", default=None)
    p_tadd.set_defaults(func=cmd_team_todo_add)

    p_tdone = sub.add_parser(
        "team-todo-done",
        help="Nancy 勾销/升级待办（T3；done 须 --done-basis）",
    )
    p_tdone.add_argument("--root", required=True)
    p_tdone.add_argument("--team-id", required=True)
    p_tdone.add_argument("--todo-id", required=True)
    p_tdone.add_argument("--actor", default="Nancy")
    p_tdone.add_argument(
        "--done-basis",
        default=None,
        help="user_confirmed | chief_confirmed | linked_task_completed:<id>",
    )
    p_tdone.add_argument("--evidence", default=None)
    p_tdone.add_argument(
        "--status",
        default="done",
        choices=["done", "escalated", "open"],
    )
    p_tdone.set_defaults(func=cmd_team_todo_done)

    p_tlist = sub.add_parser("team-todo-list", help="列出 Team 持久待办（T3）")
    p_tlist.add_argument("--root", required=True)
    p_tlist.add_argument("--team-id", required=True)
    p_tlist.add_argument("--actor", default="Nancy")
    p_tlist.add_argument("--status", default=None, choices=["open", "done", "escalated"])
    p_tlist.set_defaults(func=cmd_team_todo_list)

    p_br = sub.add_parser(
        "team-blocker-resolve",
        help="解除 blockers_escalated 中 open 项（T3；解除后不再报警）",
    )
    p_br.add_argument("--root", required=True)
    p_br.add_argument("--team-id", required=True)
    p_br.add_argument("--task-id", required=True)
    p_br.add_argument("--reason-code", default=None)
    p_br.add_argument("--actor", default="Nancy")
    p_br.add_argument("--note", default=None)
    p_br.set_defaults(func=cmd_team_blocker_resolve)

    p_pwt = sub.add_parser(
        "prepare-worktree",
        help="创建/校验真实 Git worktree（Lite-C L5）",
    )
    _add_task_selectors(p_pwt)
    p_pwt.add_argument("--base-repo", default=None, help="git worktree 的基仓库；默认识别 --root 或自举 seed")
    p_pwt.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="禁止在无 git 根时自举 runs/<id>/_seed_repo",
    )
    p_pwt.set_defaults(func=cmd_prepare_worktree)

    p_cancel = sub.add_parser(
        "cancel",
        help="取消任务：→已取消并请求停止租约（Lite-C L5；不宣称 OS 杀进程已验收）",
    )
    _add_task_selectors(p_cancel)
    p_cancel.add_argument("--actor", default="chief")
    p_cancel.add_argument("--reason", default=None)
    p_cancel.add_argument(
        "--no-signal",
        action="store_true",
        help="只写 cancel_requested，不发 SIGTERM",
    )
    p_cancel.set_defaults(func=cmd_cancel)

    p_lease = sub.add_parser(
        "acquire-lease",
        help="登记执行器租约（Lite-C；协议层）",
    )
    _add_task_selectors(p_lease)
    p_lease.add_argument("--holder", required=True)
    p_lease.add_argument("--pid", type=int, default=None)
    p_lease.add_argument("--note", default=None)
    p_lease.set_defaults(func=cmd_acquire_lease)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
