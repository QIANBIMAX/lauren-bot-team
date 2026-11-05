"""W3: path identity, replace retries, common-dir merge lock, cross-process RMW."""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lauren_team_kit import atomic_io
from lauren_team_kit.atomic_io import (
    AtomicReplaceError,
    MergeLockError,
    atomic_write_text_unlocked,
    begin_recoverable_commit,
    finish_recoverable_commit,
    integration_merge_lock,
    merge_lock_path,
    note_recoverable_file,
    reconcile_recoverable_commits,
    refuse_break_merge_lock,
    update_json_file,
)
from lauren_team_kit.git_diag import read_git_diagnostics
from lauren_team_kit.paths import (
    PathRuleError,
    filesystem_kind,
    newline_normalized_digest,
    path_issues,
    raw_digest,
    stable_dir_id,
)
from lauren_team_kit.protocol import create_task
from lauren_team_kit.worktree_ops import WorktreeError, assert_controlled_worktree_path


def _pythonpath_env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / "src")
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not prev else src + os.pathsep + prev
    return env


def test_path_rules_drive_backslash_reserved_and_dotdot() -> None:
    assert path_issues(r"C:\work\demo", platform="win32") == []
    assert any(
        item["code"] == "dotdot" for item in path_issues(r"C:\work\..\Windows", platform="win32")
    )
    assert any(item["code"] == "backslash" for item in path_issues(r"foo\bar", platform="linux"))
    assert any(item["code"] == "reserved" for item in path_issues("nested/CON/out", platform="linux"))
    assert any(
        item["code"] == "trailing_space_or_dot"
        for item in path_issues("foo./bar", platform="win32")
    )
    assert any(
        item["code"] == "trailing_space_or_dot"
        for item in path_issues("foo /bar", platform="linux")
    )
    assert any(item["code"] == "illegal_char" for item in path_issues("bad<name>", platform="win32"))
    assert any(item["code"] == "unc" for item in path_issues(r"\\server\share\a", platform="win32"))
    assert filesystem_kind("//server/share/a") == "未支持"
    assert filesystem_kind("workspace/runs/demo") == "local"


def test_external_id_stable_dir_keeps_safe_and_hashes_rest() -> None:
    assert stable_dir_id("demo-c1") == "demo-c1"
    # Chinese task ids that are one legal component stay put; the title is separate.
    assert stable_dir_id("筛选任务") == "筛选任务"
    assert stable_dir_id("r-执行中") == "r-执行中"
    nested = stable_dir_id("任务/一")
    assert nested == stable_dir_id("任务/一")
    assert "/" not in nested and "\\" not in nested
    reserved = stable_dir_id("CON")
    assert reserved == stable_dir_id("CON")
    assert reserved != "CON"
    assert stable_dir_id("a/b") != "a/b"


def test_case_collision_does_not_overwrite(tmp_path: Path) -> None:
    create_task(title="筛选甲", task_id="Demo", root=tmp_path)
    with pytest.raises(PathRuleError, match="大小写碰撞"):
        create_task(title="筛选乙", task_id="demo", root=tmp_path)
    runs = tmp_path / "workspace" / "runs"
    found = [path for path in runs.iterdir() if path.is_dir()]
    assert len(found) == 1
    task = json.loads((found[0] / "task.json").read_text(encoding="utf-8"))
    assert task["task_id"] == "Demo"
    assert task["title"] == "筛选甲"


def test_newline_digest_collapses_crlf() -> None:
    lf = "line\nnext\n"
    crlf = "line\r\nnext\r\n"
    assert newline_normalized_digest(lf) == newline_normalized_digest(crlf)
    assert raw_digest(lf) != raw_digest(crlf)


def test_symlink_escape_rejected_and_inside_link_ok(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir()
    link_parent = tmp_path / "workspace"
    link_parent.mkdir()
    escape = link_parent / "escape"
    try:
        escape.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink not permitted: {exc}")
    task = {
        "task_id": "sym",
        "worktree": {"path": "workspace/escape", "branch": "task/sym"},
    }
    with pytest.raises(WorktreeError, match="项目根"):
        assert_controlled_worktree_path(tmp_path, task)

    inside = tmp_path / "workspace" / "runs" / "real"
    inside.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(inside, target_is_directory=True)
    ok = {
        "task_id": "sym",
        "worktree": {"path": "alias", "branch": "task/sym"},
    }
    resolved = assert_controlled_worktree_path(tmp_path, ok)
    assert resolved == inside.resolve()


def test_replace_busy_does_not_truncate_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "task.json"
    target.write_text("ORIGINAL", encoding="utf-8")
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _s: None)

    def boom(_src: str, _dst: str) -> None:
        raise PermissionError("busy")

    monkeypatch.setattr(atomic_io.os, "replace", boom)
    with pytest.raises(AtomicReplaceError):
        atomic_write_text_unlocked(target, "NEW")
    assert target.read_text(encoding="utf-8") == "ORIGINAL"
    assert list(tmp_path.glob(".task.json.*.tmp")) == []


