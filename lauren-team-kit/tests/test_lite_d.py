"""Lite-D (L7/L8): lessons examples+load receipts; fail→fix→reverify→real merge.

L7 baseline already covered by T4 / test_lessons (probe approve, publish version
align, record_rule_load/receive, anti-recurrence). This module only fills the
remaining gap: positive/negative examples on candidates + subsequent-task load
traceability; and L8's clean-env real-commit closed loop (not placeholder C2/C3).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lauren_team_kit.lessons import (
    LessonError,
    add_candidate,
    load_from_store,
    publish_candidate,
    record_rule_load,
    record_rule_receive,
    review_candidate,
)
from lauren_team_kit.merge import execute_merge
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    record_check,
    save_task,
    set_artifact_commit,
    transition_task,
)
from lauren_team_kit.verify_gate import evaluate_verify_gate


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip()


def _init_feature_repo(repo: Path) -> tuple[str, str]:
    """baseline on demo/integration + feature commit with hello.txt."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "lite-d@example.com")
    _git(repo, "config", "user.name", "LiteD")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    try:
        _git(repo, "branch", "-M", "main")
    except subprocess.CalledProcessError:
        pass
    baseline = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "demo/integration", baseline)
    _git(repo, "checkout", "-b", "feature/lite-d")
    (repo / "hello.txt").write_text("ping\n", encoding="utf-8")
    _git(repo, "add", "hello.txt")
    _git(repo, "commit", "-m", "feat: hello")
    feature = _git(repo, "rev-parse", "HEAD")
    return baseline, feature


RULE = """# lite-d-empty-guard

空输入必须返回 []，不得抛异常。
"""

PROBE = {"ref": "empty-query-probe", "description": "assert empty → []", "expected": "[]"}
EVIDENCE = {
    "probe_id": "empty-query-probe",
    "passed": True,
    "stdout_summary": "[]",
    "evidence": "checks/empty-probe.log",
    "at": "2026-11-05T14:00:00+08:00",
}


def test_l7_examples_and_subsequent_load_receipt(tmp_path: Path):
    """正反样例写入 store；后续任务 load/receive 回执可追溯版本+样例。"""
    root = tmp_path / "delivery"
    (root / "lauren-team-kit" / "rules").mkdir(parents=True)
    (root / "lauren-team-kit" / "lessons" / "store").mkdir(parents=True)

    create_task(title="L7 source", task_id="lite-d-src", root=root)
    path = root / "workspace" / "runs" / "lite-d-src" / "task.json"
    task = load_task(path)

    with pytest.raises(LessonError, match="positive|negative|examples"):
        add_candidate(
            task,
            lesson_id="lite-d-empty-guard",
            summary="空输入必须返回 []",
            actor="developer",
            rule_body=RULE,
            scope={"task_kind": "filter"},
            probe=PROBE,
            examples={"positive": [], "negative": []},
        )

    task = add_candidate(
        task,
        lesson_id="lite-d-empty-guard",
        summary="空输入必须返回 []",
        actor="developer",
        rule_body=RULE,
        scope={"task_kind": "filter", "path_glob": "demo-app/**"},
        probe=PROBE,
        examples={
            "positive": ["filter('') == []", "filter(None) == []"],
            "negative": ["filter('') raises", "filter('') returns None"],
        },
        source_failure="round1 empty-query threw instead of []",
    )
    cand = task["lessons"]["candidates"][0]
    assert cand["examples"]["positive"][0].startswith("filter")
    assert cand["examples"]["negative"]
    assert "threw" in cand["source_failure"]
    save_task(path, task)

    task = review_candidate(
        task,
        "lite-d-empty-guard",
        approved=True,
        actor="verifier",
        notes="probe ok",
        probe_result=EVIDENCE,
    )
    task, record = publish_candidate(
        task, "lite-d-empty-guard", root=root, actor="chief"
    )
    save_task(path, task)

    loaded = load_from_store(root, "lite-d-empty-guard")
    assert loaded["rules_version"] == record["rules_version"]
    assert loaded["examples"]["positive"] == [
        "filter('') == []",
        "filter(None) == []",
    ]
    assert loaded["examples"]["negative"]
    assert loaded.get("source_failure")

    # Subsequent task: load + receive receipts with same version
    create_task(title="L7 follow-on", task_id="lite-d-next", root=root)
    path2 = root / "workspace" / "runs" / "lite-d-next" / "task.json"
    follow = load_task(path2)
    follow = record_rule_load(
        follow,
        eng="chief",
        lesson_id="lite-d-empty-guard",
        rules_version=record["rules_version"],
        actor="chief",
    )
    follow = record_rule_receive(
        follow,
        developer="developer",
        lesson_id="lite-d-empty-guard",
        rules_version=record["rules_version"],
        actor="developer",
    )
    save_task(path2, follow)
    receipts = follow["rule_receipts"]
    assert any(
        r.get("kind") == "load" and r.get("rules_version") == record["rules_version"]
        for r in receipts
    )
    assert any(
        r.get("kind") == "receive" and r.get("rules_version") == record["rules_version"]
        for r in receipts
    )
    again = load_from_store(root, "lite-d-empty-guard")
    assert again["examples"]["positive"]
    assert again["content_hash"] == record["content_hash"]


