"""merge-precheck: real local git checks, never merges."""

from __future__ import annotations

import subprocess
from pathlib import Path

from lauren_team_kit.cli import main
from lauren_team_kit.merge_precheck import NOTE, evaluate_merge_precheck
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    save_task,
    transition_task,
)
from _seed import seed_trusted_pass


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip()


def _init_repo(repo: Path) -> tuple[str, str]:
    """Create repo with demo/integration + feature commit. Returns (integ_sha, feature_sha)."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    # Ensure main exists as current; create integration from here
    try:
        _git(repo, "branch", "-M", "main")
    except subprocess.CalledProcessError:
        pass
    _git(repo, "branch", "demo/integration")
    integ = _git(repo, "rev-parse", "demo/integration")
    _git(repo, "checkout", "-b", "feature/demo")
    (repo / "hello.txt").write_text("ping\n", encoding="utf-8")
    _git(repo, "add", "hello.txt")
    _git(repo, "commit", "-m", "feat: hello")
    feature = _git(repo, "rev-parse", "HEAD")
    return integ, feature


def _task_to_verified(tmp_path: Path, task_id: str, commit: str) -> Path:
    create_task(title="merge demo", task_id=task_id, root=tmp_path)
    path = tmp_path / "workspace" / "runs" / task_id / "task.json"
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    task = seed_trusted_pass(task, commit=commit)
    task = transition_task(task, to_status="验证通过", actor="verifier")
    save_task(path, task)
    return path


def test_merge_precheck_pass_path(tmp_path: Path, capsys):
    task_id = "mp-ok"
    path = _task_to_verified(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)

    report = evaluate_merge_precheck(task, root=tmp_path, task_file=path)
    assert report["ok"] is True, report
    assert report["note"] == NOTE
    assert "不执行 merge" in report["note"]
    assert "占位" not in report["note"]

    rc = main(["merge-precheck", "--task-id", task_id, "--root", str(tmp_path)])
    assert rc == 0
    assert "PASS" in capsys.readouterr().out


def test_merge_precheck_dirty_worktree_fails(tmp_path: Path):
    task_id = "mp-dirty"
    path = _task_to_verified(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)
    (wt / "scratch.txt").write_text("dirty\n", encoding="utf-8")

    report = evaluate_merge_precheck(load_task(path), root=tmp_path, task_file=path)
    assert report["ok"] is False
    dirty = next(c for c in report["checklist"] if c["item"] == "worktree_clean")
    assert dirty["ok"] is False


def test_merge_precheck_missing_integration_fails(tmp_path: Path):
    task_id = "mp-nointeg"
    path = _task_to_verified(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    wt.mkdir(parents=True, exist_ok=True)
    _git(wt, "init")
    _git(wt, "config", "user.email", "test@example.com")
    _git(wt, "config", "user.name", "Test")
    (wt / "README.md").write_text("only\n", encoding="utf-8")
    _git(wt, "add", "README.md")
    _git(wt, "commit", "-m", "init")
    feature = _git(wt, "rev-parse", "HEAD")
    # deliberately no demo/integration branch
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = feature
    save_task(path, task)

    report = evaluate_merge_precheck(load_task(path), root=tmp_path, task_file=path)
    assert report["ok"] is False
    item = next(c for c in report["checklist"] if c["item"] == "integration_branch_exists")
    assert item["ok"] is False
    assert "demo/integration" in str(item["detail"])


def test_merge_precheck_commit_mismatch_fails(tmp_path: Path):
    task_id = "mp-mis"
    path = _task_to_verified(tmp_path, task_id, "placeholder")
    task = load_task(path)
    wt = tmp_path / task["worktree"]["path"]
    _, feature = _init_repo(wt)
    task["artifact"]["commit"] = feature
    task["verification"]["bound_commit"] = "deadbeef"  # mismatch, not in repo either
    # Keep status 验证通过 but break commits — evaluate_merge_precheck does not re-run verify gate
    # structural validate would fail; we only test precheck checklist here.
    save_task(path, task)

    report = evaluate_merge_precheck(load_task(path), root=tmp_path, task_file=path)
    assert report["ok"] is False
    item = next(c for c in report["checklist"] if c["item"] == "bound_matches_artifact")
    assert item["ok"] is False


def test_merge_precheck_status_blocks(tmp_path: Path):
    create_task(title="early", task_id="mp-early", root=tmp_path)
    path = tmp_path / "workspace" / "runs" / "mp-early" / "task.json"
    assert main(["merge-precheck", "--task-id", "mp-early", "--root", str(tmp_path)]) == 1
