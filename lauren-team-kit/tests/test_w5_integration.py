"""W5: Lite/Team gates stay as strict as macOS; concurrent writes; no fake delegate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from lauren_team_kit.authz import AuthzError
from lauren_team_kit.handoff import omb_delegate
from lauren_team_kit.protocol import create_task, load_task, task_path_for, transition_task
from lauren_team_kit.verify_gate import VerifyGateError, evaluate_verify_gate


def _env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / "src")
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not prev else src + os.pathsep + prev
    return env


def test_verify_permission_is_not_relaxed(tmp_path: Path) -> None:
    task = create_task(title="权限", task_id="w5-auth", root=tmp_path)
    task = transition_task(task, to_status="执行中", actor="chief")
    task = transition_task(task, to_status="待验证", actor="developer", role="developer")
    try:
        transition_task(task, to_status="验证通过", actor="developer", role="developer")
        raise AssertionError("developer 不得标验证通过")
    except (AuthzError, VerifyGateError):
        pass
    errors = evaluate_verify_gate(task)
    assert errors
    assert task["merge_policy"]["mode"] == "confirm"


def test_two_processes_do_not_drop_task_notes(tmp_path: Path) -> None:
    create_task(title="并发", task_id="w5-race", root=tmp_path)
    path = task_path_for(tmp_path, "w5-race")
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "lauren_team_kit.lock_probe",
                "notes",
                str(path),
                prefix,
                "15",
            ],
            env=_env(),
        )
        for prefix in ("left", "right")
    ]
    for proc in procs:
        proc.wait(timeout=30)
        assert proc.returncode == 0
    notes = [row.get("note") for row in load_task(path)["history"]]
    expected = [f"left-{i}" for i in range(15)] + [f"right-{i}" for i in range(15)]
    for note in expected:
        assert note in notes


def test_delegate_stays_blocked_and_gates_have_no_platform_escape() -> None:
    result = omb_delegate(actor="system")
    assert result["ok"] is False
    assert result["omb_delegation"] == "blocked"
    assert result["mode"] == "simulated"
    assert result["mode"] != "real"
    root = Path(__file__).resolve().parents[1] / "src" / "lauren_team_kit"
    for name in ("verify_gate.py", "authz.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "sys.platform" not in text
    runtime = (root / "runtime.py").read_text(encoding="utf-8")
    assert "windows_incomplete" in runtime
