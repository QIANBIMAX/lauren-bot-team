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
