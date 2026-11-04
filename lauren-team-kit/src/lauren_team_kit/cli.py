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
    status = task.get("status")
    checklist: list[dict[str, Any]] = []
    ok = True

    status_ok = status in ("验证通过", "待合并")
    checklist.append(
        {
            "item": "status_in_验证通过_or_待合并",
            "ok": status_ok,
            "detail": f"status={status!r}",
        }
    )
    if not status_ok:
        ok = False

    mp = task.get("merge_policy")
    mode_ok = isinstance(mp, dict) and isinstance(mp.get("mode"), str) and bool(mp.get("mode"))
    checklist.append(
        {
            "item": "merge_policy.mode",
            "ok": mode_ok,
            "detail": None if not isinstance(mp, dict) else mp.get("mode"),
        }
    )
    if not mode_ok:
        ok = False

    art = task.get("artifact") if isinstance(task.get("artifact"), dict) else {}
    ver = task.get("verification") if isinstance(task.get("verification"), dict) else {}
    commit = art.get("commit") or ver.get("bound_commit")
    commit_ok = isinstance(commit, str) and bool(commit.strip())
    checklist.append(
        {
            "item": "commit_present",
            "ok": commit_ok,
            "detail": commit if commit_ok else None,
        }
    )
    if not commit_ok:
        ok = False

    ev_rel = task.get("evidence_dir")
    root = Path(args.root).resolve() if args.root else path.parent.parent.parent.parent
    # path = root/workspace/runs/id/task.json → parents[3]=root when structure matches
    if args.root:
        root = Path(args.root).resolve()
    else:
        # task.json → runs/id → runs → workspace → root
        root = path.parent.parent.parent.parent
    ev_path = None
    if isinstance(ev_rel, str) and ev_rel:
        ev_path = (root / ev_rel).resolve()
    else:
        ev_path = path.parent
    ev_ok = ev_path.is_dir()
    checklist.append(
        {
            "item": "evidence_dir_exists",
            "ok": ev_ok,
            "detail": str(ev_path),
        }
    )
    if not ev_ok:
        ok = False

    report = {
        "task_id": task.get("task_id"),
        "status": status,
        "ok": ok,
        "checklist": checklist,
        "note": "占位：不执行真实 merge",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if ok:
        print("PASS merge-precheck")
        return 0
    print("FAIL merge-precheck", file=sys.stderr)
    return 1


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

    p_mp = sub.add_parser("merge-precheck", help="合并前占位检查（不真实 merge）")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    # late import for type hint used in merge-precheck local
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