def test_l8_fail_fix_reverify_real_merge(tmp_path: Path):
    """干净环境：首轮失败→需修改→修复新 attempt→真 Git commit 再验→confirm 合并。"""
    root = tmp_path
    task_id = "lite-d-loop"
    create_task(title="Lite-D closed loop", task_id=task_id, root=root)
    path = root / "workspace" / "runs" / task_id / "task.json"
    task = load_task(path)

    wt = root / "workspace" / "runs" / task_id / "worktree"
    _, feature = _init_feature_repo(wt)
    rel_wt = str(wt.relative_to(root))
    task["worktree"] = {"path": rel_wt, "branch": "feature/lite-d"}
    save_task(path, task)

    # Round 1: fail check → 需修改
    task = transition_task(task, to_status="执行中", actor="chief")
    bad = "0" * 40
    task = set_artifact_commit(task, commit=bad, actor="developer", role="developer")
    task = transition_task(task, to_status="待验证", actor="developer")
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=1,
        bound_commit=bad,
        result="fail",
        actor="verifier",
        role="verifier",
        log_path=str(root / "round1-fail.log"),
        new_round=True,
        notes="round1 intentional fail",
    )
    save_task(path, task)
    errs = evaluate_verify_gate(task)
    assert errs, f"round1 must fail gate, got {errs!r}"
    task = transition_task(task, to_status="需修改", actor="verifier")
    save_task(path, task)
    assert task["status"] == "需修改"
    round1_id = (task.get("verification") or {}).get("round_id")

    # Round 2: real feature commit → pass → merge
    task = transition_task(task, to_status="执行中", actor="developer")
    task = set_artifact_commit(
        task, commit=feature, actor="developer", role="developer"
    )
    task = transition_task(task, to_status="待验证", actor="developer")
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit=feature,
        result="pass",
        actor="verifier",
        role="verifier",
        log_path=str(root / "round2-pass.log"),
        new_round=True,
        notes="round2 fixed real commit",
    )
    save_task(path, task)
    round2_id = (task.get("verification") or {}).get("round_id")
    assert round2_id and round2_id != round1_id
    assert evaluate_verify_gate(task) == []

    task = transition_task(task, to_status="验证通过", actor="verifier")
    task = transition_task(task, to_status="待合并", actor="chief")
    save_task(path, task)

    result_nc, _ = execute_merge(
        load_task(path), root=root, task_file=path, confirm=False
    )
    assert result_nc.get("action") == "await_confirm"

    result, updated = execute_merge(
        load_task(path),
        root=root,
        task_file=path,
        confirm=True,
        post_check_paths=["hello.txt"],
    )
    assert updated["status"] == "已完成"
    assert result.get("ok") is True or result.get("action") in ("merged", "ff", "no-ff")
    r = subprocess.run(
        [
            "git",
            "-C",
            str(wt),
            "merge-base",
            "--is-ancestor",
            feature,
            "demo/integration",
        ],
        check=False,
    )
    assert r.returncode == 0
    _git(wt, "checkout", "demo/integration")
    assert (wt / "hello.txt").read_text(encoding="utf-8") == "ping\n"
    report = path.parent / "merge" / "report.json"
    assert report.is_file()


def test_l7_coverage_pointers_documented():
    """L7 主路径已由 T4/test_lessons 覆盖——本测仅作指针，防止误重造。"""
    covered = [
        "test_lessons.py::test_full_publish_path",
        "test_lessons.py::test_publish_version_aligned_and_receipts",
        "test_t4_e2e.py::test_t4_lesson_anti_recurrence",
        "test_lite_d.py::test_l7_examples_and_subsequent_load_receipt",
    ]
    assert len(covered) == 4
