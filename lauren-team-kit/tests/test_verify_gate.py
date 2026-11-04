"""Hard gate for → 验证通过 and CLI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lauren_team_kit.cli import main
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    record_check,
    save_task,
    transition_task,
    validate_task,
)
from lauren_team_kit.verify_gate import (
    VerifyGateError,
    commits_match,
    evaluate_verify_gate,
    gate_report,
)


def _to_pending_verify(tmp_path: Path, task_id: str = "g1") -> Path:
    create_task(title="gate demo", task_id=task_id, root=tmp_path)
    path = tmp_path / "workspace" / "runs" / task_id / "task.json"
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer")
    save_task(path, task)
    return path


def test_transition_to_verified_without_checks_fails(tmp_path: Path):
    path = _to_pending_verify(tmp_path)
    task = load_task(path)
    with pytest.raises(VerifyGateError) as ei:
        transition_task(task, to_status="验证通过", actor="verifier")
    msg = str(ei.value)
    assert "验证硬门" in msg
    assert "A1" in msg
    # status unchanged on disk
    assert load_task(path)["status"] == "待验证"


def test_transition_succeeds_after_record_check(tmp_path: Path):
    path = _to_pending_verify(tmp_path, task_id="g2")
    task = load_task(path)
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit="deadbeef",
        artifact_commit="deadbeef",
        result="pass",
    )
    save_task(path, task)
    assert evaluate_verify_gate(task) == []
    updated = transition_task(task, to_status="验证通过", actor="verifier")
    assert updated["status"] == "验证通过"
    save_task(path, updated)
    errors = validate_task(load_task(path))
    assert errors == [], errors


def test_verify_gate_cli_exit_codes(tmp_path: Path, capsys):
    path = _to_pending_verify(tmp_path, task_id="g3")
    root = str(tmp_path)
    rc = main(
        [
            "verify-gate",
            "--task-id",
            "g3",
            "--root",
            root,
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "FAIL" in err or "A1" in err

    task = load_task(path)
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit="abc1234",
        artifact_commit="abc1234",
        result="pass",
    )
    save_task(path, task)
    rc2 = main(["verify-gate", "--task-id", "g3", "--root", root])
    assert rc2 == 0
    out = capsys.readouterr().out
    assert "PASS" in out


def test_strict_verify_flag(tmp_path: Path):
    path = _to_pending_verify(tmp_path, task_id="g4")
    task = load_task(path)
    # without strict: 待验证 is fine structurally
    assert validate_task(task) == []
    errs = validate_task(task, strict_verify=True)
    assert errs, "strict_verify should fail without checks"
    assert any("A1" in e or "verification" in e for e in errs)


def test_executed_false_blocks(tmp_path: Path):
    path = _to_pending_verify(tmp_path, task_id="g5")
    task = load_task(path)
    task = record_check(
        task,
        acceptance_id="A1",
        executed=False,
        exit_code=1,
        bound_commit="x",
        artifact_commit="x",
        result="pass",
    )
    report = gate_report(task)
    assert report["ok"] is False
    assert any("executed" in e for e in report["errors"])


def test_commits_match_short_long():
    full = "deadbeefcafebabe0123456789abcdef01234567"
    assert commits_match(full, "deadbee")
    assert commits_match("deadbee", full)
    assert commits_match("abc", "abc")
    assert not commits_match("", "deadbeef")
    assert not commits_match("deadbeef", "c0ffee00")
    assert not commits_match("ab", "abcdef0")  # shorter < 7


def test_commit_mismatch_fails(tmp_path: Path):
    path = _to_pending_verify(tmp_path, task_id="g-mismatch")
    task = load_task(path)
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit="deadbeef",
        artifact_commit="c0ffee00",
        result="pass",
    )
    errors = evaluate_verify_gate(task)
    assert errors
    assert any("不一致" in e for e in errors)


def test_exit_code_nonzero_fails(tmp_path: Path):
    path = _to_pending_verify(tmp_path, task_id="g-exit")
    task = load_task(path)
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=1,
        bound_commit="deadbeef",
        artifact_commit="deadbeef",
        result="pass",
    )
    errors = evaluate_verify_gate(task)
    assert errors
    assert any("exit_code" in e for e in errors)


def test_matching_commits_and_exit_zero_pass(tmp_path: Path):
    path = _to_pending_verify(tmp_path, task_id="g-ok")
    task = load_task(path)
    full = "abcdef0123456789abcdef0123456789abcdef01"
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit=full,
        artifact_commit="abcdef0",
        result="pass",
    )
    assert evaluate_verify_gate(task) == []


def test_check_result_fail_blocks(tmp_path: Path):
    path = _to_pending_verify(tmp_path, task_id="g-cres")
    task = load_task(path)
    task = record_check(
        task,
        acceptance_id="A1",
        executed=True,
        exit_code=0,
        bound_commit="deadbeef",
        artifact_commit="deadbeef",
        result="pass",
    )
    # Inject check-level result=fail
    checks = task["verification"]["checks"]
    checks[0]["result"] = "fail"
    errors = evaluate_verify_gate(task)
    assert any("check.result" in e for e in errors)