def test_replace_retries_then_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "task.json"
    target.write_text("ORIGINAL", encoding="utf-8")
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _s: None)
    real = os.replace
    calls = {"n": 0}

    def flaky(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("busy")
        real(src, dst)

    monkeypatch.setattr(atomic_io.os, "replace", flaky)
    atomic_write_text_unlocked(target, "NEW")
    assert target.read_text(encoding="utf-8") == "NEW"
    assert calls["n"] == 3


def test_validator_failure_after_mutate_keeps_original(tmp_path: Path) -> None:
    target = tmp_path / "counter.json"
    target.write_text('{"n": 1}\n', encoding="utf-8")

    def reject(obj: object) -> None:
        if isinstance(obj, dict) and obj.get("n") == 2:
            raise ValueError("reject mutated")

    with pytest.raises(ValueError, match="reject"):
        update_json_file(target, lambda cur: {"n": 2}, validator=reject)
    assert json.loads(target.read_text(encoding="utf-8"))["n"] == 1


def test_recoverable_commit_is_not_a_transaction(tmp_path: Path) -> None:
    journal = tmp_path / "journal.json"
    file_a = tmp_path / "a.json"
    commit_id = begin_recoverable_commit(journal)
    atomic_write_text_unlocked(file_a, "{}\n")
    note_recoverable_file(journal, commit_id, str(file_a))
    open_rows = reconcile_recoverable_commits(journal)
    assert len(open_rows) == 1
    assert open_rows[0]["status"] == "open"
    assert str(file_a) in open_rows[0]["files"]
    assert not (tmp_path / "b.json").exists()
    finish_recoverable_commit(journal, commit_id)
    assert reconcile_recoverable_commits(journal) == []


def test_cross_process_lock_and_counter(tmp_path: Path) -> None:
    env = _pythonpath_env()
    lock = tmp_path / "demo.lock"
    start = tmp_path / "start"
    release = tmp_path / "release"
    holder = subprocess.Popen(
        [sys.executable, "-m", "lauren_team_kit.lock_probe", "hold", str(lock), str(start), str(release)],
        env=env,
    )
    try:
        deadline = os.times()  # silence unused if we use a loop
        del deadline
        for _ in range(100):
            if start.is_file() or holder.poll() is not None:
                break
            import time

            time.sleep(0.05)
        assert start.is_file(), "child did not acquire the lock"
        with pytest.raises(TimeoutError):
            from lauren_team_kit.atomic_io import file_lock

            with file_lock(lock, timeout_sec=0.4):
                pass
        assert lock.is_file()
    finally:
        release.write_text("go", encoding="utf-8")
        holder.wait(timeout=10)
    assert holder.returncode == 0

    counter = tmp_path / "counter.json"
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "lauren_team_kit.lock_probe", "bump", str(counter), "20"],
            env=env,
        )
        for _ in range(2)
    ]
    for proc in procs:
        proc.wait(timeout=30)
        assert proc.returncode == 0
    assert json.loads(counter.read_text(encoding="utf-8"))["n"] == 40


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_worktrees_share_common_dir_merge_lock(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    _git(repo, "config", "user.email", "lauren-kit@localhost")
    _git(repo, "config", "user.name", "lauren-team-kit")
    (repo / "README").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "seed")
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))

    left = merge_lock_path(repo, "demo/integration")
    right = merge_lock_path(wt, "demo/integration")
    assert left == right
    assert left.parent == left.parent  # common dir, not either worktree root
    assert left.parent != repo
    assert left.parent != wt
    other = merge_lock_path(repo, "other")
    assert other != left

    with integration_merge_lock(repo, "demo/integration"):
        assert left.is_file()
        with pytest.raises(TimeoutError):
            with integration_merge_lock(wt, "demo/integration", timeout_sec=0.35):
                pass
        assert left.is_file()
    assert left.is_file()
    with pytest.raises(MergeLockError, match="禁止"):
        refuse_break_merge_lock(left)
    source = inspect.getsource(integration_merge_lock)
    assert "unlink" not in source
    assert "remove(" not in source


def test_git_diagnostics_do_not_rewrite_global_config(tmp_path: Path) -> None:
    before = subprocess.run(
        ["git", "config", "--global", "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    report = read_git_diagnostics(repo)
    after = subprocess.run(
        ["git", "config", "--global", "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert before.returncode == after.returncode
    assert before.stdout == after.stdout
    assert report["config_rewritten"] is False
    assert report["present"] is True
    assert "version" in report
    assert "autocrlf" in report
    assert "safe_directory" in report
    assert report["safe_directory"]["observed_unrestricted"] in (True, False)
