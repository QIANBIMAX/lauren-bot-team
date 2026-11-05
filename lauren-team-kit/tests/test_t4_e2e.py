"""T4 E2E (mode=simulated / omb_delegation=blocked): lessons + chain + Nancy + routing.

Does NOT replace t1_dual_task_smoke.sh (old protocol/status). Kit-local paths only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lauren_team_kit.authz import AuthzError
from lauren_team_kit.handoff import (
    ack_handoff,
    assert_handoff_ready,
    eng_decompose,
    eng_handoff_developer,
    mark_handoff_status,
    record_local_developer_commit,
    start_rework,
)
from lauren_team_kit.lessons import (
    LessonError,
    add_candidate,
    evaluate_recurrence,
    load_from_store,
    publish_candidate,
    record_recurrence,
    record_rule_load,
    record_rule_receive,
    review_candidate,
)
from lauren_team_kit.merge import execute_merge
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    record_check,
    save_task,
    set_artifact_commit,
    task_path_for,
    transition_task,
)
from lauren_team_kit.team import (
    add_child_task,
    add_team_todo,
    assign_task,
    create_team,
    list_team_todos,
    load_team,
    save_team,
    summarize_team,
    team_path_for,
)
from _seed import seed_trusted_pass


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "workspace" / "runs").mkdir(parents=True)
    (tmp_path / "lauren-team-kit" / "rules").mkdir(parents=True)
    (tmp_path / "lauren-team-kit" / "lessons" / "store").mkdir(parents=True)
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


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip()


def _seed_team(root: Path, team_id: str = "t4") -> None:
    create_team(root=root, team_id=team_id, title="T4", force=True)


def _chain_to_verify(
    root: Path,
    *,
    team_id: str,
    task_id: str,
    eng: str = "Eng-A",
    title: str = "pkg",
    fail_first: bool = False,
) -> dict:
    """Matcha→Eng→handoff→ack→local commit→independent verify (+optional rework).

    mode=simulated — no real OMB multi-assistant.
    """
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
    aid = f"ACC-{task_id}"
    eng_decompose(
        root=root,
        team_id=team_id,
        task_id=task_id,
        actor=eng,
        goal=title,
        in_scope=[f"implement {task_id}"],
        acceptance=_acc(aid),
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

    if fail_first:
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
            note="rework",
        )
        hid = handoff2["handoff_id"]
        ack_handoff(
            root=root,
            team_id=team_id,
            handoff_id=hid,
            actor="developer",
            run_id=f"run-{task_id}-rework",
        )
        commit = (commit[::-1])[:40]
        record_local_developer_commit(
            root=root,
            team_id=team_id,
            task_id=task_id,
            handoff_id=hid,
            commit=commit,
            actor="developer",
        )
        task = set_artifact_commit(
            load_task(path),
            commit=commit,
            actor="developer",
            role="developer",
            root=root,
        )
        save_task(path, task)

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
        "mode": "simulated",
        "omb_delegation": "blocked",
    }


def test_t4_normal_complete_chain(root: Path) -> None:
    """正常完成：engineering_chain Matcha→Eng→handoff→ack→commit→独立验收."""
    _seed_team(root)
    out = _chain_to_verify(
        root, team_id="t4", task_id="t4-ok", eng="Eng-A", title="正常包"
    )
    assert out["task"]["verification"]["result"] == "pass"
    assert out["mode"] == "simulated"
    assert out["omb_delegation"] == "blocked"
    team = load_team(team_path_for(root, "t4"))
    assert any(h.get("handoff_id") == out["handoff_id"] for h in team["handoffs"])


def test_t4_fail_then_rework_pass(root: Path) -> None:
    """首次失败后修复：verify fail → rework → 新轮独立验收 pass."""
    _seed_team(root)
    out = _chain_to_verify(
        root,
        team_id="t4",
        task_id="t4-fix",
        eng="Eng-A",
        title="修复包",
        fail_first=True,
    )
    assert out["task"]["verification"]["result"] == "pass"
    team = load_team(team_path_for(root, "t4"))
    assert len([h for h in team["handoffs"] if h.get("task_id") == "t4-fix"]) >= 2


def test_t4_lesson_anti_recurrence(root: Path) -> None:
    """规则防复发：发布带探针 lesson → 加载回执 → 假回归探针仍 fail → recurrence_blocked."""
    _seed_team(root)
    create_task(title="lesson host", task_id="t4-les", root=root)
    path = task_path_for(root, "t4-les")
    task = load_task(path)
    task = add_candidate(
        task,
        lesson_id="t4-empty-guard",
        summary="空输入必须 []",
        actor="developer",
        rule_body="# t4-empty-guard\n空输入必须返回 []\n",
        scope={"task_kind": "filter"},
        probe={"ref": "t4-empty-probe", "description": "empty→[]", "expected": "[]"},
    )
    with pytest.raises(LessonError, match="探针|证据|probe"):
        review_candidate(task, "t4-empty-guard", approved=True, actor="verifier")
    task = review_candidate(
        task,
        "t4-empty-guard",
        approved=True,
        actor="verifier",
        probe_result={
            "probe_id": "t4-empty-probe",
            "passed": True,
            "stdout_summary": "[]",
            "evidence": "checks/t4-empty.log",
            "at": "2026-11-05T11:00:00+08:00",
        },
    )
    task, record = publish_candidate(task, "t4-empty-guard", root=root, actor="chief")
    loaded = load_from_store(root, "t4-empty-guard")
    assert loaded["rules_version"] == record["rules_version"]
    assert loaded["content_hash"] == record["content_hash"]
    rule_text = (root / record["rule_path"]).read_text(encoding="utf-8")
    assert record["rules_version"] in rule_text

    team = load_team(team_path_for(root, "t4"))
    team = record_rule_load(
        team,
        eng="Eng-A",
        lesson_id="t4-empty-guard",
        rules_version=record["rules_version"],
        actor="Eng-A",
    )
    team = record_rule_receive(
        team,
        developer="developer",
        lesson_id="t4-empty-guard",
        rules_version=record["rules_version"],
        actor="developer",
    )
    save_team(team_path_for(root, "t4"), team)
    assert any(r["kind"] == "load" for r in team["rule_receipts"])
    assert any(r["kind"] == "receive" for r in team["rule_receipts"])

    rec = evaluate_recurrence(
        root,
        "t4-empty-guard",
        probe_result={
            "probe_id": "t4-empty-probe",
            "passed": False,
            "stdout_summary": "TypeError: NoneType",
        },
    )
    assert rec["recurrence_blocked"] is True
    assert rec["rule_check"] == "hit"
    task = record_recurrence(task, rec, actor="verifier")
    save_task(path, task)
    assert task["recurrence_events"][-1]["recurrence_blocked"] is True


def test_t4_old_sha_stale_verification_rejected(root: Path) -> None:
    """旧 SHA/旧验收拒绝：HEAD 漂移后 merge precheck 拒（沿用 T1 行为）."""
    task_id = "t4-stale"
    create_task(title="stale", task_id=task_id, root=root)
    path = task_path_for(root, task_id)
    task = load_task(path)
    wt = root / task["worktree"]["path"]
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

    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    task = seed_trusted_pass(task, commit=feature)
    task["artifact"] = {"commit": feature}
    task = transition_task(task, to_status="验证通过", actor="verifier")
    task = transition_task(task, to_status="待合并", actor="chief")
    save_task(path, task)

    # drift HEAD after verification (旧验收)
    (wt / "extra.txt").write_text("x\n", encoding="utf-8")
    _git(wt, "add", "extra.txt")
    _git(wt, "commit", "-m", "drift")

    result, updated = execute_merge(
        load_task(path), root=root, task_file=path, confirm=True
    )
    assert result["ok"] is False
    assert result["action"] in ("precheck_failed", "artifact_bound_mismatch")
    assert updated.get("status") != "已完成"


def test_t4_failed_post_check_retry_not_auto_success(root: Path) -> None:
    """失败 post-check 重试不得自动成功（already_merged 拒未验收/拒坏后置）."""
    task_id = "t4-post"
    create_task(title="post fail", task_id=task_id, root=root)
    path = task_path_for(root, task_id)
    task = load_task(path)
    wt = root / task["worktree"]["path"]
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
    task["status"] = "待合并"
    task["artifact"] = {"commit": feature}
    task["verification"] = {
        "result": "fail",
        "bound_commit": feature,
        "checks": [],
    }
    # Prior failed post_check recorded
    task["merge"] = {
        "post_check": {"ok": False, "detail": "缺少文件 missing.txt", "paths": []}
    }
    save_task(path, task)

    result, updated = execute_merge(
        load_task(path),
        root=root,
        task_file=path,
        confirm=True,
        post_check_paths=["does-not-exist-post.txt"],
    )
    assert result["ok"] is False
    assert updated.get("status") != "已完成"
    assert result["action"] in (
        "already_in_integration_rejected",
        "post_check_failed",
        "precheck_failed",
    )


def test_t4_nancy_restart_todos(root: Path) -> None:
    """Nancy 重启汇报：todo 写入 → reload → 仍在 + summarize."""
    _seed_team(root)
    add_team_todo(
        root=root, team_id="t4", text="跟进 t4 待合并", by="Nancy", source="user"
    )
    # simulate restart: reload from disk
    todos = list_team_todos(root=root, team_id="t4", by="Nancy")
    assert any("待合并" in (t.get("text") or "") for t in todos)
    team2 = load_team(team_path_for(root, "t4"))
    assert team2.get("todos")
    summary = summarize_team(root=root, team_id="t4", by="Nancy")
    assert summary["counts"]["open_todos"] >= 1


def test_t4_default_route_rejects_chief_direct(root: Path) -> None:
    """默认路由拒绝直派：engineering_chain 下 chief 无 handoff 直推 developer 产物 → 拒."""
    _seed_team(root)
    add_child_task(root=root, team_id="t4", task_id="t4-bypass", title="X", force=True)
    assign_task(
        root=root, team_id="t4", task_id="t4-bypass", assignee="Eng-A", by="Matcha"
    )
    path = task_path_for(root, "t4-bypass")
    task = load_task(path)
    with pytest.raises(AuthzError, match="engineering_chain|绕过"):
        set_artifact_commit(
            task, commit="c" * 40, actor="幕僚长", role="chief", root=root
        )


def test_t4_fast_path_allows_small_task(root: Path) -> None:
    """启用 fast_path 的合法小任务：显式 mode+enabled+reason 后绕过 handoff 门."""
    _seed_team(root)
    tpath = team_path_for(root, "t4")
    team = load_team(tpath)
    team["routing_policy"] = {
        "mode": "fast_path",
        "fast_path_enabled": True,
        "fast_path_reason": "单行文案 typo",
    }
    save_team(tpath, team)
    add_child_task(root=root, team_id="t4", task_id="t4-fp", title="typo", force=True)
    ready = assert_handoff_ready(root=root, team_id="t4", task_id="t4-fp")
    assert ready["ok"] is True
    assert ready.get("bypassed") == "fast_path"

    path = task_path_for(root, "t4-fp")
    task = load_task(path)
    # chief may drive small path under explicit fast_path
    task = transition_task(
        task, to_status="执行中", actor="幕僚长", role="chief", root=root
    )
    task = set_artifact_commit(
        task, commit="e" * 40, actor="developer", role="developer", root=root
    )
    assert task["artifact"]["commit"] == "e" * 40


def test_t4_lite_still_direct(root: Path) -> None:
    """Lite 回归仍可直派：无 team 的独立任务 chief/developer 仍可工作."""
    create_task(title="lite", task_id="t4-lite", root=root)
    path = task_path_for(root, "t4-lite")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief", role="chief", root=root)
    task = set_artifact_commit(
        task, commit="f" * 40, actor="developer", role="developer", root=root
    )
    assert task["artifact"]["commit"] == "f" * 40
