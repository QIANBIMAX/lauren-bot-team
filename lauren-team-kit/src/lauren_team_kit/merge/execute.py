"""Real local Git merge for Demo integration branch only.

Never pushes remotes. Never touches company main repos by path convention:
operates only on the task worktree's git repo + task.integration.branch.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from lauren_team_kit.merge_precheck import (
    _integration_branch,
    _resolve_root,
    _resolve_worktree,
    evaluate_merge_precheck,
)
from lauren_team_kit.protocol import save_task, transition_task
from lauren_team_kit.state_machine import IllegalTransitionError
from lauren_team_kit.verify_gate import commits_match

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_AWAIT_CONFIRM = 3

NOTE_NO_PUSH = "仅本地 Demo 集成分支；禁止 push；禁止公司主仓"


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _rev_parse_commit(repo: Path, ref: str) -> str | None:
    """Resolve ref to full commit SHA via git (not string prefix alone)."""
    if not ref or not str(ref).strip():
        return None
    r = _run_git(repo, "rev-parse", "--verify", f"{ref.strip()}^{{commit}}")
    if r.returncode != 0:
        return None
    sha = r.stdout.strip()
    return sha or None


def _current_branch(repo: Path) -> str | None:
    r = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if r.returncode != 0:
        return None
    name = r.stdout.strip()
    if not name or name == "HEAD":
        return None
    return name


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    r = _run_git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    return r.returncode == 0


def _local_branch_exists(repo: Path, branch: str) -> bool:
    r = _run_git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    return r.returncode == 0


def _write_merge_report(evidence_dir: Path, report: dict[str, Any]) -> Path:
    merge_dir = evidence_dir / "merge"
    merge_dir.mkdir(parents=True, exist_ok=True)
    path = merge_dir / "report.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def init_integration_branch(
    worktree: Path | str,
    *,
    baseline: str,
    branch: str = "demo/integration",
    force: bool = False,
) -> dict[str, Any]:
    """Create local integration branch from an explicit clean baseline commit/ref.

    Does not guess from a dirty working tree. If branch exists, report and
    refuse to move it unless force=True.
    """
    repo = Path(worktree).resolve()
    out: dict[str, Any] = {
        "ok": False,
        "worktree": str(repo),
        "branch": branch,
        "baseline": baseline,
        "created": False,
        "already_exists": False,
        "note": NOTE_NO_PUSH,
    }
    if not repo.is_dir():
        out["error"] = f"worktree 不存在: {repo}"
        return out
    inside = _run_git(repo, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        out["error"] = f"不是 git 工作区: {repo}"
        return out

    base_sha = _rev_parse_commit(repo, baseline)
    if not base_sha:
        out["error"] = f"无法解析基线为 commit: {baseline!r}"
        return out
    out["baseline_resolved"] = base_sha

    if _local_branch_exists(repo, branch):
        tip = _rev_parse_commit(repo, branch)
        out["already_exists"] = True
        out["existing_tip"] = tip
        if not force:
            out["ok"] = True
            out["message"] = (
                f"本地分支 {branch!r} 已存在（tip={tip}）；默认不覆盖。"
                "若要重建请显式 --force（危险，会移动分支指针）。"
            )
            return out
        # force: reset branch tip to baseline without checkout if possible
        r = _run_git(repo, "branch", "-f", branch, base_sha)
        if r.returncode != 0:
            out["error"] = f"强制移动分支失败: {(r.stderr or r.stdout).strip()}"
            return out
        out["ok"] = True
        out["created"] = True
        out["forced"] = True
        out["message"] = f"已强制将 {branch!r} 指向 {base_sha}"
        return out

    r = _run_git(repo, "branch", branch, base_sha)
    if r.returncode != 0:
        out["error"] = f"创建分支失败: {(r.stderr or r.stdout).strip()}"
        return out
    out["ok"] = True
    out["created"] = True
    out["message"] = f"已从基线 {base_sha} 创建本地分支 {branch!r}"
    return out


def plan_merge(
    task: dict[str, Any],
    *,
    root: str | Path | None = None,
    task_file: str | Path | None = None,
) -> dict[str, Any]:
    """Describe what would be merged (no git writes)."""
    tf = Path(task_file).resolve() if task_file else None
    project_root = _resolve_root(tf, root) if tf or root else Path.cwd()
    if root:
        project_root = Path(root).resolve()
    elif tf:
        project_root = _resolve_root(tf, None)

    worktree = _resolve_worktree(project_root, task)
    integ = _integration_branch(task)
    art = task.get("artifact") if isinstance(task.get("artifact"), dict) else {}
    ver = task.get("verification") if isinstance(task.get("verification"), dict) else {}
    artifact = art.get("commit")
    bound = ver.get("bound_commit")
    mp = task.get("merge_policy") if isinstance(task.get("merge_policy"), dict) else {}
    mode = mp.get("mode")

    resolved_bound = None
    resolved_artifact = None
    if worktree and worktree.is_dir():
        if isinstance(bound, str):
            resolved_bound = _rev_parse_commit(worktree, bound)
        if isinstance(artifact, str):
            resolved_artifact = _rev_parse_commit(worktree, artifact)

    return {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "merge_policy_mode": mode,
        "worktree": str(worktree) if worktree else None,
        "integration_branch": integ,
        "artifact_commit": artifact,
        "bound_commit": bound,
        "artifact_resolved": resolved_artifact,
        "bound_resolved": resolved_bound,
        "note": (
            "默认 confirm：须加 --confirm 才会真正 merge；"
            "merge_policy.mode=auto 可跳过确认但仍跑全部检查。"
            f" {NOTE_NO_PUSH}"
        ),
    }


def _ensure_待合并(task: dict[str, Any], *, actor: str) -> dict[str, Any]:
    status = task.get("status")
    if status == "待合并":
        return task
    if status == "验证通过":
        return transition_task(
            task,
            to_status="待合并",
            actor=actor,
            note="merge 入口：验证通过 → 待合并",
        )
    raise IllegalTransitionError(
        f"merge 要求状态为 待合并 或 验证通过，当前={status!r}"
    )


def _git_commits_same(repo: Path, a: str, b: str) -> bool:
    ra = _rev_parse_commit(repo, a)
    rb = _rev_parse_commit(repo, b)
    if ra and rb:
        return ra == rb
    return commits_match(a, b)


def execute_merge(
    task: dict[str, Any],
    *,
    root: str | Path | None = None,
    task_file: str | Path | None = None,
    confirm: bool = False,
    actor: str = "merge",
    post_check_paths: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run confirm-gated local merge into integration branch.

    Returns (result_dict, updated_task). Caller should save_task when
    result indicates task was mutated (merged / failed / already).

    result keys include: ok, exit_code, action, precheck, plan, merge, …
    """
    tf = Path(task_file).resolve() if task_file else None
    project_root = Path(root).resolve() if root else (
        _resolve_root(tf, None) if tf else Path.cwd()
    )

    plan = plan_merge(task, root=project_root, task_file=tf)
    mp = task.get("merge_policy") if isinstance(task.get("merge_policy"), dict) else {}
    mode = mp.get("mode")
    needs_confirm = mode != "auto"

    result: dict[str, Any] = {
        "ok": False,
        "exit_code": EXIT_FAIL,
        "action": None,
        "plan": plan,
        "note": NOTE_NO_PUSH,
    }

    if needs_confirm and not confirm:
        result["action"] = "await_confirm"
        result["exit_code"] = EXIT_AWAIT_CONFIRM
        result["ok"] = False
        result["message"] = (
            "merge_policy.mode=confirm 且未传 --confirm：未改 git、未改任务状态。"
            "将要合并的对象见 plan。"
        )
        return result, task

    # Re-run full precheck
    precheck = evaluate_merge_precheck(task, root=project_root, task_file=tf)
    result["precheck"] = precheck
    if not precheck.get("ok"):
        result["action"] = "precheck_failed"
        result["exit_code"] = EXIT_FAIL
        result["message"] = "执行前预检失败，拒绝 merge"
        return result, task

    worktree = _resolve_worktree(project_root, task)
    integ = _integration_branch(task)
    if worktree is None or not integ:
        result["action"] = "missing_worktree_or_branch"
        result["message"] = "缺少 worktree 或 integration.branch"
        return result, task

    ver = task.get("verification") if isinstance(task.get("verification"), dict) else {}
    art = task.get("artifact") if isinstance(task.get("artifact"), dict) else {}
    bound_raw = ver.get("bound_commit")
    artifact_raw = art.get("commit")
    if not isinstance(bound_raw, str) or not bound_raw.strip():
        result["action"] = "missing_bound"
        result["message"] = "缺少 verification.bound_commit"
        return result, task

    bound_full = _rev_parse_commit(worktree, bound_raw)
    if not bound_full:
        result["action"] = "bound_unresolvable"
        result["message"] = f"git rev-parse 无法解析 bound: {bound_raw!r}"
        return result, task

    if isinstance(artifact_raw, str) and artifact_raw.strip():
        if not _git_commits_same(worktree, artifact_raw, bound_raw):
            result["action"] = "artifact_bound_mismatch"
            result["message"] = (
                f"产物与绑定经 git 解析后不一致: "
                f"artifact={artifact_raw!r} bound={bound_raw!r}"
            )
            return result, task

    # Idempotent: already on integration history
    integ_tip = _rev_parse_commit(worktree, integ)
    if integ_tip and _is_ancestor(worktree, bound_full, integ_tip):
        updated = dict(task)
        try:
            if updated.get("status") not in ("已完成",):
                updated = _ensure_待合并(updated, actor=actor)
                if updated.get("status") == "待合并":
                    updated = transition_task(
                        updated,
                        to_status="已完成",
                        actor=actor,
                        note=f"幂等：{integ} 已包含 {bound_full[:12]}，跳过重复 merge",
                    )
        except IllegalTransitionError as e:
            # already 已完成 or illegal — still report success for git state
            result["transition_note"] = str(e)

        merge_info = {
            "already_merged": True,
            "integration_before": integ_tip,
            "integration_after": integ_tip,
            "bound": bound_full,
            "method": "noop",
            "message": f"{integ} 已包含 bound，未重复合并",
        }
        updated = dict(updated)
        updated["merge"] = merge_info
        ev_rel = updated.get("evidence_dir")
        if isinstance(ev_rel, str) and ev_rel:
            ev_path = (project_root / ev_rel).resolve()
        elif tf:
            ev_path = tf.parent
        else:
            ev_path = project_root
        report_path = _write_merge_report(
            ev_path,
            {
                **merge_info,
                "task_id": updated.get("task_id"),
                "status": updated.get("status"),
            },
        )
        merge_info["report_path"] = str(report_path)
        updated["merge"] = merge_info
        result["ok"] = True
        result["exit_code"] = EXIT_OK
        result["action"] = "already_merged"
        result["merge"] = merge_info
        result["message"] = merge_info["message"]
        return result, updated

    # Prepare transition to 待合并
    try:
        updated = _ensure_待合并(dict(task), actor=actor)
    except IllegalTransitionError as e:
        result["action"] = "bad_status"
        result["message"] = str(e)
        return result, task

    orig_branch = _current_branch(worktree)
    orig_head = _rev_parse_commit(worktree, "HEAD")
    before = integ_tip

    # Checkout integration
    co = _run_git(worktree, "checkout", integ)
    if co.returncode != 0:
        result["action"] = "checkout_failed"
        result["message"] = f"checkout {integ} 失败: {(co.stderr or co.stdout).strip()}"
        return result, updated

    # Prefer FF, else merge --no-ff
    method = "ff"
    mg = _run_git(worktree, "merge", "--ff-only", bound_full)
    if mg.returncode != 0:
        method = "no-ff"
        mg = _run_git(
            worktree,
            "merge",
            "--no-ff",
            "--no-edit",
            "-m",
            f"merge {bound_full[:12]} for task {task.get('task_id')}",
            bound_full,
        )

    if mg.returncode != 0:
        # Conflict or other failure — abort and restore
        _run_git(worktree, "merge", "--abort")
        if orig_branch:
            _run_git(worktree, "checkout", orig_branch)
        elif orig_head:
            _run_git(worktree, "checkout", orig_head)

        merge_info = {
            "already_merged": False,
            "integration_before": before,
            "integration_after": _rev_parse_commit(worktree, integ),
            "bound": bound_full,
            "method": method,
            "error": (mg.stderr or mg.stdout).strip(),
            "conflict": True,
            "message": "合并冲突或失败；已 abort，禁止 force",
        }
        try:
            updated = transition_task(
                updated,
                to_status="合并失败",
                actor=actor,
                note=merge_info["message"],
            )
        except IllegalTransitionError:
            pass
        updated = dict(updated)
        updated["merge"] = merge_info
        ev_rel = updated.get("evidence_dir")
        ev_path = (
            (project_root / ev_rel).resolve()
            if isinstance(ev_rel, str) and ev_rel
            else (tf.parent if tf else project_root)
        )
        report_path = _write_merge_report(
            ev_path,
            {**merge_info, "task_id": updated.get("task_id"), "status": updated.get("status")},
        )
        merge_info["report_path"] = str(report_path)
        updated["merge"] = merge_info
        result["ok"] = False
        result["exit_code"] = EXIT_FAIL
        result["action"] = "conflict"
        result["merge"] = merge_info
        result["message"] = merge_info["message"]
        return result, updated

    after = _rev_parse_commit(worktree, "HEAD")
    merge_info: dict[str, Any] = {
        "already_merged": False,
        "integration_before": before,
        "integration_after": after,
        "bound": bound_full,
        "method": method,
        "orig_branch": orig_branch,
    }

    # Post-check: bound must be ancestor of new HEAD; optional path existence
    post_ok = bool(after) and _is_ancestor(worktree, bound_full, after)
    post_detail = (
        f"bound 是 integration HEAD 祖先（HEAD={after}）"
        if post_ok
        else f"post-check 失败：bound 未进入 integration（HEAD={after}）"
    )
    path_checks: list[dict[str, Any]] = []
    for rel in post_check_paths or []:
        p = worktree / rel
        exists = p.exists()
        path_checks.append({"path": rel, "ok": exists})
        if not exists:
            post_ok = False
            post_detail += f"；缺少文件 {rel}"
    merge_info["post_check"] = {"ok": post_ok, "detail": post_detail, "paths": path_checks}

    if not post_ok:
        # Git already merged — do not rewrite history; mark 合并失败
        if orig_branch and orig_branch != integ:
            _run_git(worktree, "checkout", orig_branch)
        try:
            updated = transition_task(
                updated,
                to_status="合并失败",
                actor=actor,
                note=f"git 已合并但后续检查失败: {post_detail}",
            )
        except IllegalTransitionError:
            pass
        updated = dict(updated)
        updated["merge"] = merge_info
        ev_rel = updated.get("evidence_dir")
        ev_path = (
            (project_root / ev_rel).resolve()
            if isinstance(ev_rel, str) and ev_rel
            else (tf.parent if tf else project_root)
        )
        report_path = _write_merge_report(
            ev_path,
            {
                **merge_info,
                "task_id": updated.get("task_id"),
                "status": updated.get("status"),
                "git_merged_but_post_failed": True,
            },
        )
        merge_info["report_path"] = str(report_path)
        updated["merge"] = merge_info
        result["ok"] = False
        result["exit_code"] = EXIT_FAIL
        result["action"] = "post_check_failed"
        result["merge"] = merge_info
        result["message"] = post_detail
        return result, updated

    # Success → 已完成; leave HEAD on integration (delivery tip) unless we restore
    # Restore feature branch checkout so developer worktree tip stays usable
    if orig_branch and orig_branch != integ:
        _run_git(worktree, "checkout", orig_branch)

    try:
        updated = transition_task(
            updated,
            to_status="已完成",
            actor=actor,
            note=f"已合入 {integ}（{method}）{bound_full[:12]} → {str(after)[:12] if after else '?'}",
        )
    except IllegalTransitionError as e:
        result["action"] = "transition_failed_after_merge"
        result["message"] = (
            f"git 已合并但状态迁移失败: {e}；integration_after={after}"
        )
        updated = dict(updated)
        updated["merge"] = merge_info
        result["ok"] = False
        result["exit_code"] = EXIT_FAIL
        result["merge"] = merge_info
        return result, updated

    updated = dict(updated)
    merge_info["message"] = f"已合入 {integ}（{method}）"
    updated["merge"] = merge_info
    ev_rel = updated.get("evidence_dir")
    ev_path = (
        (project_root / ev_rel).resolve()
        if isinstance(ev_rel, str) and ev_rel
        else (tf.parent if tf else project_root)
    )
    report_path = _write_merge_report(
        ev_path,
        {**merge_info, "task_id": updated.get("task_id"), "status": updated.get("status")},
    )
    merge_info["report_path"] = str(report_path)
    updated["merge"] = merge_info

    result["ok"] = True
    result["exit_code"] = EXIT_OK
    result["action"] = "merged"
    result["merge"] = merge_info
    result["message"] = merge_info["message"]
    return result, updated
