"""Real Git worktree create/verify for Lite-C L5."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lauren_team_kit.paths import PathRuleError, resolve_under_root, stable_dir_id


class WorktreeError(ValueError):
    """Illegal or failed worktree setup."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_git_bare(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    r = _run_git(path, "rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and r.stdout.strip() == "true"


def head_sha(repo: Path) -> str | None:
    r = _run_git(repo, "rev-parse", "HEAD")
    if r.returncode != 0:
        return None
    sha = r.stdout.strip()
    return sha or None


def current_branch(repo: Path) -> str | None:
    r = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if r.returncode != 0:
        return None
    b = r.stdout.strip()
    return b or None


def worktree_dirty(repo: Path) -> tuple[bool, str]:
    r = _run_git(repo, "status", "--porcelain")
    if r.returncode != 0:
        return True, f"git status 失败: {r.stderr.strip() or r.stdout.strip()}"
    if r.stdout.strip():
        return True, r.stdout.rstrip()
    return False, ""


def resolve_worktree_path(root: Path | str, task: dict[str, Any]) -> Path:
    root_p = Path(root).resolve()
    wt = task.get("worktree")
    if not isinstance(wt, dict):
        raise WorktreeError("缺少 worktree 对象")
    rel = wt.get("path")
    if not isinstance(rel, str) or not rel.strip():
        raise WorktreeError("缺少 worktree.path")
    p = Path(rel.strip())
    return p.resolve() if p.is_absolute() else (root_p / p).resolve()


def assert_controlled_worktree_path(
    root: Path | str, task: dict[str, Any], path: Path | None = None
) -> Path:
    """Worktree must stay under project root (no path escape).

    Lite default paths live under workspace/runs/<task_id>/; Team handoff may
    place worktrees under other in-root dirs (e.g. wt/<id>). Both are OK as
    long as the resolved path is inside root.
    """
    root_p = Path(root).resolve()
    task_id = str(task.get("task_id") or "").strip()
    if not task_id:
        raise WorktreeError("缺少 task_id，无法校验受控路径")
    wt = task.get("worktree") if isinstance(task.get("worktree"), dict) else {}
    raw = wt.get("path") if isinstance(wt.get("path"), str) else None
    if raw is None and path is not None:
        raw = str(path)
    if not isinstance(raw, str) or not raw.strip():
        raise WorktreeError("缺少 worktree.path")
    try:
        target = resolve_under_root(root_p, raw.strip())
    except PathRuleError as exc:
        raise WorktreeError(str(exc)) from exc
    if path is not None:
        try:
            explicit = Path(path).resolve()
            explicit.relative_to(root_p)
        except (OSError, ValueError) as exc:
            raise WorktreeError(
                f"worktree.path 必须位于项目根 {root_p} 下；实际={path}"
            ) from exc
        if explicit == root_p:
            raise WorktreeError("worktree.path 不能等于项目根，须为独立子目录")
    return target


def detect_base_repo(root: Path | str, base_repo: str | Path | None = None) -> Path:
    if base_repo:
        p = Path(base_repo).resolve()
        if not is_git_repo(p):
            raise WorktreeError(f"base_repo 不是 git 工作区: {p}")
        return p
    root_p = Path(root).resolve()
    if is_git_repo(root_p):
        return root_p
    raise WorktreeError(
        "无法自动找到 base_repo（项目根不是 git）；请传 base_repo="
        "一个已有仓库路径，或允许 bootstrap_base=True"
    )


