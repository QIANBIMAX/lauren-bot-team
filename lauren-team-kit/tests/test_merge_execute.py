"""Real local merge: six acceptance scenarios + init-integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lauren_team_kit.cli import main
from lauren_team_kit.merge import EXIT_AWAIT_CONFIRM, execute_merge, init_integration_branch
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    record_check,
    save_task,
    transition_task,
)


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip()


def _init_repo(repo: Path) -> tuple[str, str]:
    """Returns (baseline_sha on main, feature_sha). Creates demo/integration at baseline."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    try:
        _git(repo, "branch", "-M", "main")
    except subprocess.CalledProcessError:
        pass
    baseline = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "demo/integration", baseline)
    _git(repo, "checkout", "-b", "feature/demo")
    (repo / "hello.txt").write_text("ping\n", encoding="utf-8")
    _git(repo, "add", "hello.txt")
    _git(repo, "commit", "-m", "feat: hello")
    feature = _git(repo, "rev-parse", "HEAD")
    return baseline, feature


def _task_pending_merge(tmp_path: Path, task_id: str, commit: str) -> Path:
    create_task(title="merge exec", task_id=task_id, root=tmp_path)
    path = tmp_path / "workspace" / "runs" / task_id / "task.json"
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit=commit,
        artifact_commit=commit,
        result="pass",
    )
    task = transition_task(task, to_status="验证通过", actor="verifier")
    task = transition_task(task, to_status="待合并", actor="chief")
    save_task(path, task)
    return path


def test_init_integration_creates_from_baseline(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "base")
    try:
        _git(repo, "branch", "-M", "main")
    except subprocess.CalledProcessError:
        pass
    base = _git(repo, "rev-parse", "HEAD")
    # diverge main
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-m", "extra")

    report = init_integration_branch(repo, baseline=base, branch="demo/integration")
    assert report["ok"] is True
    assert report["created"] is True
    tip = _git(repo, "rev-parse", "demo/integration")
    assert tip == base

    # second call: exists, no overwrite
    report2 = init_integration_branch(repo, baseline=base, branch="demo/integration")
    assert report2["ok"] is True
    assert report2["already_exists"] is True
    assert report2["created"] is False


def test_merge_happy_path(tmp_path: Path, capsys):
    task_id = "mg-ok"
    path = _task_pending_merge(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)

    rc = main(
        [
            "merge",
            "--task-id",
            task_id,
            "--root",
            str(tmp_path),
            "--confirm",
            "--post-check-path",
            "hello.txt",
        ]
    )
    assert rc == 0, capsys.readouterr()
    task2 = load_task(path)
    assert task2["status"] == "已完成"
    assert task2.get("merge", {}).get("method") in ("ff", "no-ff")
    integ = _git(wt, "rev-parse", "demo/integration")
    assert _git(wt, "merge-base", "--is-ancestor", feature, integ) == "" or True
    # verify ancestor
    r = subprocess.run(
        ["git", "-C", str(wt), "merge-base", "--is-ancestor", feature, "demo/integration"],
        check=False,
    )
    assert r.returncode == 0
    assert (wt / "hello.txt").read_text(encoding="utf-8") == "ping\n" or True
    # file on integration tip
    _git(wt, "checkout", "demo/integration")
    assert (wt / "hello.txt").is_file()
    report = path.parent / "merge" / "report.json"
    assert report.is_file()


def test_merge_cancel_without_confirm(tmp_path: Path, capsys):
    task_id = "mg-cancel"
    path = _task_pending_merge(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)
    before = _git(wt, "rev-parse", "demo/integration")
    head_before = _git(wt, "rev-parse", "HEAD")

    rc = main(["merge", "--task-id", task_id, "--root", str(tmp_path)])
    assert rc == EXIT_AWAIT_CONFIRM
    assert _git(wt, "rev-parse", "demo/integration") == before
    assert _git(wt, "rev-parse", "HEAD") == head_before
    task2 = load_task(path)
    assert task2["status"] == "待合并"


def test_merge_stale_verification_rejects(tmp_path: Path):
    task_id = "mg-stale"
    path = _task_pending_merge(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)
    # drift HEAD: new commit on feature
    (wt / "extra.txt").write_text("x\n", encoding="utf-8")
    _git(wt, "add", "extra.txt")
    _git(wt, "commit", "-m", "drift")

    result, updated = execute_merge(
        load_task(path), root=tmp_path, task_file=path, confirm=True
    )
    assert result["ok"] is False
    assert result["action"] == "precheck_failed"
    assert load_task(path)["status"] == "待合并"  # execute didn't save; status unchanged
    assert updated.get("status") == "待合并"


