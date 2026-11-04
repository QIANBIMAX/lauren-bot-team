"""CLI for lauren-team-kit: create, transition, validate, verify-gate, …"""

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
    try:
        updated = transition_task(
            task, to_status=args.to, actor=args.actor, note=args.note
        )
    except IllegalTransitionError as e:
        print(str(e), file=sys.stderr)
        return 1
    except VerifyGateError as e:
        print(str(e), file=sys.stderr)
        return 1
    save_task(path, updated)
    print(f"transitioned {path}: {prev} → {args.to} (actor={args.actor})")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