def bootstrap_task_base_repo(root: Path | str, task_id: str) -> Path:
    """Create an isolated seed repo under runs/<id>/_seed_repo for demos/tests.

    Used when project root is not a git repo. Still a *real* git base for
    ``git worktree add``.
    """
    root_p = Path(root).resolve()
    seed = root_p / "workspace" / "runs" / stable_dir_id(task_id) / "_seed_repo"
    if is_git_repo(seed):
        return seed
    seed.mkdir(parents=True, exist_ok=True)
    cmds = [
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "lauren-kit@localhost"],
        ["git", "config", "user.name", "lauren-team-kit"],
    ]
    for c in cmds:
        r = subprocess.run(c, cwd=str(seed), capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise WorktreeError(
                f"bootstrap seed 失败 ({' '.join(c)}): {(r.stderr or r.stdout).strip()}"
            )
    readme = seed / "README.seed.md"
    readme.write_text(f"# seed for {task_id}\n", encoding="utf-8")
    for c in (
        ["git", "add", "README.seed.md"],
        ["git", "commit", "-m", f"seed:{task_id}"],
    ):
        r = subprocess.run(c, cwd=str(seed), capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise WorktreeError(
                f"bootstrap commit 失败: {(r.stderr or r.stdout).strip()}"
            )
    return seed


def inspect_worktree(root: Path | str, task: dict[str, Any]) -> dict[str, Any]:
    """Snapshot Git reality for resume reconcile / gates."""
    report: dict[str, Any] = {
        "ok": False,
        "path": None,
        "exists": False,
        "is_git": False,
        "controlled": False,
        "branch": None,
        "expected_branch": None,
        "head": None,
        "dirty": None,
        "dirty_detail": "",
        "errors": [],
    }
    wt = task.get("worktree") if isinstance(task.get("worktree"), dict) else {}
    report["expected_branch"] = wt.get("branch")
    try:
        path = resolve_worktree_path(root, task)
        report["path"] = str(path)
        assert_controlled_worktree_path(root, task, path)
        report["controlled"] = True
    except WorktreeError as e:
        report["errors"].append(str(e))
        return report

    report["exists"] = path.is_dir()
    if not report["exists"]:
        report["errors"].append(f"worktree 目录不存在: {path}")
        return report

    report["is_git"] = is_git_repo(path)
    if not report["is_git"]:
        report["errors"].append(f"目录不是 git 工作区: {path}")
        return report

    report["branch"] = current_branch(path)
    report["head"] = head_sha(path)
    dirty, detail = worktree_dirty(path)
    report["dirty"] = dirty
    report["dirty_detail"] = detail
    expected = report["expected_branch"]
    if expected and report["branch"] not in (expected, "HEAD"):
        # Detached HEAD is reported as HEAD; still ok if created via worktree
        if report["branch"] != expected:
            report["errors"].append(
                f"当前分支 {report['branch']!r} ≠ 协议 branch {expected!r}"
            )
    report["ok"] = len(report["errors"]) == 0
    return report


def ensure_task_worktree(
    task: dict[str, Any],
    *,
    root: Path | str,
    base_repo: str | Path | None = None,
    start_point: str | None = None,
    bootstrap_base: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create or verify a real git worktree; update task.worktree metadata.

    Returns (updated_task, report).
    When project root is not git and base_repo is omitted, optionally bootstrap
    an isolated seed repo under runs/<task_id>/_seed_repo (still real git).
    """
    root_p = Path(root).resolve()
    task = dict(task)
    wt = dict(task.get("worktree") or {})
    if "path" not in wt or "branch" not in wt:
        raise WorktreeError("worktree.path / worktree.branch 必填")

    path = assert_controlled_worktree_path(root_p, task)
    branch = str(wt["branch"]).strip()
    if not branch:
        raise WorktreeError("worktree.branch 不能为空")

    try:
        base = detect_base_repo(root_p, base_repo)
    except WorktreeError:
        if not bootstrap_base:
            raise
        tid = str(task.get("task_id") or "").strip()
        if not tid:
            raise
        base = bootstrap_task_base_repo(root_p, tid)
    report: dict[str, Any] = {
        "action": "noop",
        "path": str(path),
        "branch": branch,
        "base_repo": str(base),
    }

    if path.is_dir() and is_git_repo(path):
        insp = inspect_worktree(root_p, task)
        if not insp["ok"]:
            raise WorktreeError(
                "已有 worktree 校验失败: " + "; ".join(insp["errors"])
            )
        report["action"] = "verified_existing"
        report["head"] = insp["head"]
        wt["created"] = True
        wt["verified_at"] = _now_iso()
        wt["base_repo"] = str(base)
        task["worktree"] = wt
        return task, report

    if path.exists():
        raise WorktreeError(f"路径已存在但不是 git 工作区: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer creating branch from start_point (default HEAD of base)
    sp = start_point or "HEAD"
    # If branch already exists on base, add worktree without -b
    exists = _run_git(base, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    if exists.returncode == 0:
        add = _run_git(base, "worktree", "add", str(path), branch)
    else:
        add = _run_git(base, "worktree", "add", "-b", branch, str(path), sp)
    if add.returncode != 0:
        raise WorktreeError(
            f"git worktree add 失败: {(add.stderr or add.stdout).strip()}"
        )

    insp = inspect_worktree(root_p, {**task, "worktree": {**wt, "path": wt["path"]}})
    if not insp["ok"]:
        raise WorktreeError(
            "新建 worktree 后校验失败: " + "; ".join(insp["errors"])
        )

    now = _now_iso()
    wt["created"] = True
    wt["created_at"] = now
    wt["verified_at"] = now
    wt["base_repo"] = str(base)
    # Keep relative path as protocol path when it was relative
    task["worktree"] = wt
    report["action"] = "created"
    report["head"] = insp["head"]
    return task, report


def remove_task_worktree(
    task: dict[str, Any],
    *,
    root: Path | str,
    force: bool = False,
) -> dict[str, Any]:
    """Best-effort git worktree remove (used by cancel cleanup)."""
    root_p = Path(root).resolve()
    report: dict[str, Any] = {"removed": False, "detail": ""}
    try:
        path = resolve_worktree_path(root_p, task)
    except WorktreeError as e:
        report["detail"] = str(e)
        return report
    wt = task.get("worktree") if isinstance(task.get("worktree"), dict) else {}
    base_s = wt.get("base_repo")
    if not base_s or not Path(str(base_s)).is_dir():
        report["detail"] = "无 base_repo，跳过 git worktree remove"
        return report
    base = Path(str(base_s))
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(path))
    r = _run_git(base, *args)
    report["removed"] = r.returncode == 0
    report["detail"] = (r.stderr or r.stdout or "").strip()
    return report
