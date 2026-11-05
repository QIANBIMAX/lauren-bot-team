"""Lite L4: budget / timeout / retry hard gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lauren_team_kit.budget import (
    BUDGET_ATTEMPTS,
    BUDGET_DURATION,
    BUDGET_TOKENS,
    BudgetError,
    evaluate_budget,
    record_tokens,
    set_budget,
    transition_with_budget,
)
from lauren_team_kit.protocol import create_task, load_task, save_task, transition_task
from lauren_team_kit.resume import block_task, resume_task


def _path(root: Path, tid: str) -> Path:
    return root / "workspace" / "runs" / tid / "task.json"


def test_set_budget_and_check_ok(tmp_path: Path):
    create_task(title="t", task_id="b0", root=tmp_path)
    path = _path(tmp_path, "b0")
    task = load_task(path)
    task = set_budget(task, max_attempts=2, max_duration_sec=3600, actor="chief")
    assert task["budget"]["max_attempts"] == 2
    assert task["budget"]["attempts_used"] == 0
    report = evaluate_budget(task, pending_attempt=True)
    assert report["ok"] is True
    save_task(path, task)


def test_attempts_gate_blocks_on_third_enter(tmp_path: Path):
    create_task(title="t", task_id="b1", root=tmp_path)
    path = _path(tmp_path, "b1")
    task = load_task(path)
    task = set_budget(task, max_attempts=2, actor="chief")
    # 1st enter 执行中
    task, rep = transition_with_budget(task, to_status="执行中", actor="chief")
    assert task["status"] == "执行中"
    assert task["budget"]["attempts_used"] == 1
    assert rep and rep["ok"]
    # back via 需修改 path: 执行中 → 需修改 → 执行中
    task = transition_task(task, to_status="需修改", actor="verifier", note="fail")
    task, rep = transition_with_budget(task, to_status="执行中", actor="developer")
    assert task["status"] == "执行中"
    assert task["budget"]["attempts_used"] == 2
    task = transition_task(task, to_status="需修改", actor="verifier", note="fail2")
    # 3rd would exceed
    blocked, rep = transition_with_budget(task, to_status="执行中", actor="developer")
    assert blocked["status"] == "受阻"
    assert rep and rep["action"] == "blocked"
    assert any(v["code"] == BUDGET_ATTEMPTS for v in rep["violations"])
    assert blocked["blockers"][-1]["code"] == BUDGET_ATTEMPTS
    assert blocked["blockers"][-1]["recovery_hint"]
    assert blocked["resume"]["resume_point"] == "待执行"


def test_duration_gate(tmp_path: Path):
    create_task(title="t", task_id="b2", root=tmp_path)
    path = _path(tmp_path, "b2")
    task = load_task(path)
    task = set_budget(task, max_duration_sec=10, max_attempts=5, actor="chief")
    task, _ = transition_with_budget(task, to_status="执行中", actor="chief")
    assert task["status"] == "执行中"
    # forge old started_at
    task = dict(task)
    old = (datetime.now(timezone.utc) - timedelta(seconds=60)).astimezone().isoformat(
        timespec="seconds"
    )
    task["budget"] = dict(task["budget"])
    task["budget"]["started_at"] = old
    task = transition_task(task, to_status="需修改", actor="verifier")
    blocked, rep = transition_with_budget(task, to_status="执行中", actor="developer")
    assert blocked["status"] == "受阻"
    assert any(v["code"] == BUDGET_DURATION for v in rep["violations"])


def test_tokens_gate(tmp_path: Path):
    create_task(title="t", task_id="b3", root=tmp_path)
    path = _path(tmp_path, "b3")
    task = load_task(path)
    task = set_budget(task, max_tokens=100, max_attempts=5, actor="chief")
    task = record_tokens(task, tokens=80, actor="developer")
    assert task["budget"]["tokens_used"] == 80
    report = evaluate_budget(task)
    assert report["ok"] is True
    task = record_tokens(task, tokens=30, actor="developer")
    report = evaluate_budget(task, pending_attempt=True)
    assert report["ok"] is False
    assert any(v["code"] == BUDGET_TOKENS for v in report["violations"])
    blocked, rep = transition_with_budget(task, to_status="执行中", actor="chief")
    assert blocked["status"] == "受阻"
    assert blocked["blockers"][-1]["code"] == BUDGET_TOKENS


def test_no_budget_no_gate(tmp_path: Path):
    create_task(title="t", task_id="b4", root=tmp_path)
    path = _path(tmp_path, "b4")
    task = load_task(path)
    task, rep = transition_with_budget(task, to_status="执行中", actor="chief")
    assert task["status"] == "执行中"
    # no budget object → evaluate ok / no limits
    assert evaluate_budget(task)["ok"] is True


def test_refuse_without_autoblock(tmp_path: Path):
    create_task(title="t", task_id="b5", root=tmp_path)
    task = load_task(_path(tmp_path, "b5"))
    task = set_budget(task, max_attempts=1, actor="chief")
    task, _ = transition_with_budget(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="需修改", actor="verifier")
    with pytest.raises(BudgetError) as ei:
        transition_with_budget(
            task, to_status="执行中", actor="developer", auto_block=False
        )
    assert BUDGET_ATTEMPTS in str(ei.value)


def test_raise_requires_allow_raise(tmp_path: Path):
    create_task(title="t", task_id="b6", root=tmp_path)
    task = load_task(_path(tmp_path, "b6"))
    task = set_budget(task, max_attempts=2, actor="chief")
    with pytest.raises(BudgetError) as ei:
        set_budget(task, max_attempts=5, actor="chief")
    assert "allow-raise" in str(ei.value)
    # lower ok without flag
    task = set_budget(task, max_attempts=1, actor="chief")
    assert task["budget"]["max_attempts"] == 1
    # raise with flag
    task = set_budget(task, max_attempts=3, actor="chief", allow_raise=True)
    assert task["budget"]["max_attempts"] == 3
    # first-time other dimension ok without flag
    task = set_budget(task, max_tokens=100, actor="chief")
    assert task["budget"]["max_tokens"] == 100


def _over_token_blocked_with_resume_exec(tmp_path: Path, tid: str):
    """tokens 超限 + 受阻 + resume_point=执行中 的共用夹具。"""
    create_task(title="t", task_id=tid, root=tmp_path)
    path = _path(tmp_path, tid)
    task = load_task(path)
    task = set_budget(task, max_tokens=100, max_attempts=5, actor="chief")
    task = record_tokens(task, tokens=150, actor="developer")
    assert task["budget"]["tokens_used"] > task["budget"]["max_tokens"]
    # 进入执行中会被预算门挡住；先无预算态进执行中再记 token 后 block 更贴近探针场景
    # 这里直接从 待执行 block，resume_point=执行中
    blocked = block_task(
        task,
        code=BUDGET_TOKENS,
        message="token 超限（探针夹具）",
        recovery_hint="抬高 max_tokens 后 resume",
        resume_point="执行中",
        actor="chief",
    )
    assert blocked["status"] == "受阻"
    assert blocked["resume"]["resume_point"] == "执行中"
    save_task(path, blocked)
    return blocked, path


def test_resume_to_executing_refused_when_tokens_over_budget(tmp_path: Path):
    """L4: tokens 超限 + resume_point=执行中 → resume 不得进执行中。"""
    blocked, _ = _over_token_blocked_with_resume_exec(tmp_path, "rb1")
    updated, report = resume_task(blocked, actor="chief")
    assert updated["status"] == "受阻"
    assert report["action"] == "budget_blocked"
    assert any(v["code"] == BUDGET_TOKENS for v in report.get("violations") or [])
    assert updated["status"] != "执行中"


def test_resume_to_override_executing_refused_when_tokens_over(tmp_path: Path):
    """L4: --to 执行中（覆盖 resume_point）在超预算时同样拒。"""
    create_task(title="t", task_id="rb2", root=tmp_path)
    path = _path(tmp_path, "rb2")
    task = load_task(path)
    task = set_budget(task, max_tokens=50, max_attempts=5, actor="chief")
    task = record_tokens(task, tokens=80, actor="developer")
    # resume_point 存 待执行，但 --to 覆盖为 执行中
    blocked = block_task(
        task,
        code="ENV",
        message="环境",
        recovery_hint="修好",
        resume_point="待执行",
        actor="chief",
    )
    updated, report = resume_task(blocked, actor="chief", to_status="执行中")
    assert updated["status"] == "受阻"
    assert report["action"] == "budget_blocked"
    assert any(v["code"] == BUDGET_TOKENS for v in report.get("violations") or [])


def test_resume_to_executing_refused_hard_without_autoblock(tmp_path: Path):
    """L4: auto_block=False 时超预算 resume→执行中 抛 BudgetError。"""
    blocked, _ = _over_token_blocked_with_resume_exec(tmp_path, "rb3")
    with pytest.raises(BudgetError) as ei:
        resume_task(blocked, actor="chief", auto_block=False)
    assert BUDGET_TOKENS in str(ei.value)


def test_resume_to_executing_ok_within_budget(tmp_path: Path):
    """L4: 合法预算下 resume 仍可回执行中。"""
    create_task(title="t", task_id="rb4", root=tmp_path)
    path = _path(tmp_path, "rb4")
    task = load_task(path)
    task = set_budget(task, max_tokens=200, max_attempts=5, actor="chief")
    task = record_tokens(task, tokens=50, actor="developer")
    task, _ = transition_with_budget(task, to_status="执行中", actor="chief")
    assert task["status"] == "执行中"
    assert task["budget"]["attempts_used"] == 1
    blocked = block_task(
        task,
        code="KILL",
        message="中断",
        recovery_hint="resume",
        resume_point="执行中",
        actor="chief",
    )
    updated, report = resume_task(blocked, actor="chief")
    assert report["action"] == "resumed"
    assert updated["status"] == "执行中"
    # 再次进入执行中应记一轮 attempt
    assert updated["budget"]["attempts_used"] == 2


def test_resume_to_pending_not_hurt_by_over_budget(tmp_path: Path):
    """恢复到 待执行 / 待验证 不受执行中预算门误伤。"""
    create_task(title="t", task_id="rb5", root=tmp_path)
    path = _path(tmp_path, "rb5")
    task = load_task(path)
    task = set_budget(task, max_tokens=10, max_attempts=5, actor="chief")
    task = record_tokens(task, tokens=99, actor="developer")
    blocked = block_task(
        task,
        code="ENV",
        message="缺依赖",
        recovery_hint="装好",
        resume_point="待执行",
        actor="chief",
    )
    updated, report = resume_task(blocked, actor="chief")
    assert report["action"] == "resumed"
    assert updated["status"] == "待执行"

    # 待验证路径
    create_task(title="t", task_id="rb5b", root=tmp_path)
    path2 = _path(tmp_path, "rb5b")
    task2 = load_task(path2)
    task2 = set_budget(task2, max_tokens=10, max_attempts=5, actor="chief")
    task2 = record_tokens(task2, tokens=99, actor="developer")
    # 需要先到 待验证 再 block；用 transition 无预算进执行中会失败，直接造状态
    # 先清预算再走状态，再把超限预算挂回去
    task2 = dict(task2)
    task2.pop("budget", None)
    task2 = transition_task(task2, to_status="执行中", actor="chief")
    task2 = transition_task(task2, to_status="待验证", actor="developer")
    task2 = set_budget(task2, max_tokens=10, max_attempts=5, actor="chief")
    task2 = record_tokens(task2, tokens=99, actor="developer")
    blocked2 = block_task(
        task2,
        code="ENV",
        message="缺依赖",
        recovery_hint="装好",
        resume_point="待验证",
        actor="chief",
    )
    updated2, report2 = resume_task(blocked2, actor="chief")
    assert report2["action"] == "resumed"
    assert updated2["status"] == "待验证"
