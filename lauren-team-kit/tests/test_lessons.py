"""Lite L5: candidate → review → publish → store readable."""

from __future__ import annotations

from pathlib import Path

import pytest

from lauren_team_kit.lessons import (
    LessonError,
    add_candidate,
    list_store,
    load_from_store,
    publish_candidate,
    review_candidate,
)
from lauren_team_kit.protocol import create_task, load_task, save_task


def _path(root: Path, tid: str) -> Path:
    return root / "workspace" / "runs" / tid / "task.json"


RULE = """# demo-l5-empty-guard

空输入必须返回 []，不得抛异常。
"""


def test_full_publish_path(tmp_path: Path):
    # Use a mini root that looks like delivery root (needs lauren-team-kit/)
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
    )
    assert task["lessons"]["candidates"][0]["status"] == "proposed"
    save_task(path, task)

    with pytest.raises(LessonError):
        publish_candidate(task, "demo-l5-empty-guard", root=root, actor="chief")

    task = review_candidate(
        task, "demo-l5-empty-guard", approved=True, actor="verifier", notes="probe ok"
    )
    assert task["lessons"]["candidates"][0]["status"] == "approved"

    task, record = publish_candidate(
        task, "demo-l5-empty-guard", root=root, actor="chief"
    )
    assert record["id"] == "demo-l5-empty-guard"
    assert record["store_path"].endswith("demo-l5-empty-guard.json")
    pubs = task["lessons"]["published"]
    assert any(p["id"] == "demo-l5-empty-guard" for p in pubs)
    assert task["lessons"]["candidates"][0]["status"] == "published"

    store_file = root / record["store_path"]
    assert store_file.is_file()
    loaded = load_from_store(root, "demo-l5-empty-guard")
    assert loaded["summary"] == "空输入必须返回 []"
    assert "rule_body" in loaded
    assert any(x["id"] == "demo-l5-empty-guard" for x in list_store(root))

    rule_path = root / record["rule_path"]
    assert rule_path.is_file()
    assert "空输入" in rule_path.read_text(encoding="utf-8")
    save_task(path, task)


def test_reject_stays_unpublished(tmp_path: Path):
    root = tmp_path / "delivery"
    (root / "lauren-team-kit" / "lessons" / "store").mkdir(parents=True)
    create_task(title="L5", task_id="rej", root=root)
    task = load_task(_path(root, "rej"))
    task = add_candidate(
        task, lesson_id="nope", summary="bad idea", actor="developer"
    )
    task = review_candidate(task, "nope", approved=False, actor="verifier")
    with pytest.raises(LessonError):
        publish_candidate(task, "nope", root=root, actor="chief")
    assert list_store(root) == []


def test_duplicate_candidate_refused(tmp_path: Path):
    root = tmp_path
    create_task(title="L5", task_id="dup", root=root)
    task = load_task(_path(root, "dup"))
    task = add_candidate(task, lesson_id="x", summary="s", actor="developer")
    with pytest.raises(LessonError):
        add_candidate(task, lesson_id="x", summary="s2", actor="developer")