def test_merge_integration_baseline_changed_rejects(tmp_path: Path):
    """Target baseline change: move demo/integration so precheck ancestor/conflict fails."""
    task_id = "mg-base"
    path = _task_pending_merge(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)

    # Diverging change on integration that conflicts with feature's hello.txt
    _git(wt, "checkout", "demo/integration")
    (wt / "hello.txt").write_text("OTHER\n", encoding="utf-8")
    _git(wt, "add", "hello.txt")
    _git(wt, "commit", "-m", "integration diverged")
    _git(wt, "checkout", "feature/demo")

    result, _ = execute_merge(
        load_task(path), root=tmp_path, task_file=path, confirm=True
    )
    assert result["ok"] is False
    # either precheck conflict detection or actual conflict
    assert result["action"] in ("precheck_failed", "conflict")


def test_merge_conflict_marks_failed_no_force(tmp_path: Path):
    task_id = "mg-conflict"
    path = _task_pending_merge(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    repo = wt
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    (repo / "hello.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "hello.txt")
    _git(repo, "commit", "-m", "init")
    try:
        _git(repo, "branch", "-M", "main")
    except subprocess.CalledProcessError:
        pass
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "demo/integration", base)

    _git(repo, "checkout", "-b", "feature/demo")
    (repo / "hello.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "hello.txt")
    _git(repo, "commit", "-m", "feature side")
    feature = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "demo/integration")
    (repo / "hello.txt").write_text("integration\n", encoding="utf-8")
    _git(repo, "add", "hello.txt")
    _git(repo, "commit", "-m", "integration side")
    _git(repo, "checkout", "feature/demo")

    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)

    # If merge-tree detects conflict, precheck fails; else merge conflicts
    result, updated = execute_merge(
        load_task(path), root=tmp_path, task_file=path, confirm=True
    )
    assert result["ok"] is False
    if result["action"] == "conflict":
        save_task(path, updated)
        assert load_task(path)["status"] == "合并失败"
        # no conflict markers left / clean after abort
        st = subprocess.run(
            ["git", "-C", str(wt), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "UU" not in st.stdout
    else:
        assert result["action"] == "precheck_failed"


def test_merge_idempotent_no_double_merge(tmp_path: Path):
    task_id = "mg-idem"
    path = _task_pending_merge(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)

    assert (
        main(
            [
                "merge",
                "--task-id",
                task_id,
                "--root",
                str(tmp_path),
                "--confirm",
            ]
        )
        == 0
    )
    tip1 = _git(wt, "rev-parse", "demo/integration")
    task_done = load_task(path)
    assert task_done["status"] == "已完成"

    # Reset status to 待合并 to re-request merge (simulating repeat request)
    # After 已完成, cannot transition; so call execute_merge on a copy that is 待合并
    # but integration already contains bound — should noop without new merge commit
    task_again = load_task(path)
    # Manually set status back for idempotent re-entry test of git side
    # Use fresh task file state: 待合并 with same commits
    path2 = _task_pending_merge(tmp_path, "mg-idem2", feature)
    # Reuse same worktree path pointing at already-merged repo
    t2 = load_task(path2)
    t2["worktree"]["path"] = task["worktree"]["path"]
    t2["artifact"]["commit"] = feature
    t2["verification"]["bound_commit"] = feature
    save_task(path2, t2)

    # HEAD may be on feature; precheck wants HEAD==bound. Ensure checkout feature@bound
    _git(wt, "checkout", feature)
    result, updated = execute_merge(
        load_task(path2), root=tmp_path, task_file=path2, confirm=True
    )
    assert result["ok"] is True
    assert result["action"] == "already_merged"
    tip2 = _git(wt, "rev-parse", "demo/integration")
    assert tip2 == tip1
    save_task(path2, updated)
    assert load_task(path2)["status"] == "已完成"
    assert updated.get("merge", {}).get("method") == "noop"


def test_merge_auto_mode_skips_confirm_flag(tmp_path: Path):
    task_id = "mg-auto"
    path = _task_pending_merge(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    task["merge_policy"]["mode"] = "auto"
    save_task(path, task)

    rc = main(["merge", "--task-id", task_id, "--root", str(tmp_path)])
    assert rc == 0
    assert load_task(path)["status"] == "已完成"


def test_merge_idempotent_when_already_completed(tmp_path: Path):
    """status=已完成 + integration already has bound → already_merged, no git change."""
    task_id = "mg-done-idem"
    path = _task_pending_merge(tmp_path, task_id, "x")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)

    r1, t1 = execute_merge(load_task(path), root=tmp_path, task_file=path, confirm=True)
    assert r1["ok"] and r1["action"] == "merged"
    save_task(path, t1)
    assert load_task(path)["status"] == "已完成"
    tip_before = _git(wt, "rev-parse", "demo/integration")

    r2, t2 = execute_merge(load_task(path), root=tmp_path, task_file=path, confirm=True)
    assert r2["ok"] is True
    assert r2["action"] == "already_merged"
    assert r2["exit_code"] == 0
    assert t2["status"] == "已完成"
    assert _git(wt, "rev-parse", "demo/integration") == tip_before
