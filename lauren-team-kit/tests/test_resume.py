"""Lite L3: block / resume without duplicate artifact writes."""

from __future__ import annotations

from pathlib import Path

import pytest

from lauren_team_kit.protocol import create_task, load_task, save_task, transition_task
from lauren_team_kit.resume import BlockResumeError, block_task, resume_task
from lauren_team_kit.state_machine import ALLOWED, can_transition


def _path(root: Path, tid: str) -> Path:
    return root / "workspace" / "runs" / tid / "task.json"


def test_block_from_running_sets_blockers_and_resume(tmp_path: Path):
    create_task(title="t", task_id="b1", root=tmp_path)
    path = _path(tmp_path, "b1")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    blocked = block_task(
        task,
        code="KILL",
        message="模拟进程被杀",
        recovery_hint="重新拉起开发助手后 resume",
        resume_point="执行中",
        actor="chief",
    )
    assert blocked["status"] == "受阻"
    assert blocked["blockers"][-1]["code"] == "KILL"
    assert blocked["blockers"][-1]["recovery_hint"]
    assert blocked["resume"]["resume_point"] == "执行中"
    assert blocked["resume"]["interrupted_at"]
    assert "block code=KILL" in blocked["history"][-1]["note"]
    save_task(path, blocked)


@pytest.mark.parametrize(
    "point",
    ["执行中", "待验证", "待执行"],
)
def test_resume_to_stored_point(tmp_path: Path, point: str):
    create_task(title="t", task_id=f"r-{point}", root=tmp_path)
    path = _path(tmp_path, f"r-{point}")
    task = load_task(path)
    # Reach a blockable status: 待执行 is already ok; others need transition.
    if point == "执行中":
        task = transition_task(task, to_status="执行中", actor="chief")
    elif point == "待验证":
        task = transition_task(task, to_status="执行中", actor="chief")
        task = transition_task(task, to_status="待验证", actor="developer")
    # point == 待执行: already there
    blocked = block_task(
        task,
        code="ENV",
        message="缺依赖",
        recovery_hint="pip install …",
        resume_point=point,
        actor="chief",
    )
    assert blocked["status"] == "受阻"
    updated, report = resume_task(blocked, actor="chief")
    assert updated["status"] == point
    assert report["action"] == "resumed"
    assert report["to_status"] == point
    assert "resume →" in updated["history"][-1]["note"]


def test_illegal_resume_target_refused(tmp_path: Path):
    create_task(title="t", task_id="bad", root=tmp_path)
    path = _path(tmp_path, "bad")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    blocked = block_task(
        task,
        code="X",
        message="m",
        recovery_hint="h",
        resume_point="执行中",
        actor="chief",
    )
    with pytest.raises(BlockResumeError) as ei:
        resume_task(blocked, actor="chief", to_status="已完成")
    assert "非法恢复目标" in str(ei.value)
    # missing resume_point and no --to
    blocked2 = dict(blocked)
    blocked2["resume"] = {"interrupted_at": "t", "reason": "r"}
    with pytest.raises(BlockResumeError) as ei2:
        resume_task(blocked2, actor="chief")
    assert "resume_point" in str(ei2.value) or "缺失" in str(ei2.value)


def test_resume_keeps_artifact_and_reports_already_have(tmp_path: Path):
    create_task(title="t", task_id="art", root=tmp_path)
    path = _path(tmp_path, "art")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    sha = "abc1234deadbeef"
    task = dict(task)
    task["artifact"] = {"commit": sha, "summary": "already committed"}
    blocked = block_task(
        task,
        code="INTERRUPT",
        message="中断",
        recovery_hint="resume 即可，勿重提",
        resume_point="执行中",
        actor="chief",
    )
    assert blocked["resume"]["artifact_commit_at_interrupt"] == sha
    # artifact must survive block
    assert blocked["artifact"]["commit"] == sha
    updated, report = resume_task(blocked, actor="chief")
    assert updated["status"] == "执行中"
    assert updated["artifact"]["commit"] == sha  # not cleared
    assert report["already_have_artifact"] is True
    assert report["recommit_needed"] is False
    assert "already_have_artifact=true" in updated["history"][-1]["note"]


def test_resume_idempotent_when_not_blocked(tmp_path: Path):
    create_task(title="t", task_id="idemp", root=tmp_path)
    path = _path(tmp_path, "idemp")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    same, report = resume_task(task, actor="chief")
    assert same["status"] == "执行中"
    assert report["action"] == "noop_not_blocked"
    assert report["idempotent"] is True


def test_block_rejects_non_blockable(tmp_path: Path):
    create_task(title="t", task_id="nb", root=tmp_path)
    path = _path(tmp_path, "nb")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    # forge a verification-passing jump isn't needed; go via 需修改 path is hard.
    # Use status 验证通过 by direct mutation for this negative test only.
    task = dict(task)
    task["status"] = "已完成"
    with pytest.raises(BlockResumeError):
        block_task(
            task,
            code="X",
            message="m",
            recovery_hint="h",
            resume_point="执行中",
            actor="chief",
        )


def test_state_machine_blocked_edges():
    assert ALLOWED["受阻"] == frozenset({"待执行", "执行中", "待验证", "已取消"})
    for t in ("待执行", "执行中", "待验证", "已取消"):
        assert can_transition("受阻", t)
    assert not can_transition("受阻", "已完成")
    assert not can_transition("受阻", "验证通过")


def test_resume_no_interrupt_sha_no_recommit(tmp_path: Path):
    """无中断 SHA 时不应提示 recommit_needed（首次提交是正常工作）。"""
    create_task(title="t", task_id="nosh", root=tmp_path)
    path = _path(tmp_path, "nosh")
    task = load_task(path)  # 待执行，无可 block 的 artifact
    blocked = block_task(
        task,
        code="ENV",
        message="卡住",
        recovery_hint="修好再 resume",
        resume_point="待执行",
        actor="chief",
    )
    assert "artifact_commit_at_interrupt" not in blocked.get("resume", {})
    blocked.pop("artifact", None)
    updated, report = resume_task(blocked, actor="chief")
    assert report["already_have_artifact"] is False
    assert report["recommit_needed"] is False
    assert updated["status"] == "待执行"


def test_resume_recommit_when_artifact_lost(tmp_path: Path):
    create_task(title="t", task_id="lost", root=tmp_path)
    path = _path(tmp_path, "lost")
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief", note="go")
    task = dict(task)
    task["artifact"] = {"commit": "sha-before"}
    blocked = block_task(
        task,
        code="KILL",
        message="中断",
        recovery_hint="resume",
        resume_point="执行中",
        actor="chief",
    )
    assert blocked["resume"]["artifact_commit_at_interrupt"] == "sha-before"
    blocked = dict(blocked)
    blocked["artifact"] = {}
    updated, report = resume_task(blocked, actor="chief")
    assert report["already_have_artifact"] is False
    assert report["recommit_needed"] is True
    assert updated["status"] == "执行中"
