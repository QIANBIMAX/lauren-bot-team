"""Lite L5 + T4: candidate → probe review → publish → store + receipts."""

from __future__ import annotations

from pathlib import Path

import pytest

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
from lauren_team_kit.protocol import create_task, load_task, save_task


def _path(root: Path, tid: str) -> Path:
    return root / "workspace" / "runs" / tid / "task.json"


RULE = """# demo-l5-empty-guard

空输入必须返回 []，不得抛异常。
"""

PROBE = {"ref": "empty-query-probe", "description": "assert empty → []", "expected": "[]"}
EVIDENCE = {
    "probe_id": "empty-query-probe",
    "passed": True,
    "stdout_summary": "[]",
    "evidence": "checks/empty-probe.log",
    "at": "2026-11-05T00:00:00+08:00",
}


def test_full_publish_path(tmp_path: Path):
    root = tmp_path / "delivery"
    (root / "lauren-team-kit" / "rules").mkdir(parents=True)
    (root / "lauren-team-kit" / "lessons" / "store").mkdir(parents=True)
    create_task(title="L5", task_id="demo-c8", root=root)
    path = _path(root, "demo-c8")
    task = load_task(path)

    task = add_candidate(
        task,
        lesson_id="demo-l5-empty-guard",
        summary="空输入必须返回 []",
        actor="developer",
        rule_body=RULE,
        scope={"task_kind": "filter", "path_glob": "demo-app/**"},
        probe=PROBE,
    )
    assert task["lessons"]["candidates"][0]["status"] == "proposed"
    assert task["lessons"]["candidates"][0]["probe"]["ref"] == "empty-query-probe"
    save_task(path, task)

    with pytest.raises(LessonError):
        publish_candidate(task, "demo-l5-empty-guard", root=root, actor="chief")

    # approve without probe evidence must fail (T4)
    with pytest.raises(LessonError, match="探针|probe|证据"):
        review_candidate(
            task, "demo-l5-empty-guard", approved=True, actor="verifier", notes="bare"
        )

    task = review_candidate(
        task,
        "demo-l5-empty-guard",
        approved=True,
        actor="verifier",
        notes="probe ok",
        probe_result=EVIDENCE,
    )
    assert task["lessons"]["candidates"][0]["status"] == "approved"
    assert task["lessons"]["candidates"][0]["probe_result"]["passed"] is True

    task, record = publish_candidate(
        task, "demo-l5-empty-guard", root=root, actor="chief"
    )
    assert record["id"] == "demo-l5-empty-guard"
    assert record["store_path"].endswith("demo-l5-empty-guard.json")
    assert record["rules_version"]
    assert record["content_hash"]
    assert record["version"] == record["rules_version"]
    pubs = task["lessons"]["published"]
    assert any(p["id"] == "demo-l5-empty-guard" for p in pubs)
    assert task["lessons"]["candidates"][0]["status"] == "published"

    store_file = root / record["store_path"]
    assert store_file.is_file()
    loaded = load_from_store(root, "demo-l5-empty-guard")
    assert loaded["summary"] == "空输入必须返回 []"
    assert "rule_body" in loaded
    assert loaded["rules_version"] == record["rules_version"]
    assert loaded["content_hash"] == record["content_hash"]
    assert any(x["id"] == "demo-l5-empty-guard" for x in list_store(root))

    rule_path = root / record["rule_path"]
    assert rule_path.is_file()
    rule_text = rule_path.read_text(encoding="utf-8")
    assert "空输入" in rule_text
    assert record["rules_version"] in rule_text
    assert record["content_hash"] in rule_text
    save_task(path, task)


def test_reject_stays_unpublished(tmp_path: Path):
    root = tmp_path / "delivery"
    (root / "lauren-team-kit" / "lessons" / "store").mkdir(parents=True)
    create_task(title="L5", task_id="rej", root=root)
    task = load_task(_path(root, "rej"))
    task = add_candidate(
        task,
        lesson_id="nope",
        summary="bad idea",
        actor="developer",
        probe_ref="nope-probe",
    )
    task = review_candidate(task, "nope", approved=False, actor="verifier")
    with pytest.raises(LessonError):
        publish_candidate(task, "nope", root=root, actor="chief")
    assert list_store(root) == []


def test_duplicate_candidate_refused(tmp_path: Path):
    root = tmp_path
    create_task(title="L5", task_id="dup", root=root)
    task = load_task(_path(root, "dup"))
    task = add_candidate(
        task, lesson_id="x", summary="s", actor="developer", probe="x-probe"
    )
    with pytest.raises(LessonError):
        add_candidate(
            task, lesson_id="x", summary="s2", actor="developer", probe="x-probe"
        )


def test_add_without_probe_refused(tmp_path: Path):
    root = tmp_path
    create_task(title="L5", task_id="noprobe", root=root)
    task = load_task(_path(root, "noprobe"))
    with pytest.raises(LessonError, match="probe"):
        add_candidate(task, lesson_id="z", summary="s", actor="developer")


def test_publish_version_aligned_and_receipts(tmp_path: Path):
    root = tmp_path / "delivery"
    (root / "lauren-team-kit" / "rules").mkdir(parents=True)
    (root / "lauren-team-kit" / "lessons" / "store").mkdir(parents=True)
    create_task(title="L5", task_id="recv", root=root)
    path = _path(root, "recv")
    task = load_task(path)
    task = add_candidate(
        task,
        lesson_id="recv-rule",
        summary="防空输入",
        actor="developer",
        rule_body=RULE,
        applies_to="filter",
        probe_ref="recv-probe",
    )
    task = review_candidate(
        task,
        "recv-rule",
        approved=True,
        actor="verifier",
        evidence=EVIDENCE | {"probe_id": "recv-probe"},
    )
    task, record = publish_candidate(task, "recv-rule", root=root, actor="chief")
    loaded = load_from_store(root, "recv-rule")
    assert loaded["rules_version"] == record["rules_version"]
    assert loaded["content_hash"] == record["content_hash"]
    rule_text = (root / record["rule_path"]).read_text(encoding="utf-8")
    assert loaded["rules_version"] in rule_text
    assert loaded["content_hash"] in rule_text

    task = record_rule_load(
        task,
        eng="Eng-A",
        lesson_id="recv-rule",
        rules_version=record["rules_version"],
        actor="Eng-A",
    )
    task = record_rule_receive(
        task,
        developer="developer",
        lesson_id="recv-rule",
        rules_version=record["rules_version"],
        actor="developer",
    )
    receipts = task["rule_receipts"]
    assert any(r["kind"] == "load" and r["eng"] == "Eng-A" for r in receipts)
    assert any(r["kind"] == "receive" and r["developer"] == "developer" for r in receipts)
    assert any(
        r["kind"] == "load" for r in task["lessons"]["rule_receipts"]
    )
    save_task(path, task)

    # recurrence: fake regression still fails probe → blocked
    rec = evaluate_recurrence(
        root,
        "recv-rule",
        probe_result={
            "probe_id": "recv-probe",
            "passed": False,
            "stdout_summary": "raised TypeError",
        },
    )
    assert rec["recurrence_blocked"] is True
    assert rec["rule_check"] == "hit"
    task = record_recurrence(task, rec, actor="verifier")
    assert task["recurrence_events"][-1]["recurrence_blocked"] is True
