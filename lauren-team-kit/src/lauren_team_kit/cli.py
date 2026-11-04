"""CLI for lauren-team-kit: create, transition, block, resume, validate, …"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lauren_team_kit import __version__
from lauren_team_kit.evidence import ensure_evidence_dir
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    record_check,
    resolve_task_file,
    save_task,
    transition_task,
    validate_task,
)
from lauren_team_kit.resume import (
    RESUME_POINTS,
    BlockResumeError,
    block_task,
    resume_task,
)
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
    list_store,
    load_from_store,
    publish_candidate,
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
    assign_task,
    create_team,
    eng_status_note,
    summarize_team,
    team_path_for,
    team_status,
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
    """Leave 受阻 toward stored or overridden resume_point (Lite L3)."""
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    if args.to is not None and args.to not in RESUME_POINTS:
        print(
            f"非法 --to: {args.to!r}；允许: {', '.join(sorted(RESUME_POINTS))}",
            file=sys.stderr,
        )
        return 2
    task = load_task(path)
    try:
        updated, report = resume_task(
            task,
            actor=args.actor,
            to_status=args.to,
            clear_blocker_code=args.clear_blocker_code,
        )
    except BlockResumeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except IllegalTransitionError as e:
        print(str(e), file=sys.stderr)
        return 1
    if report.get("action") == "resumed":
        save_task(path, updated)
    report_out = {
        **report,
        "task_file": str(path),
        "status": updated.get("status"),
    }
    print(json.dumps(report_out, ensure_ascii=False, indent=2))
    if report.get("already_have_artifact"):
        print("already_have_artifact=true（勿重复提交）")
    print(
        f"resume {path}: {report.get('from_status')} → {updated.get('status')} "
        f"(action={report.get('action')})"
    )
    return 0


def cmd_record_check(args: argparse.Namespace) -> int:
    path = _resolve_or_exit(args)
    if isinstance(path, int):
        return path
    if not path.is_file():
        print(f"找不到 task: {path}", file=sys.stderr)
        return 1
    task = load_task(path)
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
    )
    save_task(path, updated)
    print(
        f"recorded check acceptance_id={args.acceptance_id} "
        f"executed={args.executed} result={updated.get('verification', {}).get('result')}"
    )
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
    try:
        updated = add_candidate(
            task,
            lesson_id=args.id,
            summary=args.summary,
            actor=args.actor,
            rule_body=rule_body,
            proposed_rule_path=args.rule_path,
            tags=args.tag,
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
    try:
        updated = review_candidate(
            task,
            args.id,
            approved=approved,
            actor=args.actor,
            notes=args.notes,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lauren-team-kit",
        description="Lauren 任务协议 CLI（create / transition / validate / …）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

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

    p_mp = sub.add_parser("merge-precheck", help="合并前本地 Git 预检（不执行 merge）")
    _add_task_selectors(p_mp)
    p_mp.set_defaults(func=cmd_merge_precheck)

    p_rc = sub.add_parser("record-check", help="写入/更新 verification.checks 与 commits")
    _add_task_selectors(p_rc)
    p_rc.add_argument("--acceptance-id", required=True)
    p_rc.add_argument("--executed", type=_parse_bool, required=True)
    p_rc.add_argument("--exit-code", type=int, default=None)
    p_rc.add_argument("--bound-commit", default=None)
    p_rc.add_argument("--artifact-commit", default=None)
    p_rc.add_argument("--result", default=None, choices=["pass", "fail", "inconclusive"])
    p_rc.add_argument("--log-path", default=None)
    p_rc.add_argument("--notes", default=None)
    p_rc.set_defaults(func=cmd_record_check)


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
    p_la = sub.add_parser("lesson-add", help="提名经验候选（Lite L5）")
    _add_task_selectors(p_la)
    p_la.add_argument("--id", required=True, help="lesson id")
    p_la.add_argument("--summary", required=True)
    p_la.add_argument("--rule-body", default=None, help="规则正文（可选）")
    p_la.add_argument("--rule-file", default=None, help="从文件读规则正文")
    p_la.add_argument("--rule-path", default=None, help="拟发布规则相对路径")
    p_la.add_argument("--tag", action="append", default=None)
    p_la.add_argument("--actor", default="developer")
    p_la.set_defaults(func=cmd_lesson_add)

    p_lr = sub.add_parser("lesson-review", help="审核经验候选 approve|reject（Lite L5）")
    _add_task_selectors(p_lr)
    p_lr.add_argument("--id", required=True)
    p_lr.add_argument("--verdict", required=True, choices=["approve", "reject"])
    p_lr.add_argument("--notes", default=None)
    p_lr.add_argument("--actor", default="verifier")
    p_lr.set_defaults(func=cmd_lesson_review)

    p_lp = sub.add_parser("lesson-publish", help="发布已批准经验到 store（Lite L5）")
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


    # ---- Team v0.2 dual-task ----
    p_tc = sub.add_parser("team-create", help="创建 Team v0.2 run（Nancy/Matcha）")
    p_tc.add_argument("--root", required=True)
    p_tc.add_argument("--team-id", required=True)
    p_tc.add_argument("--title", required=True)
    p_tc.add_argument("--requester", default="user")
    p_tc.add_argument("--eng-stub", action="append", default=None, help="Eng stub 名（可多次）")
    p_tc.add_argument("--force", action="store_true")
    p_tc.set_defaults(func=cmd_team_create)

    p_ta = sub.add_parser("team-add-task", help="在 Team 下新增子任务（双任务）")
    p_ta.add_argument("--root", required=True)
    p_ta.add_argument("--team-id", required=True)
    p_ta.add_argument("--task-id", required=True)
    p_ta.add_argument("--title", required=True)
    p_ta.add_argument("--role", default="worker")
    p_ta.add_argument("--actor", default="Matcha")
    p_ta.add_argument("--force", action="store_true")
    p_ta.set_defaults(func=cmd_team_add_task)

    p_as = sub.add_parser("team-assign", help="Matcha 指派/跟踪 Eng（stub）")
    p_as.add_argument("--root", required=True)
    p_as.add_argument("--team-id", required=True)
    p_as.add_argument("--task-id", required=True)
    p_as.add_argument("--assignee", required=True)
    p_as.add_argument("--assignee-role", default="eng_stub")
    p_as.add_argument("--actor", default="Matcha")
    p_as.add_argument("--note", default=None)
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

    p_en = sub.add_parser("team-eng-note", help="Eng stub 仅写状态备注（硬拦）")
    p_en.add_argument("--root", required=True)
    p_en.add_argument("--team-id", required=True)
    p_en.add_argument("--task-id", required=True)
    p_en.add_argument("--actor", required=True, help="必须是 eng_stubs 之一")
    p_en.add_argument("--note", required=True)
    p_en.set_defaults(func=cmd_team_eng_note)


    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
