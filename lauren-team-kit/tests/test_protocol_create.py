import json
from pathlib import Path

import pytest

from lauren_team_kit.evidence import ensure_evidence_dir
from lauren_team_kit.protocol import (
    create_task,
    load_task,
    transition_task,
    validate_task,
)
from lauren_team_kit.state_machine import IllegalTransitionError


def test_create_and_validate(tmp_path: Path):
    task = create_task(
        title="demo filter smoke",
        task_id="demo-c1",
        root=tmp_path,
    )
    assert task["status"] == "待执行"
    assert task["schema_version"] == "lauren-task-protocol/0.1"
    assert task["merge_policy"]["mode"] == "confirm"
    assert task["roles"]["chief"] == "幕僚长"
    path = tmp_path / "workspace" / "runs" / "demo-c1" / "task.json"
    assert path.is_file()
    for sub in ("logs", "artifacts", "checks"):
        assert (tmp_path / "workspace" / "runs" / "demo-c1" / sub / ".gitkeep").is_file()
    errors = validate_task(load_task(path))
    assert errors == [], errors


def test_transition_and_illegal(tmp_path: Path):
    create_task(title="t", task_id="t1", root=tmp_path)
    path = tmp_path / "workspace" / "runs" / "t1" / "task.json"
    task = load_task(path)
    task = transition_task(task, to_status="执行中", actor="chief")
    assert task["status"] == "执行中"
    assert task["history"][-1]["from"] == "待执行"
    with pytest.raises(IllegalTransitionError):
        transition_task(task, to_status="已完成", actor="chief")


def test_init_evidence_idempotent(tmp_path: Path):
    a = ensure_evidence_dir(tmp_path, "x")
    b = ensure_evidence_dir(tmp_path, "x")
    assert a == b
    assert (a / "logs" / ".gitkeep").is_file()
