"""T2: Eng decompose → handoff → Developer ack → local commit → verify; route guards."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lauren_team_kit.authz import AuthzError
from lauren_team_kit.handoff import (
    ack_handoff,
    assert_handoff_ready,
    eng_decompose,
    eng_handoff_developer,
    escalate_scope_change,
    find_handoff,
    mark_handoff_status,
    omb_delegate,
    record_local_developer_commit,
    start_rework,
)
from lauren_team_kit.protocol import (
    load_task,
    record_check,
    save_task,
    set_artifact_commit,
    task_path_for,
    transition_task,
)
from lauren_team_kit.team import (
    TeamError,
    add_child_task,
    assign_task,
    create_team,
    load_team,
    set_task_dependencies,
    team_path_for,
    team_status,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "workspace" / "runs").mkdir(parents=True)
    return tmp_path


def _acc(aid: str = "A1") -> list[dict]:
    return [
        {
            "id": aid,
            "description": f"check {aid}",
            "command": "true",
            "must_run": True,
            "pass_criteria": "exit 0",
        }
    ]


def _seed_team(root: Path, team_id: str = "t2") -> None:
    create_team(root=root, team_id=team_id, title="T2", force=True)


def _package_path(
    root: Path,
    *,
    team_id: str,
    task_id: str,
    eng: str,
    title: str,
    fail_then_pass: bool = False,
) -> dict:
    """Full Eng-A/B style path: assign→decompose→handoff→ack→commit→verify (+optional rework)."""
    add_child_task(
        root=root, team_id=team_id, task_id=task_id, title=title, force=True
    )
    assign_task(
        root=root,
        team_id=team_id,
        task_id=task_id,
        assignee=eng,
        by="Matcha",
        assignee_role="eng_coordinator",
    )
    eng_decompose(
        root=root,
        team_id=team_id,
        task_id=task_id,
        actor=eng,
        goal=title,
        in_scope=[f"implement {task_id}"],
        acceptance=_acc(f"ACC-{task_id}"),
        worktree=str(root / "wt" / task_id),
    )
    handoff = eng_handoff_developer(
        root=root,
        team_id=team_id,
        task_id=task_id,
        actor=eng,
        developer="developer",
        mode="local",
    )
    hid = handoff["handoff_id"]
    ack_handoff(
        root=root,
        team_id=team_id,
        handoff_id=hid,
        actor="developer",
        run_id=f"run-{task_id}",
    )

    # Local mock commit (temp git optional; SHA string is enough for kit record)
    commit = "a" * 40 if task_id.endswith("a") else "b" * 40
    # Make distinct
    commit = (task_id.encode().hex() + "0" * 40)[:40]
    record_local_developer_commit(
        root=root,
        team_id=team_id,
        task_id=task_id,
        handoff_id=hid,
        commit=commit,
        actor="developer",
    )

    path = task_path_for(root, task_id)
    task = load_task(path)
    # Eng may acknowledge 执行中 (old mid-layer); developer enter after ack
    if task["status"] == "待执行":
        task = transition_task(
            task, to_status="执行中", actor=eng, role="eng_stub", root=root
        )
    task = set_artifact_commit(
        task, commit=commit, actor="developer", role="developer", root=root
    )
    task = transition_task(
        task, to_status="待验证", actor="developer", role="developer", root=root
    )
    save_task(path, task)

    aid = f"ACC-{task_id}"
    if fail_then_pass:
        task = record_check(
            load_task(path),
            acceptance_id=aid,
            executed=True,
            exit_code=1,
            bound_commit=commit,
            result="fail",
            actor="verifier",
            role="verifier",
            log_path=str(root / "fail.log"),
            new_round=True,
        )
        save_task(path, task)
        start_rework(
            root=root,
            team_id=team_id,
            task_id=task_id,
            actor=eng,
            reason="first verify fail",
        )
        # Eng schedules repair: new handoff + re-ack + new commit + new round
        eng_decompose(
            root=root,
            team_id=team_id,
            task_id=task_id,
            actor=eng,
            goal=title + " (rework)",
            in_scope=[f"fix {task_id}"],
            acceptance=_acc(aid),
            worktree=str(root / "wt" / task_id),
        )
        handoff2 = eng_handoff_developer(
            root=root,
            team_id=team_id,
            task_id=task_id,
            actor=eng,
            developer="developer",
            mode="local",
            note="rework package",
        )
        hid = handoff2["handoff_id"]
        ack_handoff(
            root=root,
            team_id=team_id,
            handoff_id=hid,
            actor="developer",
            run_id=f"run-{task_id}-rework",
        )
        commit2 = (commit[::-1])[:40]
        record_local_developer_commit(
            root=root,
            team_id=team_id,
            task_id=task_id,
            handoff_id=hid,
            commit=commit2,
            actor="developer",
        )
        task = load_task(path)
        # After fail path status may still be 待验证; set new artifact and re-verify
        if task["status"] == "待验证":
            # stay; just refresh artifact
            pass
        elif task["status"] == "执行中":
            pass
        else:
            # best-effort
            pass
        task = set_artifact_commit(
            task, commit=commit2, actor="developer", role="developer", root=root
        )
        # Move to 需修改 then 执行中 then 待验证 if needed — keep simple: from 待验证
        # record new round pass
        save_task(path, task)
        commit = commit2

    task = record_check(
        load_task(path),
        acceptance_id=aid,
        executed=True,
        exit_code=0,
        bound_commit=commit,
        result="pass",
        actor="verifier",
        role="verifier",
        log_path=str(root / "pass.log"),
        new_round=True,
    )
    save_task(path, task)
    mark_handoff_status(
        root=root,
        team_id=team_id,
        handoff_id=hid,
        status="done",
        actor="verifier",
        note="verified pass",
    )
    return {
        "task_id": task_id,
        "handoff_id": hid,
        "commit": commit,
        "task": load_task(path),
    }


def test_eng_a_and_eng_b_full_paths(root: Path) -> None:
    _seed_team(root)
    a = _package_path(
        root, team_id="t2", task_id="pkg-a", eng="Eng-A", title="Package A"
    )
    b = _package_path(
        root,
        team_id="t2",
        task_id="pkg-b",
        eng="Eng-B",
        title="Package B",
        fail_then_pass=True,
    )
    assert a["task"]["verification"]["result"] == "pass"
    assert b["task"]["verification"]["result"] == "pass"
    assert a["task"]["artifact"]["commit"] == a["commit"]
    team = load_team(team_path_for(root, "t2"))
    assert len(team["handoffs"]) >= 2
    # B had rework then new handoff
    assert any(h.get("status") == "done" for h in team["handoffs"])
    st = team_status(root=root, team_id="t2", actor="Nancy")
    assert st["routing_policy"]["mode"] == "engineering_chain"
    assert st["routing_policy"]["fast_path_enabled"] is False


def test_chief_cannot_bypass_without_handoff(root: Path) -> None:
    _seed_team(root)
    add_child_task(root=root, team_id="t2", task_id="x1", title="X", force=True)
    assign_task(
        root=root, team_id="t2", task_id="x1", assignee="Eng-A", by="Matcha"
    )
    path = task_path_for(root, "x1")
    task = load_task(path)
    # Chief tries to write developer artifact without handoff
    with pytest.raises(AuthzError, match="engineering_chain|绕过"):
        set_artifact_commit(
            task, commit="c" * 40, actor="幕僚长", role="chief", root=root
        )
    # Developer without ack
    with pytest.raises(AuthzError, match="handoff|接单|委派"):
        set_artifact_commit(
            task, commit="c" * 40, actor="developer", role="developer", root=root
        )
    # Chief cannot enter developer execute
    with pytest.raises(AuthzError, match="engineering_chain|绕过"):
        transition_task(
            task, to_status="执行中", actor="幕僚长", role="chief", root=root
        )


def test_assert_handoff_ready_rejects_unacked(root: Path) -> None:
    _seed_team(root)
    add_child_task(root=root, team_id="t2", task_id="y1", title="Y", force=True)
    assign_task(
        root=root, team_id="t2", task_id="y1", assignee="Eng-A", by="Matcha"
    )
    eng_decompose(
        root=root,
        team_id="t2",
        task_id="y1",
        actor="Eng-A",
        goal="Y",
        in_scope=["y"],
        acceptance=_acc(),
    )
    eng_handoff_developer(
        root=root, team_id="t2", task_id="y1", actor="Eng-A"
    )
    with pytest.raises(TeamError, match="acked|接单"):
        assert_handoff_ready(root=root, team_id="t2", task_id="y1")


def test_non_assignee_eng_still_blocked(root: Path) -> None:
    """T1 rule preserved: Eng-B cannot operate Eng-A's package."""
    _seed_team(root)
    add_child_task(root=root, team_id="t2", task_id="z1", title="Z", force=True)
    assign_task(
        root=root, team_id="t2", task_id="z1", assignee="Eng-A", by="Matcha"
    )
    with pytest.raises(TeamError, match="负责人|不得"):
        eng_decompose(
            root=root,
            team_id="t2",
            task_id="z1",
            actor="Eng-B",
            goal="nope",
            in_scope=["x"],
            acceptance=_acc(),
        )


