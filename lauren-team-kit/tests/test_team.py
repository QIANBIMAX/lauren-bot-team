"""Team dual-task protocol tests (hard role whitelist)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lauren_team_kit.protocol import load_task, validate_task
from lauren_team_kit.team import (
    TeamError,
    add_child_task,
    assign_task,
    create_team,
    eng_status_note,
    refuse_forbidden_payload,
    summarize_team,
    team_path_for,
    team_status,
    _resolve_team_role,
    _require_team_role,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "workspace" / "runs").mkdir(parents=True)
    (tmp_path / "lauren-team-kit").mkdir()
    return tmp_path


def test_create_team_and_two_children(root: Path) -> None:
    team = create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    assert team["schema_version"] == "lauren-team-run/0.2"
    assert team["roles"]["nancy"] == "Nancy"
    assert "Eng-A" in team["roles"]["eng_stubs"]

    team, t1 = add_child_task(
        root=root, team_id="demo-t1", task_id="t1-alpha", title="Alpha", force=True
    )
    team, t2 = add_child_task(
        root=root, team_id="demo-t1", task_id="t1-beta", title="Beta", force=True
    )
    assert team["child_task_ids"] == ["t1-alpha", "t1-beta"]
    assert t1["team"]["team_id"] == "demo-t1"
    assert validate_task(t1) == []
    assert validate_task(t2) == []


def test_matcha_assign_and_nancy_summarize(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-b", title="B", force=True)

    team = assign_task(
        root=root, team_id="demo-t1", task_id="t1-a", assignee="Eng-A", by="Matcha"
    )
    assert team["assignments"][-1]["assignee"] == "Eng-A"
    child = load_task(root / "workspace" / "runs" / "t1-a" / "task.json")
    assert child["team"]["assignee"] == "Eng-A"

    summary = summarize_team(root=root, team_id="demo-t1", by="Nancy")
    assert summary["counts"]["total"] == 2
    assert "t1-a" in summary["text"]
    assert Path(root / summary["path"]).is_file()

    st = team_status(root=root, team_id="demo-t1", actor="Nancy")
    assert st["children"][0]["task_id"] in ("t1-a", "t1-b")
    team_status(root=root, team_id="demo-t1", actor="Matcha")


def test_nancy_cannot_assign(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="不得 assign_task"):
        assign_task(
            root=root, team_id="demo-t1", task_id="t1-a", assignee="Eng-A", by="Nancy"
        )


def test_nancy_cannot_add_task(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    with pytest.raises(TeamError, match="不得 add_child_task"):
        add_child_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-x",
            title="X",
            requester="Nancy",
            force=True,
        )


def test_summarize_refuses_fake_verify_pass(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="禁止"):
        summarize_team(
            root=root,
            team_id="demo-t1",
            by="Nancy",
            note="本轮验证通过请合并",
        )


def test_matcha_rejects_code_field_note(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="禁止"):
        assign_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            assignee="Eng-A",
            by="Matcha",
            note="artifact.commit=abc123",
        )


def test_matcha_rejects_non_eng_stub_role(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="eng_stub"):
        assign_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            assignee="Eng-A",
            assignee_role="code",
            by="Matcha",
        )


def test_team_json_persisted(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    data = json.loads(team_path_for(root, "demo-t1").read_text(encoding="utf-8"))
    assert data["constraints"]["nancy_may_not"]
    assert "mark_verify_pass" in data["constraints"]["matcha_may_not"]


def test_matcha_cannot_summarize(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="不得 summarize_team"):
        summarize_team(root=root, team_id="demo-t1", by="Matcha")


def test_unknown_actor_rejected(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="未知 actor"):
        assign_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            assignee="Eng-A",
            by="RandomBot",
        )
    with pytest.raises(TeamError, match="未知 actor"):
        summarize_team(root=root, team_id="demo-t1", by="Ghost")
    with pytest.raises(TeamError, match="未知 actor"):
        add_child_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-z",
            title="Z",
            requester="Nobody",
            force=True,
        )


def test_eng_stub_status_note_ok_and_forbidden(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    assign_task(
        root=root, team_id="demo-t1", task_id="t1-a", assignee="Eng-A", by="Matcha"
    )
    entry = eng_status_note(
        root=root,
        team_id="demo-t1",
        task_id="t1-a",
        actor="Eng-A",
        note="ack stub; waiting real eng",
    )
    assert entry["kind"] == "eng_status_note"
    child = load_task(root / "workspace" / "runs" / "t1-a" / "task.json")
    assert any("eng_status_note" in (h.get("note") or "") for h in child["history"])

    with pytest.raises(TeamError, match="不得 assign_task"):
        assign_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            assignee="Eng-B",
            by="Eng-A",
        )
    with pytest.raises(TeamError, match="不得 summarize_team"):
        summarize_team(root=root, team_id="demo-t1", by="Eng-A")
    with pytest.raises(TeamError, match="不得 add_child_task"):
        add_child_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-y",
            title="Y",
            requester="Eng-A",
            force=True,
        )
    with pytest.raises(TeamError, match="禁止"):
        eng_status_note(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            actor="Eng-A",
            note="done artifact.commit=deadbeef",
        )
    with pytest.raises(TeamError, match="禁止字段"):
        eng_status_note(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            actor="Eng-A",
            note="looks fine",
            fields={"artifact": {"commit": "abc"}},
        )


def test_forbidden_fields_regardless_of_note(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="禁止字段"):
        assign_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            assignee="Eng-A",
            by="Matcha",
            note="harmless",
            fields={"verification": {"result": "pass"}},
        )
    with pytest.raises(TeamError, match="禁止字段"):
        summarize_team(
            root=root,
            team_id="demo-t1",
            by="Nancy",
            note="ok",
            fields={"merge": {"ok": True}},
        )


def test_resolve_role_helpers() -> None:
    team = {
        "roles": {
            "nancy": "Nancy",
            "matcha": "Matcha",
            "chief": "幕僚长",
            "eng_stubs": ["Eng-A", "Eng-B"],
        },
        "requester": "user",
    }
    assert _resolve_team_role(team, "Nancy") == "nancy"
    assert _resolve_team_role(team, "Eng-B") == "eng_stub"
    assert _require_team_role(team, "Matcha", allowed={"matcha"}, op="assign") == "matcha"
    assert _resolve_team_role(team, "Stranger") == "unknown"
    with pytest.raises(TeamError, match="未知 actor"):
        _require_team_role(team, "Stranger", allowed={"matcha"}, op="x")
    with pytest.raises(TeamError, match="禁止"):
        refuse_forbidden_payload("please execute_merge now")
    with pytest.raises(TeamError, match="不得"):
        _require_team_role(team, "幕僚长", allowed={"nancy", "matcha"}, op="team_status")


def test_assignee_must_be_listed_stub(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="eng_stubs"):
        assign_task(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            assignee="Eng-Z",
            by="Matcha",
        )


def test_eng_cannot_team_status_when_actor_set(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    with pytest.raises(TeamError, match="不得 team_status"):
        team_status(root=root, team_id="demo-t1", actor="Eng-A")


def test_matcha_cannot_eng_note(root: Path) -> None:
    create_team(root=root, team_id="demo-t1", title="Dual", force=True)
    add_child_task(root=root, team_id="demo-t1", task_id="t1-a", title="A", force=True)
    with pytest.raises(TeamError, match="不得 eng_status_note"):
        eng_status_note(
            root=root,
            team_id="demo-t1",
            task_id="t1-a",
            actor="Matcha",
            note="nope",
        )
