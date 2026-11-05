"""T1 probes: Nancy/Eng-B/already_merged must refuse; Nancy read-only still OK."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lauren_team_kit.authz import AuthzError
from lauren_team_kit.merge import execute_merge
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    record_check,
    save_task,
    set_artifact_commit,
    transition_task,
)
from lauren_team_kit.team import (
    TeamError,
    add_child_task,
    assign_task,
    create_team,
    eng_status_note,
    summarize_team,
    team_status,
)
from lauren_team_kit.verify_gate import evaluate_verify_gate
from _seed import seed_trusted_pass


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip()


def test_nancy_cannot_drive_execution_or_fake_verify(tmp_path: Path) -> None:
    create_task(title="nancy probe", task_id="n1", root=tmp_path)
    path = tmp_path / "workspace" / "runs" / "n1" / "task.json"
    task = load_task(path)

    with pytest.raises(AuthzError, match="Nancy|不得"):
        transition_task(task, to_status="执行中", actor="Nancy", role="nancy")

    # Even with claimed actor name only (inferred nancy)
    with pytest.raises(AuthzError, match="Nancy|不得"):
        transition_task(task, to_status="执行中", actor="Nancy")

    # Legal path to 待验证 as real roles, then Nancy must not push verify
    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    save_task(path, task)

    with pytest.raises(AuthzError):
        record_check(
            task,
            acceptance_id="A1",
            executed=True,
            exit_code=0,
            bound_commit="deadbeef",
            result="pass",
            actor="Nancy",
            role="nancy",
            log_path="/tmp/fake.log",
        )

    # Diagnostic-looking hand-fill by Nancy still must not satisfy gate
    with pytest.raises(AuthzError):
        record_check(
            load_task(path),
            acceptance_id="A1",
            executed=True,
            exit_code=0,
            bound_commit="deadbeef",
            result="pass",
            actor="Nancy",
            diagnostic=True,
        )

    with pytest.raises(AuthzError, match="Nancy|不得|验证通过"):
        transition_task(load_task(path), to_status="验证通过", actor="Nancy")


def test_nancy_readonly_summarize_status_ok(tmp_path: Path) -> None:
    create_team(root=tmp_path, team_id="tn", title="Nancy RO", force=True)
    add_child_task(root=tmp_path, team_id="tn", task_id="tn-a", title="A", force=True)
    summary = summarize_team(root=tmp_path, team_id="tn", by="Nancy", note="进度正常")
    assert summary["counts"]["total"] == 1
    st = team_status(root=tmp_path, team_id="tn", actor="Nancy")
    assert st["team_id"] == "tn"


def test_eng_b_cannot_note_eng_a_task(tmp_path: Path) -> None:
    create_team(root=tmp_path, team_id="te", title="Eng probe", force=True)
    add_child_task(root=tmp_path, team_id="te", task_id="te-a", title="A", force=True)
    assign_task(
        root=tmp_path, team_id="te", task_id="te-a", assignee="Eng-A", by="Matcha"
    )
    # Eng-A OK
    entry = eng_status_note(
        root=tmp_path,
        team_id="te",
        task_id="te-a",
        actor="Eng-A",
        note="ack stub; waiting real eng",
    )
    assert entry["by"] == "Eng-A"
    # Eng-B REFUSED
    with pytest.raises(TeamError, match="不是任务|负责人|不得"):
        eng_status_note(
            root=tmp_path,
            team_id="te",
            task_id="te-a",
            actor="Eng-B",
            note="hijack note",
        )


def test_already_merged_with_failed_acceptance_refuses_completion(tmp_path: Path) -> None:
    """verification=fail + empty checks + missing post path + bound already in integ →拒."""
    task_id = "mg-t1-reject"
    create_task(title="already_merged reject", task_id=task_id, root=tmp_path)
    path = tmp_path / "workspace" / "runs" / task_id / "task.json"
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    wt.mkdir(parents=True, exist_ok=True)
    _git(wt, "init")
    _git(wt, "config", "user.email", "t@e.com")
    _git(wt, "config", "user.name", "T")
    (wt / "README.md").write_text("base\n", encoding="utf-8")
    _git(wt, "add", "README.md")
    _git(wt, "commit", "-m", "init")
    try:
        _git(wt, "branch", "-M", "main")
    except subprocess.CalledProcessError:
        pass
    base = _git(wt, "rev-parse", "HEAD")
    _git(wt, "branch", "demo/integration", base)
    _git(wt, "checkout", "-b", "feature/demo")
    (wt / "hello.txt").write_text("ping\n", encoding="utf-8")
    _git(wt, "add", "hello.txt")
    _git(wt, "commit", "-m", "feat")
    feature = _git(wt, "rev-parse", "HEAD")
    # Merge feature into integration so bound is already ancestor
    _git(wt, "checkout", "demo/integration")
    _git(wt, "merge", "--ff-only", feature)
    _git(wt, "checkout", feature)

    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    # Intentionally BAD acceptance: fail + empty trusted checks
    task["artifact"] = {"commit": feature}
    task["verification"] = {
        "result": "fail",
        "bound_commit": feature,
        "checks": [],
        "trust": "diagnostic",
    }
    task = transition_task(task, to_status="需修改", actor="verifier")
    # Force status to 待合并 for the probe (bypass would previously complete)
    # Go: 需修改 → 执行中 → 待验证, then illegally craft 待合并 without pass
    task = transition_task(task, to_status="执行中", actor="developer")
    task = transition_task(task, to_status="待验证", actor="developer")
    # Seed a fake fail verification again and jump via direct status for probe
    # (simulating the historical bad state the bug accepted)
    task["status"] = "待合并"
    task["verification"] = {
        "result": "fail",
        "bound_commit": feature,
        "checks": [],
    }
    task["artifact"] = {"commit": feature}
    save_task(path, task)

    result, updated = execute_merge(
        load_task(path),
        root=tmp_path,
        task_file=path,
        confirm=True,
        post_check_paths=["does-not-exist-post.txt"],
    )
    assert result["ok"] is False
    assert result["action"] == "already_in_integration_rejected"
    assert updated.get("status") != "已完成"
    assert load_task(path)["status"] == "待合并"  # execute_merge caller didn't save on reject; status in updated
    assert updated.get("status") == "待合并"


def test_already_merged_with_valid_acceptance_still_idempotent(tmp_path: Path) -> None:
    task_id = "mg-t1-ok"
    create_task(title="already_merged ok", task_id=task_id, root=tmp_path)
    path = tmp_path / "workspace" / "runs" / task_id / "task.json"
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    wt.mkdir(parents=True, exist_ok=True)
    _git(wt, "init")
    _git(wt, "config", "user.email", "t@e.com")
    _git(wt, "config", "user.name", "T")
    (wt / "README.md").write_text("base\n", encoding="utf-8")
    _git(wt, "add", "README.md")
    _git(wt, "commit", "-m", "init")
    try:
        _git(wt, "branch", "-M", "main")
    except subprocess.CalledProcessError:
        pass
    base = _git(wt, "rev-parse", "HEAD")
    _git(wt, "branch", "demo/integration", base)
    _git(wt, "checkout", "-b", "feature/demo")
    (wt / "hello.txt").write_text("ping\n", encoding="utf-8")
    _git(wt, "add", "hello.txt")
    _git(wt, "commit", "-m", "feat")
    feature = _git(wt, "rev-parse", "HEAD")
    _git(wt, "checkout", "demo/integration")
    _git(wt, "merge", "--ff-only", feature)
    _git(wt, "checkout", feature)

    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    task = seed_trusted_pass(task, commit=feature)
    task = transition_task(task, to_status="验证通过", actor="verifier")
    task = transition_task(task, to_status="待合并", actor="chief")
    save_task(path, task)

    result, updated = execute_merge(
        load_task(path),
        root=tmp_path,
        task_file=path,
        confirm=True,
        post_check_paths=["hello.txt"],
    )
    assert result["ok"] is True
    assert result["action"] == "already_merged"
    assert updated["status"] == "已完成"


def test_diagnostic_checks_do_not_pass_gate(tmp_path: Path) -> None:
    create_task(title="diag", task_id="d1", root=tmp_path)
    path = tmp_path / "workspace" / "runs" / "d1" / "task.json"
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    task = set_artifact_commit(task, commit="deadbeef", actor="developer")
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit="deadbeef",
        result="pass",
        actor="developer",
        role="developer",
        diagnostic=True,
    )
    errs = evaluate_verify_gate(task)
    assert errs
    assert any("可信" in e or "verified_run" in e or "result" in e for e in errs)