def test_matcha_load_and_dependency_conflict(root: Path) -> None:
    _seed_team(root)
    for tid in ("d1", "d2", "d3"):
        add_child_task(
            root=root, team_id="t2", task_id=tid, title=tid, force=True
        )
    assign_task(root=root, team_id="t2", task_id="d1", assignee="Eng-A", by="Matcha")
    assign_task(root=root, team_id="t2", task_id="d2", assignee="Eng-A", by="Matcha")
    with pytest.raises(TeamError, match="负载"):
        assign_task(
            root=root, team_id="t2", task_id="d3", assignee="Eng-A", by="Matcha"
        )
    # Eng-B OK
    assign_task(root=root, team_id="t2", task_id="d3", assignee="Eng-B", by="Matcha")

    # Dependency cycle
    set_task_dependencies(
        root=root, team_id="t2", task_id="d1", depends_on=["d2"], by="Matcha"
    )
    with pytest.raises(TeamError, match="依赖冲突|环"):
        set_task_dependencies(
            root=root, team_id="t2", task_id="d2", depends_on=["d1"], by="Matcha"
        )


def test_omb_delegate_blocked_not_real(root: Path) -> None:
    _seed_team(root)
    add_child_task(root=root, team_id="t2", task_id="o1", title="O", force=True)
    assign_task(root=root, team_id="t2", task_id="o1", assignee="Eng-A", by="Matcha")
    eng_decompose(
        root=root,
        team_id="t2",
        task_id="o1",
        actor="Eng-A",
        goal="O",
        in_scope=["o"],
        acceptance=_acc(),
    )
    h = eng_handoff_developer(
        root=root,
        team_id="t2",
        task_id="o1",
        actor="Eng-A",
        mode="omb",
    )
    result = omb_delegate(
        root=root, team_id="t2", handoff_id=h["handoff_id"], actor="system"
    )
    assert result["omb_delegation"] == "blocked"
    assert result["mode"] == "simulated"
    team = load_team(team_path_for(root, "t2"))
    h2 = find_handoff(team, handoff_id=h["handoff_id"])
    assert h2 is not None
    assert h2["omb_delegation"] == "blocked"
    assert h2["mode"] == "simulated"


