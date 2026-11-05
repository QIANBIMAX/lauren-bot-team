"""Rule probes: structured argv by default, Bash only when explicitly supported.

Markdown ``## 验收探针`` blocks are ``requires_bash``. When Bash is not a
capable POSIX shell, those probes return ``cannot_run`` and are not a pass.
Windows does not search Git Bash. ``## 结构化探针`` JSON runs through the W1
argv runner.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

from lauren_team_kit.exec_run import run_acceptance_item


def parse_probes(rule_path: Path) -> list[str]:
    text = rule_path.read_text(encoding="utf-8")
    match = re.search(r"## 验收探针.*?```(?:bash)?\n(.*?)```", text, re.S)
    if not match:
        return []
    return [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.startswith("#")
    ]


def parse_structured_probes(rule_path: Path) -> list[dict[str, Any]]:
    text = rule_path.read_text(encoding="utf-8")
    match = re.search(r"## 结构化探针\s*```json\n(.*?)```", text, re.S)
    if not match:
        return []
    data = json.loads(match.group(1))
    if isinstance(data, dict):
        probes = data.get("probes") or []
    elif isinstance(data, list):
        probes = data
    else:
        probes = []
    return [row for row in probes if isinstance(row, dict)]


def rule_requires_bash(rule_path: Path) -> bool:
    text = rule_path.read_text(encoding="utf-8")
    return re.search(r"requires_bash\s*:\s*true", text) is not None


def bash_supported() -> bool:
    """POSIX bash on this host. Windows never counts Git Bash as support."""
    if sys.platform == "win32":
        return False
    return shutil.which("bash") is not None


def _python_for(_demo_root: Path) -> str:
    from lauren_team_kit.exec_run import resolve_interpreter

    return resolve_interpreter()


def _substitute_python(cmd: str, interpreter: str) -> str:
    """Replace the first ``python`` token with a shell-safe interpreter path.

    A callable replacement is required: ``re.sub`` treats backslashes in a
    string replacement as escapes, so a Windows interpreter path would raise
    ``re.error``.
    """
    quoted = shlex.quote(interpreter)

    def repl(_match: re.Match[str]) -> str:
        return quoted

    return re.sub(r"\bpython\b", repl, cmd, count=1)


def _expand(value: str, *, impl: str, python: str, pythonpath: str) -> str:
    return (
        value.replace("{impl}", impl)
        .replace("{python}", python)
        .replace("{pythonpath}", pythonpath)
    )


def _run_structured(
    probes: list[dict[str, Any]],
    demo_root: Path,
    impl: str,
) -> list[dict[str, Any]]:
    python = _python_for(demo_root)
    pythonpath = str((demo_root / "src").resolve())
    rows: list[dict[str, Any]] = []
    for probe in probes:
        argv = [
            _expand(part, impl=impl, python=python, pythonpath=pythonpath)
            for part in probe.get("argv") or []
        ]
        env_in = probe.get("env") if isinstance(probe.get("env"), dict) else {}
        env = {
            str(key): _expand(str(value), impl=impl, python=python, pythonpath=pythonpath)
            for key, value in env_in.items()
        }
        env.setdefault("DEMO_FILTER_IMPL", impl)
        env.setdefault("PYTHONPATH", pythonpath)
        item = {
            "id": str(probe.get("id") or "probe"),
            "exec": {
                "kind": "argv",
                "argv": argv,
                "cwd": str(probe.get("cwd") or "."),
                "env": env,
                "timeout_sec": probe.get("timeout_sec") or 120,
            },
        }
        ran = run_acceptance_item(item, base=demo_root)
        expect_exit = probe.get("expect_exit", 0)
        expect_out = probe.get("expect_stdout_contains")
        ok = ran["outcome"] == "exit" and ran.get("exit_code") == expect_exit
        if expect_exit != 0:
            ok = ran["outcome"] == "nonzero" and ran.get("exit_code") == expect_exit
        if ok and isinstance(expect_out, str) and expect_out not in (ran.get("stdout_tail") or ""):
            ok = False
        rows.append(
            {
                "id": item["id"],
                "ok": ok,
                "outcome": ran["outcome"],
                "exit_code": ran.get("exit_code"),
                "argv": ran.get("argv"),
                "stderr_tail": (ran.get("stderr_tail") or "")[-400:],
            }
        )
    return rows


def _run_bash(probes: list[str], demo_root: Path, impl: str) -> dict[str, Any]:
    if not probes:
        return {"status": "absent", "requires_bash": False, "ok": False, "probes": []}
    if not bash_supported():
        return {
            "status": "cannot_run",
            "requires_bash": True,
            "ok": False,
            "reason": "当前环境不能运行 Bash 探针；Windows 原生不会改走 Git Bash。这不是 pass。",
            "probes": [],
        }
    import subprocess

    py = _python_for(demo_root)
    env = dict(os.environ)
    env["DEMO_FILTER_IMPL"] = impl
    env["PYTHONPATH"] = str(demo_root / "src")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    mod = "demo_app.filter_buggy" if impl == "buggy" else "demo_app.filter"
    results = []
    for raw in probes:
        cmd = re.sub(r"DEMO_FILTER_IMPL=\w+ ", "", raw).replace("PYTHONPATH=src ", "")
        cmd = cmd.replace("from demo_app.filter import", f"from {mod} import")
        cmd = _substitute_python(cmd, py)
        proc = subprocess.run(
            ["bash", "-c", "set -o pipefail; " + cmd],
            cwd=demo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        results.append(
            {
                "probe": raw,
                "impl": impl,
                "exit_code": proc.returncode,
                "ok": proc.returncode == 0,
                "stderr_tail": (proc.stderr or "")[-400:],
            }
        )
    ok = all(row["ok"] for row in results)
    return {
        "status": "pass" if ok else "fail",
        "requires_bash": True,
        "ok": ok,
        "probes": results,
    }


def run_rule(rule_path: str | Path, demo_root: str | Path, impl: str | None = None) -> dict[str, Any]:
    rule = Path(rule_path).resolve()
    demo = Path(demo_root).resolve()
    impl_name = (impl or os.environ.get("DEMO_FILTER_IMPL") or "fixed").strip().lower()
    structured = parse_structured_probes(rule)
    bash_lines = parse_probes(rule)
    structured_rows = _run_structured(structured, demo, impl_name) if structured else []
    bash = _run_bash(bash_lines, demo, impl_name) if bash_lines else {
        "status": "absent",
        "requires_bash": rule_requires_bash(rule),
        "ok": False,
        "probes": [],
    }
    if structured:
        ok = bool(structured_rows) and all(row["ok"] for row in structured_rows)
        status = "pass" if ok else "fail"
        errors: list[str] = []
    elif bash.get("status") == "cannot_run":
        ok = False
        status = "cannot_run"
        errors = [str(bash.get("reason") or "bash cannot_run")]
    elif bash_lines:
        ok = bool(bash.get("ok"))
        status = "pass" if ok else "fail"
        errors = []
    else:
        ok = False
        status = "cannot_run" if rule_requires_bash(rule) else "fail"
        errors = ["规则中未找到可执行探针"]
    return {
        "rule": str(rule),
        "against": str(demo),
        "impl": impl_name,
        "ok": ok,
        "status": status,
        "requires_bash": rule_requires_bash(rule) or bool(bash_lines),
        "structured": structured_rows,
        "bash": bash,
        "probes": bash.get("probes") or [],
        "errors": errors,
    }
