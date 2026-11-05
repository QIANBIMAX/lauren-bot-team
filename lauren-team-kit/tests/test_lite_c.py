"""Lite-C (L5/L6): real worktree, atomic RMW, cancel, reconcile, contract."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from lauren_team_kit.atomic_io import update_json_file
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    save_task,
    task_path_for,
    transition_task,
    update_task,
    validate_task,
)
from lauren_team_kit.runtime import (
    acquire_lease,
    cancel_task,
    reconcile_for_resume,
    resume_with_reconcile,
)
from lauren_team_kit.state_machine import IllegalTransitionError, can_transition
from lauren_team_kit.worktree_ops import (
    WorktreeError,
    assert_controlled_worktree_path,
    ensure_task_worktree,
    inspect_worktree,
    is_git_repo,
)


def test_ensure_real_worktree_creates_git_branch(tmp_path: Path) -> None:
    create_task(title="wt", task_id="lite-c-wt", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-wt")
    task = load_task(path)
    updated, report = ensure_task_worktree(task, root=tmp_path)
    assert report["action"] == "created"
    assert updated["worktree"]["created"] is True
    wt_path = tmp_path / "workspace" / "runs" / "lite-c-wt" / "worktree"
    assert wt_path.is_dir()
    assert is_git_repo(wt_path)
    insp = inspect_worktree(tmp_path, updated)
    assert insp["ok"], insp
    assert insp["branch"] == "task/lite-c-wt"
    save_task(path, updated)
    # idempotent verify
    again, report2 = ensure_task_worktree(load_task(path), root=tmp_path)
    assert report2["action"] == "verified_existing"
    assert again["worktree"]["created"] is True


def test_worktree_path_outside_controlled_rejected(tmp_path: Path) -> None:
    create_task(title="bad", task_id="lite-c-bad", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-bad")
    task = load_task(path)
    # Escape project root entirely
    task["worktree"]["path"] = str(tmp_path.parent / "outside-root-worktree")
    with pytest.raises(WorktreeError, match="项目根"):
        assert_controlled_worktree_path(tmp_path, task)
    with pytest.raises(WorktreeError, match="项目根"):
        ensure_task_worktree(task, root=tmp_path)


def test_concurrent_task_json_updates_no_loss(tmp_path: Path) -> None:
    create_task(title="rmw", task_id="lite-c-rmw", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-rmw")

    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def bump(i: int) -> None:
        try:
            barrier.wait(timeout=5)

            def mut(cur):
                cur = dict(cur)
                notes = list(cur.get("lite_c_notes") or [])
                notes.append(i)
                cur["lite_c_notes"] = notes
                return cur

            # schema additionalProperties=false — write via side file for RMW proof
            side = path.with_name("counter.json")
            update_json_file(
                side,
                lambda cur: {"n": int(cur.get("n", 0)) + 1, "seen": list(cur.get("seen") or []) + [i]},
                default={"n": 0, "seen": []},
            )
            update_task(
                path,
                lambda cur: {
                    **cur,
                    "history": list(cur.get("history") or [])
                    + [{"at": f"t{i}", "actor": "t", "to": cur.get("status"), "note": f"bump-{i}"}],
                },
            )
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=bump, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    side = path.with_name("counter.json")
    import json

    counter = json.loads(side.read_text(encoding="utf-8"))
    assert counter["n"] == 8
    assert sorted(counter["seen"]) == list(range(8))
    task = load_task(path)
    bump_notes = [h.get("note") for h in task["history"] if str(h.get("note", "")).startswith("bump-")]
    assert len(bump_notes) == 8
    assert sorted(bump_notes) == [f"bump-{i}" for i in range(8)]


def test_cancel_stops_lease_and_marks_cancelled(tmp_path: Path) -> None:
    create_task(title="cancel", task_id="lite-c-cancel", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-cancel")
    task = load_task(path)
    task, _ = ensure_task_worktree(task, root=tmp_path)
    task = transition_task(task, to_status="执行中", actor="developer", role="developer", root=tmp_path)
    task = acquire_lease(task, holder="dev-runner", pid=None, note="unit")
    updated, report = cancel_task(task, actor="chief", reason="user_abort", signal_process=False)
    assert updated["status"] == "已取消"
    assert updated["executor_lease"]["cancel_requested"] is True
    assert updated["executor_lease"]["status"] == "released"
    assert updated["cancel"]["os_kill_verified"] is False
    assert report["os_kill_verified"] is False
    save_task(path, updated)


def test_reconcile_blocks_when_executor_pid_alive(tmp_path: Path) -> None:
    create_task(title="rec", task_id="lite-c-rec", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-rec")
    task = load_task(path)
    task, _ = ensure_task_worktree(task, root=tmp_path)
    task = transition_task(task, to_status="执行中", actor="developer", role="developer", root=tmp_path)
    import os

    task = acquire_lease(task, holder="runner", pid=os.getpid())
    from lauren_team_kit.resume import block_task

    task = block_task(
        task,
        code="TEST_INTERRUPT",
        message="interrupted",
        recovery_hint="resume",
        resume_point="执行中",
        actor="chief",
    )
    rec = reconcile_for_resume(task, root=tmp_path)
    assert rec["safe_to_resume"] is False
    assert rec["code"] == "EXECUTOR_STILL_RUNNING"
    updated, report = resume_with_reconcile(
        task, root=tmp_path, actor="chief", to_status="执行中"
    )
    assert report["action"] == "reconcile_blocked"
    assert updated["status"] == "受阻"


def test_reconcile_allows_when_lease_released(tmp_path: Path) -> None:
    create_task(title="rec2", task_id="lite-c-rec2", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-rec2")
    task = load_task(path)
    task, _ = ensure_task_worktree(task, root=tmp_path)
    task = transition_task(task, to_status="执行中", actor="developer", role="developer", root=tmp_path)
    from lauren_team_kit.resume import block_task
    from lauren_team_kit.runtime import release_lease

    task = acquire_lease(task, holder="runner", pid=None)
    task = release_lease(task, reason="done")
    task = block_task(
        task,
        code="TEST_INTERRUPT",
        message="interrupted",
        recovery_hint="resume",
        resume_point="执行中",
        actor="chief",
    )
    updated, report = resume_with_reconcile(
        task, root=tmp_path, actor="chief", to_status="执行中"
    )
    assert report["action"] == "resumed"
    assert updated["status"] == "执行中"


def test_cancel_requested_blocks_resume(tmp_path: Path) -> None:
    create_task(title="cx", task_id="lite-c-cx", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-cx")
    task = load_task(path)
    task, _ = ensure_task_worktree(task, root=tmp_path)
    task = transition_task(task, to_status="执行中", actor="developer", role="developer", root=tmp_path)
    from lauren_team_kit.resume import block_task
    from lauren_team_kit.runtime import request_cancel_on_lease

    task, _ = request_cancel_on_lease(task, signal_process=False)
    task = block_task(
        task,
        code="CANCELLED_MID",
        message="cancel mid",
        recovery_hint="do not resume",
        resume_point="执行中",
        actor="chief",
    )
    # block_task may clear? no — lease remains
    updated, report = resume_with_reconcile(task, root=tmp_path, actor="chief")
    assert report["action"] == "reconcile_blocked"
    assert updated["status"] == "受阻"


def test_need_modify_cannot_skip_to_pending_verify() -> None:
    assert can_transition("需修改", "待验证") is False
    assert can_transition("需修改", "执行中") is True
    with pytest.raises(IllegalTransitionError):
        transition_task(
            {"status": "需修改", "history": []},
            to_status="待验证",
            actor="developer",
            role="developer",
            skip_authz=True,
            skip_route_guard=True,
        )


def test_lite_instructions_match_state_machine() -> None:
    # tests/ -> lauren-team-kit/ -> repo root
    repo = Path(__file__).resolve().parents[2]
    candidates = [
        repo / "lauren-omb-pack" / "bots" / "developer" / "instructions.md",
        repo / "lauren-omb-pack" / "bots" / "developer.instructions.md",
    ]
    found = False
    for c in candidates:
        if c.is_file():
            text = c.read_text(encoding="utf-8")
            assert "需修改 → 待验证" not in text
            assert "需修改 → 执行中" in text
            found = True
    assert found, "developer instructions not found"


def test_lite_path_no_team_hard_dependency(tmp_path: Path) -> None:
    create_task(title="lite", task_id="lite-c-direct", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-direct")
    task = load_task(path)
    assert "team" not in task
    task, _ = ensure_task_worktree(task, root=tmp_path)
    # developer may enter executing without handoff
    task = transition_task(
        task,
        to_status="执行中",
        actor="developer",
        role="developer",
        root=tmp_path,
    )
    assert task["status"] == "执行中"


def test_jsonschema_missing_reports_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_task(title="js", task_id="lite-c-js", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-js")
    task = load_task(path)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jsonschema" or name.startswith("jsonschema."):
            raise ImportError("simulated missing jsonschema")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from lauren_team_kit import protocol as proto

    errs = proto.jsonschema_validate(task, require=True)
    assert errs and "jsonschema" in errs[0]
    errs2 = validate_task(task, require_jsonschema=True)
    assert any("jsonschema" in e for e in errs2)


def test_enter_executing_auto_prepares_worktree(tmp_path: Path) -> None:
    create_task(title="auto", task_id="lite-c-auto", root=tmp_path)
    path = task_path_for(tmp_path, "lite-c-auto")
    task = load_task(path)
    assert not (tmp_path / "workspace/runs/lite-c-auto/worktree").exists()
    task = transition_task(
        task,
        to_status="执行中",
        actor="developer",
        role="developer",
        root=tmp_path,
    )
    assert task["status"] == "执行中"
    assert task["worktree"].get("created") is True
    assert is_git_repo(tmp_path / "workspace/runs/lite-c-auto/worktree")