def test_escalate_scope_change(root: Path) -> None:
    _seed_team(root)
    add_child_task(root=root, team_id="t2", task_id="s1", title="S", force=True)
    assign_task(root=root, team_id="t2", task_id="s1", assignee="Eng-A", by="Matcha")
    entry = escalate_scope_change(
        root=root,
        team_id="t2",
        task_id="s1",
        actor="Eng-A",
        reason="API shape changed",
        to="matcha",
    )
    assert entry["kind"] == "scope_change"
    team = load_team(team_path_for(root, "t2"))
    assert team["scope_escalations"]
    assert any(
        "SCOPE_CHANGE" in (b.get("blockers") or [])
        for b in team["blockers_escalated"]
    )


def test_eng_stubs_field_retained(root: Path) -> None:
    team = create_team(root=root, team_id="compat", title="C", force=True)
    assert "eng_stubs" in team["roles"]
    assert team["roles"]["eng_coordinators"] == team["roles"]["eng_stubs"]
    assert "handoffs" in team
    assert team["routing_policy"]["mode"] == "engineering_chain"


def test_cannot_handoff_without_decompose(root: Path) -> None:
    _seed_team(root)
    add_child_task(root=root, team_id="t2", task_id="n1", title="N", force=True)
    assign_task(root=root, team_id="t2", task_id="n1", assignee="Eng-A", by="Matcha")
    with pytest.raises(TeamError, match="decompose"):
        eng_handoff_developer(
            root=root, team_id="t2", task_id="n1", actor="Eng-A"
        )


def test_lite_task_unaffected_by_route_guard(root: Path) -> None:
    """Standalone Lite task (no team) — chief/developer still work as before."""
    from lauren_team_kit.protocol import create_task

    create_task(title="lite", task_id="lite1", root=root)
    path = task_path_for(root, "lite1")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief", role="chief", root=root)
    task = set_artifact_commit(
        task, commit="d" * 40, actor="developer", role="developer", root=root
    )
    assert task["artifact"]["commit"] == "d" * 40
