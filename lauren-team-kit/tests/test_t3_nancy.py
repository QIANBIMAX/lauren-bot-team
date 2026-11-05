"""T3: Nancy persistence, stage split, blocker dedup, objective notes."""

from __future__ import annotations

from pathlib import Path

import pytest

from lauren_team_kit.protocol import load_task, save_task
from lauren_team_kit.resume import block_task, resume_task
from lauren_team_kit.team import (
    TeamError,
    add_child_task,
    add_team_todo,
    assign_task,
    complete_team_todo,
    create_team,
    list_team_todos,
    load_team,
    refuse_forbidden_payload,
    resolve_team_blocker,
    summarize_team,
    team_path_for,
    team_status,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "workspace" / "runs").mkdir(parents=True)
    (tmp_path / "lauren-team-kit").mkdir()
    return tmp_path


def _seed(root: Path, team_id: str = "t3") -> None:
    create_team(root=root, team_id=team_id, title="T3", force=True)
    add_child_task(root=root, team_id=team_id, task_id="t3-a", title="A", force=True)
    assign_task(root=root, team_id=team_id, task_id="t3-a", assignee="Eng-A", by="Matcha")


def test_todo_persists_across_reload(root: Path) -> None:
    _seed(root)
    entry = add_team_todo(
        root=root,
        team_id="t3",
        text="催一下 beta 阻塞",
        by="Nancy",
        source="user",
    )
    assert entry["todo_id"] == "todo-001"
    assert entry["status"] == "open"
    # Simulate restart: re-load team.json from disk
    team = load_team(team_path_for(root, "t3"))
    assert any(t.get("todo_id") == "todo-001" for t in team.get("todos") or [])
    listed = list_team_todos(root=root, team_id="t3", by="Nancy")
    assert listed[0]["text"] == "催一下 beta 阻塞"
    st = team_status(root=root, team_id="t3", actor="Nancy")
    assert st["todos"][0]["todo_id"] == "todo-001"


def test_todo_done_requires_basis(root: Path) -> None:
    _seed(root)
    add_team_todo(root=root, team_id="t3", text="跟进合并", by="Nancy")
    with pytest.raises(TeamError, match="done_basis"):
        complete_team_todo(
            root=root, team_id="t3", todo_id="todo-001", by="Nancy", done_basis=None
        )
    with pytest.raises(TeamError, match="done_basis|非法"):
        complete_team_todo(
            root=root,
            team_id="t3",
            todo_id="todo-001",
            by="Nancy",
            done_basis="title_looks_done",
        )
    done = complete_team_todo(
        root=root,
        team_id="t3",
        todo_id="todo-001",
        by="Nancy",
        done_basis="user_confirmed",
    )
    assert done["status"] == "done"
    assert done["done_basis"] == "user_confirmed"


def test_blocker_dedup_and_resolve(root: Path) -> None:
    _seed(root)
    path = root / "workspace" / "runs" / "t3-a" / "task.json"
    task = load_task(path)
    task = block_task(
        task,
        code="WAITING_ENG",
        message="wait",
        recovery_hint="hint",
        resume_point="执行中",
        actor="Matcha",
    )
    save_task(path, task)

    s1 = summarize_team(root=root, team_id="t3", by="Nancy")
    s2 = summarize_team(root=root, team_id="t3", by="Nancy")
    team = load_team(team_path_for(root, "t3"))
    open_waiting = [
        e
        for e in team["blockers_escalated"]
        if e.get("task_id") == "t3-a"
        and (e.get("reason_code") == "WAITING_ENG" or "WAITING_ENG" in (e.get("blockers") or []))
        and (e.get("status") or e.get("lifecycle") or "open") == "open"
    ]
    assert len(open_waiting) == 1
    assert s1["counts"]["open_blocker_escalations"] == 1
    assert s2["counts"]["open_blocker_escalations"] == 1

    resolve_team_blocker(
        root=root, team_id="t3", task_id="t3-a", reason_code="WAITING_ENG", by="Nancy"
    )
    # Clear the underlying task blocker so auto-sync does not re-open
    task = load_task(path)
    task, _report = resume_task(
        task, actor="Matcha", to_status="执行中", clear_blocker_code="WAITING_ENG"
    )
    save_task(path, task)

    s3 = summarize_team(root=root, team_id="t3", by="Nancy")
    team = load_team(team_path_for(root, "t3"))
    open_waiting = [
        e
        for e in team["blockers_escalated"]
        if e.get("task_id") == "t3-a"
        and (e.get("reason_code") == "WAITING_ENG" or "WAITING_ENG" in (e.get("blockers") or []))
        and (e.get("status") or e.get("lifecycle") or "open") == "open"
    ]
    assert open_waiting == []
    assert s3["counts"]["open_blocker_escalations"] == 0


def test_pending_merge_not_completed(root: Path) -> None:
    _seed(root)
    path = root / "workspace" / "runs" / "t3-a" / "task.json"
    task = load_task(path)
    task["status"] = "待合并"
    save_task(path, task)

    summary = summarize_team(root=root, team_id="t3", by="Nancy")
    assert "doneish" not in summary["counts"]
    assert summary["counts"]["pending_merge"] == 1
    assert summary["counts"]["completed"] == 0
    assert summary["counts"]["verified"] == 0
    assert "尚未完成" in summary["text"]
    assert "pending_merge=1" in summary["text"]


def test_objective_status_note_allowed(root: Path) -> None:
    _seed(root)
    # Must succeed (T3 / R5)
    summary = summarize_team(
        root=root,
        team_id="t3",
        by="Nancy",
        note="任务待合并，尚未完成",
    )
    assert "任务待合并，尚未完成" in summary["text"]

    # Structured field smuggling still refused
    with pytest.raises(TeamError, match="禁止字段"):
        summarize_team(
            root=root,
            team_id="t3",
            by="Nancy",
            note="客观备注",
            fields={"verification": {"result": "pass"}},
        )
    # Imperative smuggling still refused
    with pytest.raises(TeamError, match="禁止"):
        refuse_forbidden_payload("本轮验证通过请合并")
    with pytest.raises(TeamError, match="禁止"):
        refuse_forbidden_payload("please execute_merge now")


def test_execution_view_columns(root: Path) -> None:
    _seed(root)
    st = team_status(root=root, team_id="t3", actor="Nancy")
    assert st["execution_view"]
    row = st["execution_view"][0]
    assert row["responsible"] == "Eng-A"
    assert row["executor"] == "-"
    assert "verifier" in row
    summary = summarize_team(root=root, team_id="t3", by="Nancy")
    assert summary["execution_view"][0]["responsible"] == "Eng-A"
