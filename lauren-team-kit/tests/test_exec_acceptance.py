"""W1: structured acceptance argv/cwd/env/timeout and legacy shell type."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from lauren_team_kit.exec_run import (
    acceptance_fingerprint,
    command_kind,
    prepare_argv,
    resolve_interpreter,
    run_acceptance_item,
    run_must_run_round,
    select_posix_shell,
)
from lauren_team_kit.protocol import create_task, load_task, save_task, task_path_for, validate_task
from lauren_team_kit.verify_gate import evaluate_verify_gate


def _argv_item(argv: list[str], **extra: object) -> dict:
    spec: dict = {"kind": "argv", "argv": argv, "timeout_sec": 30}
    spec.update(extra)
    return {
        "id": "A",
        "description": "probe",
        "command": "python",
        "must_run": True,
        "pass_criteria": "exit_code==0",
        "exec": spec,
    }


def test_default_acceptance_is_argv_not_venv_shell(tmp_path: Path) -> None:
    task = create_task(title="demo", task_id="exec-default", root=tmp_path)
    item = task["acceptance"][0]
    assert item["exec"]["kind"] == "argv"
    assert item["exec"]["cwd"] == "demo-app"
    assert "{python}" in item["exec"]["argv"]
    assert "&&" not in item["command"]
    assert ".venv/bin/python" not in item["command"]
    assert validate_task(task) == []
    source = inspect.getsource(resolve_interpreter)
    assert ".venv/bin/python" not in source
    resolved = resolve_interpreter()
    assert Path(resolved).is_file()
    assert resolved != "python3"


def test_prepare_argv_uses_real_interpreter() -> None:
    argv, interp = prepare_argv(["{python}", "-c", "pass"])
    assert argv[0] == interp
    assert Path(interp).is_file()
    bare, interp2 = prepare_argv(["python3", "-c", "pass"])
    assert bare[0] == interp2


def test_legacy_shell_is_not_split_and_windows_skips_git_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = "cd demo-app && .venv/bin/python -m pytest -q"
    item = {
        "id": "LEGACY",
        "description": "old",
        "command": command,
        "must_run": True,
        "pass_criteria": "exit_code==0",
    }
    assert command_kind(item) == "shell"
    seen: dict = {}

    class Dummy:
        pid = 4321
        returncode = 0

        def poll(self) -> int:
            return 0

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "ok\n", ""

    def fake_popen(argv: list[str], **kwargs: object) -> Dummy:
        seen["argv"] = argv
        seen["cwd"] = kwargs.get("cwd")
        seen["env"] = kwargs.get("env")
        return Dummy()

    monkeypatch.setattr("lauren_team_kit.exec_run.subprocess.Popen", fake_popen)
    # Force the POSIX branch even on Windows CI, where the host itself must
    # refuse shell. The fake Popen only records argv.
    ran = run_acceptance_item(item, base=tmp_path, platform="linux")
    assert ran["outcome"] == "exit"
    assert ran["split_attempted"] is False
    assert ran["command_type"] == "shell"
    assert ran["argv"] is not None
    assert ran["argv"][1:] == ["-c", command]
    assert "&&" in ran["argv"][-1]
    assert seen["cwd"] == str(tmp_path.resolve())
    assert isinstance(seen["env"], dict)

    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("Windows shell must not start a process")

    monkeypatch.setattr("lauren_team_kit.exec_run.subprocess.Popen", refuse)
    blocked = run_acceptance_item(item, base=tmp_path, platform="win32", environ={})
    assert blocked["outcome"] == "start_fail"
    assert blocked["executed"] is False
    assert "Git Bash" in (blocked["reason"] or "")
    assert select_posix_shell(
        platform="win32",
        environ={},
        which=lambda _name: r"C:\Program Files\Git\bin\bash.exe",
        is_file=lambda _p: True,
    ) is None


def test_argv_cwd_env_empty_and_special_args(tmp_path: Path) -> None:
    work = tmp_path / "任务 目录"
    work.mkdir()
    expected = str(work.resolve())
    item = _argv_item(
        [
            "{python}",
            "-c",
            "import os,sys; raise SystemExit(0 if os.getcwd()==sys.argv[1] and sys.argv[2]=='' and sys.argv[3]=='a&b' and os.environ.get('LAUREN_ACCEPT')=='1' else 4)",
            expected,
            "",
            "a&b",
        ],
        cwd=expected,
        env={"LAUREN_ACCEPT": "1", "API_TOKEN": "sk-super-secret"},
    )
    result = run_acceptance_item(item, base=tmp_path)
    assert result["outcome"] == "exit", result
    assert result["exit_code"] == 0
    assert result["cwd"] == expected
    assert result["env"]["API_TOKEN"] == "***"
    assert "sk-super-secret" not in json.dumps(result)
    assert "a&b" in (result["argv"] or [])
    assert "" in (result["argv"] or [])


def test_outcomes_nonzero_timeout_cancel_start_fail_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = run_acceptance_item(
        _argv_item(["{python}", "-c", "import sys; sys.exit(3)"]),
        base=tmp_path,
    )
    assert bad["outcome"] == "nonzero"
    assert bad["exit_code"] == 3

    missing = run_acceptance_item(
        _argv_item(["definitely-missing-bin-xyz"]),
        base=tmp_path,
    )
    assert missing["outcome"] == "start_fail"
    assert missing["executed"] is False

    marker = tmp_path / "should-not-run"
    cancelled = run_acceptance_item(
        _argv_item(
            [
                "{python}",
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('x')",
                str(marker),
            ]
        ),
        base=tmp_path,
        cancel=lambda: True,
    )
    assert cancelled["outcome"] == "cancel"
    assert cancelled["cancel_tree"] == "not_started"
    assert not marker.exists()

    timed = run_acceptance_item(
        _argv_item(["{python}", "-c", "import time; time.sleep(30)"], timeout_sec=1),
        base=tmp_path,
    )
    assert timed["outcome"] == "timeout"
    assert timed["exit_code"] is None
    assert timed["cancel_tree"] in ("posix_process_group", "direct_child_only")

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("lauren_team_kit.exec_run.subprocess.Popen", boom)
    unknown = run_acceptance_item(_argv_item(["{python}", "-c", "print(1)"]), base=tmp_path)
    assert unknown["outcome"] == "unknown"


def test_one_round_two_must_run_and_stale_fingerprint(tmp_path: Path) -> None:
    create_task(title="round", task_id="exec-round", root=tmp_path)
    path = task_path_for(tmp_path, "exec-round")
    task = load_task(path)
    task["acceptance"] = [
        _argv_item(["{python}", "-c", "import sys; sys.exit(0)"]),
        {
            **_argv_item(["{python}", "-c", "import sys; sys.exit(2)"]),
            "id": "B",
        },
    ]
    updated, summary = run_must_run_round(task, base=tmp_path)
    assert summary["ok"] is False
    assert summary["round_id"]
    checks = updated["verification"]["checks"]
    assert {c["acceptance_id"] for c in checks} == {"A", "B"}
    assert len({c["round_id"] for c in checks}) == 1
    assert updated["verification"]["result"] == "fail"
    assert updated["verification"]["acceptance_fingerprint"] == acceptance_fingerprint(
        task["acceptance"]
    )

    task["acceptance"] = [
        _argv_item(["{python}", "-c", "import sys; sys.exit(0)"]),
        {**_argv_item(["{python}", "-c", "import sys; sys.exit(0)"]), "id": "B"},
    ]
    passed, summary_ok = run_must_run_round(task, base=tmp_path)
    assert summary_ok["ok"] is True
    assert summary_ok["failed_ids"] == []
    assert len({c["round_id"] for c in passed["verification"]["checks"]}) == 1
    assert all(c["outcome"] == "exit" and c["exit_code"] == 0 for c in passed["verification"]["checks"])

    stale = dict(passed)
    verification = dict(stale["verification"])
    verification["acceptance_fingerprint"] = "ffff"
    verification["result"] = "pass"
    verification["bound_commit"] = "abc1234"
    verification["trust"] = "verified_run"
    checks = []
    for row in verification["checks"]:
        copied = dict(row)
        copied["acceptance_fingerprint"] = "eeee"
        checks.append(copied)
    verification["checks"] = checks
    stale["verification"] = verification
    stale["artifact"] = {"commit": "abc1234"}
    stale["status"] = "验证通过"
    errors = evaluate_verify_gate(stale)
    assert errors
    assert any("A" in err or "B" in err for err in errors)
    save_task(path, passed)
    assert validate_task(load_task(path)) == []
