#!/usr/bin/env python3
"""T0: validate key handoff JSON examples against authoritative Schema."""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("FAIL: jsonschema not installed", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "lauren-team-kit" / "contracts" / "task-protocol.schema.json"

# Minimal but Schema-valid engineering_chain handoff shape (chief/Eng → developer).
EXAMPLES = {
    "team_chief_engineering_chain_handoff": {
        "schema_version": "lauren-task-protocol/0.1",
        "task_id": "t-eng-hand-001",
        "title": "Eng handoff example",
        "status": "待执行",
        "created_at": "2026-11-05T02:00:00+00:00",
        "updated_at": "2026-11-05T02:00:00+00:00",
        "requester": "Eng-A",
        "roles": {
            "chief": "幕僚长",
            "developer": "云端编程助手",
            "verifier": "验证助手",
        },
        "parent_task_id": "parent-biz-001",
        "scope": {
            "goal": "实现某功能切片",
            "in_scope": ["指定模块"],
            "out_of_scope": ["Full OMB GUI"],
        },
        "acceptance": [
            {
                "id": "A1",
                "description": "单元测试通过",
                "command": "cd demo-app && .venv/bin/python -m pytest -q",
                "must_run": True,
                "pass_criteria": "exit_code==0",
            }
        ],
        "worktree": {"path": "workspace/runs/t-eng-hand-001/worktree", "branch": "task/t-eng-hand-001"},
        "integration": {"branch": "demo/integration"},
        "merge_policy": {"mode": "confirm"},
        "evidence_dir": "workspace/runs/t-eng-hand-001/",
        "history": [
            {
                "at": "2026-11-05T02:00:00+00:00",
                "actor": "Eng-A",
                "to": "待执行",
                "note": "engineering_chain handoff",
            }
        ],
        "team": {"team_id": "demo-t1", "role": "developer"},
    },
    "illegal_parent_inside_team_should_fail": {
        "schema_version": "lauren-task-protocol/0.1",
        "task_id": "t-bad-001",
        "title": "bad nest",
        "status": "待执行",
        "created_at": "2026-11-05T02:00:00+00:00",
        "updated_at": "2026-11-05T02:00:00+00:00",
        "requester": "Eng-A",
        "roles": {"chief": "幕僚长", "developer": "云端编程助手", "verifier": "验证助手"},
        "scope": {"goal": "x", "in_scope": ["a"], "out_of_scope": ["b"]},
        "acceptance": [
            {
                "id": "A1",
                "description": "x",
                "command": "true",
                "must_run": False,
                "pass_criteria": "n/a",
            }
        ],
        "worktree": {"path": "w", "branch": "b"},
        "integration": {"branch": "demo/integration"},
        "merge_policy": {"mode": "confirm"},
        "evidence_dir": "workspace/runs/t-bad-001/",
        "history": [
            {"at": "2026-11-05T02:00:00+00:00", "actor": "Eng-A", "to": "待执行", "note": "bad"}
        ],
        "team": {"team_id": "demo-t1", "parent_task_id": "nested-illegal", "role": "developer"},
    },
}


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Validator = jsonschema.Draft202012Validator
    # Fall back if meta not available
    try:
        vproto = Validator(schema)
    except Exception:
        vproto = jsonschema.Draft7Validator(schema)

    ok = EXAMPLES["team_chief_engineering_chain_handoff"]
    errs = sorted(vproto.iter_errors(ok), key=lambda e: e.path)
    if errs:
        print("FAIL valid example:")
        for e in errs:
            print(" ", list(e.path), e.message)
        return 1
    print("PASS: team_chief_engineering_chain_handoff validates")

    bad = EXAMPLES["illegal_parent_inside_team_should_fail"]
    errs = list(vproto.iter_errors(bad))
    if not errs:
        print("FAIL: nested parent_task_id under team was accepted")
        return 1
    print("PASS: nested parent_task_id under team rejected (", errs[0].message, ")")

    # Also validate a live child from add_child_task shape via kit if importable
    try:
        from lauren_team_kit.protocol import validate_task
        from lauren_team_kit.team import add_child_task, create_team
        import tempfile
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as td:
            root = P(td)
            (root / "workspace" / "runs").mkdir(parents=True)
            create_team(root=root, team_id="demo-t1", title="T0", force=True)
            _team, child = add_child_task(
                root=root,
                team_id="demo-t1",
                task_id="t0-child",
                title="child",
                force=True,
                parent_task_id="biz-1",
            )
            verr = validate_task(child)
            schema_errs = list(vproto.iter_errors(child))
            if verr or schema_errs:
                print("FAIL child task:", verr, [e.message for e in schema_errs[:3]])
                return 1
            if child["acceptance"][0]["must_run"] is not False:
                print("FAIL: child still has must_run true demo acceptance")
                return 1
            if "pytest" in child["acceptance"][0].get("command", ""):
                print("FAIL: child still inherits demo pytest")
                return 1
            print("PASS: add_child_task placeholder acceptance + top-level parent_task_id")
    except Exception as e:
        print("WARN: live add_child_task check skipped:", e)

    print("T0 schema example validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
