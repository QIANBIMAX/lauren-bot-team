"""Local Git merge precheck: inspect only, never merge or push."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from lauren_team_kit.verify_gate import commits_match

NOTE = "仅预检，不执行 merge；默认 confirm 需用户确认后再合"


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    r = _run_git(path, "rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and r.stdout.strip() == "true"


def _resolve_root(task_file: Path, root: str | Path | None) -> Path:
    if root:
        return Path(root).resolve()
    # task.json → runs/id → runs → workspace → project root
    return task_file.parent.parent.parent.parent


def _resolve_worktree(root: Path, task: dict[str, Any]) -> Path | None:
    wt = task.get("worktree")
    if not isinstance(wt, dict):
        return None
    rel = wt.get("path")
    if not isinstance(rel, str) or not rel.strip():
        return None
    p = Path(rel)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def _integration_branch(task: dict[str, Any]) -> str | None:
    integ = task.get("integration")
    if not isinstance(integ, dict):
        return None
    b = integ.get("branch")
    if isinstance(b, str) and b.strip():
        return b.strip()
    return None


def _head_sha(repo: Path) -> str | None:
    r = _run_git(repo, "rev-parse", "HEAD")
    if r.returncode != 0:
        return None
    sha = r.stdout.strip()
    return sha or None


def _local_branch_exists(repo: Path, branch: str) -> bool:
    r = _run_git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    return r.returncode == 0


def _commit_exists(repo: Path, commit: str) -> bool:
    r = _run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    return r.returncode == 0


def _worktree_clean(repo: Path) -> tuple[bool, str]:
    r = _run_git(repo, "status", "--porcelain")
    if r.returncode != 0:
        return False, f"git status 失败: {r.stderr.strip() or r.stdout.strip()}"
    porcelain = r.stdout
    if porcelain.strip():
        return False, f"工作区不干净:\n{porcelain.rstrip()}"
    return True, "git status --porcelain 为空"


def _ancestor_or_mergeable(
    repo: Path, integration: str, bound: str
) -> tuple[bool, str]:
    """FF if integration is ancestor of bound; else merge-tree for conflicts."""
    anc = _run_git(repo, "merge-base", "--is-ancestor", integration, bound)
    if anc.returncode == 0:
        return True, f"{integration} 是 {bound} 的祖先（可快进）"

    # Diverged or unrelated: dry-run merge via merge-tree --write-tree
    mt = _run_git(repo, "merge-tree", "--write-tree", integration, bound)
    if mt.returncode == 0:
        tree = mt.stdout.strip().splitlines()[0] if mt.stdout.strip() else ""
        return True, f"merge-tree 无冲突（tree={tree or 'ok'}）"

    detail = (mt.stderr or mt.stdout or "").strip()
    # Fallback older trivial form if --write-tree unsupported
    if "unknown option" in detail.lower() or "usage:" in detail.lower():
        mb = _run_git(repo, "merge-base", integration, bound)
        if mb.returncode != 0:
            return False, f"无法计算 merge-base: {mb.stderr.strip() or mb.stdout.strip()}"
        base = mb.stdout.strip()
        old = _run_git(repo, "merge-tree", base, integration, bound)
        out = old.stdout or ""
        if "changed in both" in out or "\n++<<<<<<<" in out or "<<<<<<<" in out:
            return False, "merge-tree 检测到冲突"
        if old.returncode != 0:
            return False, f"merge-tree 失败: {(old.stderr or out).strip()}"
        return True, "merge-tree（旧式）无冲突标记"

    return False, f"merge-tree 报告冲突或失败: {detail or f'exit={mt.returncode}'}"


def evaluate_merge_precheck(
    task: dict[str, Any],
    *,
    root: str | Path | None = None,
    task_file: str | Path | None = None,
) -> dict[str, Any]:
    """Build checklist report. Never performs merge or push."""
    checklist: list[dict[str, Any]] = []
    ok = True

    def add(item: str, item_ok: bool, detail: Any) -> None:
        nonlocal ok
        checklist.append({"item": item, "ok": item_ok, "detail": detail})
        if not item_ok:
            ok = False

    status = task.get("status")
    status_ok = status in ("验证通过", "待合并")
    add("status_in_验证通过_or_待合并", status_ok, f"status={status!r}")

    mp = task.get("merge_policy")
    mode_ok = isinstance(mp, dict) and isinstance(mp.get("mode"), str) and bool(mp.get("mode"))
    add(
        "merge_policy.mode",
        mode_ok,
        None if not isinstance(mp, dict) else mp.get("mode"),
    )

    art = task.get("artifact") if isinstance(task.get("artifact"), dict) else {}
    ver = task.get("verification") if isinstance(task.get("verification"), dict) else {}
    artifact_commit = art.get("commit")
    bound_commit = ver.get("bound_commit")
    commit_present = (
        isinstance(artifact_commit, str)
        and bool(artifact_commit.strip())
    ) or (isinstance(bound_commit, str) and bool(bound_commit.strip()))
    add(
        "commit_present",
        commit_present,
        {
            "artifact.commit": artifact_commit,
            "verification.bound_commit": bound_commit,
        },
    )

    tf = Path(task_file).resolve() if task_file else None
    project_root = _resolve_root(tf, root) if tf or root else Path.cwd()
    if root:
        project_root = Path(root).resolve()
    elif tf:
        project_root = _resolve_root(tf, None)

    ev_rel = task.get("evidence_dir")
    if isinstance(ev_rel, str) and ev_rel:
        ev_path = (project_root / ev_rel).resolve()
    elif tf:
        ev_path = tf.parent
    else:
        ev_path = project_root
    add("evidence_dir_exists", ev_path.is_dir(), str(ev_path))

    bound_ok = commits_match(artifact_commit, bound_commit)
    add(
        "bound_matches_artifact",
        bound_ok,
        f"artifact={artifact_commit!r}, bound={bound_commit!r}",
    )

    worktree = _resolve_worktree(project_root, task)
    integ = _integration_branch(task)
    bound_str = bound_commit.strip() if isinstance(bound_commit, str) else ""

    if worktree is None:
        add("worktree_path_resolvable", False, "缺少 worktree.path")
        add("worktree_is_git_repo", False, "无法解析 worktree")
        add("worktree_head_matches_bound", False, "跳过：无 worktree")
        add("worktree_clean", False, "跳过：无 worktree")
        add("commit_exists", False, "跳过：无 worktree")
        add("integration_branch_exists", False, "跳过：无 worktree")
        add("ancestor_or_fastforward_possible", False, "跳过：无 worktree")
        add("verification_not_stale", False, "跳过：无 worktree")
    elif not _is_git_repo(worktree):
        add("worktree_path_resolvable", True, str(worktree))
        add(
            "worktree_is_git_repo",
            False,
            f"目录不是 git 仓库或不存在: {worktree}",
        )
        add("worktree_head_matches_bound", False, "跳过：非 git 仓库")
        add("worktree_clean", False, "跳过：非 git 仓库")
        add("commit_exists", False, "跳过：非 git 仓库")
        add("integration_branch_exists", False, "跳过：非 git 仓库")
        add("ancestor_or_fastforward_possible", False, "跳过：非 git 仓库")
        add("verification_not_stale", False, "跳过：非 git 仓库")
    else:
        add("worktree_path_resolvable", True, str(worktree))
        add("worktree_is_git_repo", True, str(worktree))

        head = _head_sha(worktree)
        head_match = bool(head) and commits_match(head, bound_str)
        add(
            "worktree_head_matches_bound",
            head_match,
            f"HEAD={head!r}, bound={bound_str!r}",
        )
        # Same underlying fact: verification must still point at current HEAD
        add(
            "verification_not_stale",
            head_match,
            f"HEAD 仍等于 bound（HEAD={head!r}, bound={bound_str!r}）",
        )

        clean_ok, clean_detail = _worktree_clean(worktree)
        add("worktree_clean", clean_ok, clean_detail)

        exists = bool(bound_str) and _commit_exists(worktree, bound_str)
        add(
            "commit_exists",
            exists,
            f"git cat-file -e {bound_str!r} → {'ok' if exists else 'missing'}",
        )

        if not integ:
            add(
                "integration_branch_exists",
                False,
                "缺少 integration.branch（例如 demo/integration）",
            )
            add(
                "ancestor_or_fastforward_possible",
                False,
                "跳过：无 integration.branch",
            )
        else:
            branch_ok = _local_branch_exists(worktree, integ)
            add(
                "integration_branch_exists",
                branch_ok,
                (
                    f"本地分支 {integ!r} 存在"
                    if branch_ok
                    else f"本地不存在分支 {integ!r}；请先创建该 Demo 集成分支（预检不会自动创建）"
                ),
            )
            if branch_ok and exists and bound_str:
                merge_ok, merge_detail = _ancestor_or_mergeable(
                    worktree, integ, bound_str
                )
                add("ancestor_or_fastforward_possible", merge_ok, merge_detail)
            else:
                add(
                    "ancestor_or_fastforward_possible",
                    False,
                    "跳过：integration 分支或 bound commit 不可用",
                )

    return {
        "task_id": task.get("task_id"),
        "status": status,
        "ok": ok,
        "checklist": checklist,
        "note": NOTE,
        "root": str(project_root),
        "worktree": str(worktree) if worktree else None,
        "integration_branch": integ,
    }
