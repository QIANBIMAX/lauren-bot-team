"""check-rule：对 demo-app 跑规则 `## 验收探针`（filter-empty-query）。impl=buggy 时探针应失败。"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_probes(rule_path: Path) -> list[str]:
    text = rule_path.read_text(encoding="utf-8")
    m = re.search(r"## 验收探针\s*```(?:bash)?\n(.*?)```", text, re.S)
    if not m:
        return []
    return [l.strip() for l in m.group(1).splitlines() if l.strip() and not l.startswith("#")]


def _python_for(demo_root: Path) -> str:
    venv = demo_root / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _substitute_python(cmd: str, interpreter: str) -> str:
    """Replace the first ``python`` token with a shell-safe interpreter path.

    A callable replacement is required: ``re.sub`` treats backslashes in a
    string replacement as escapes, so ``C:\\hostedtoolcache\\...`` raises
    ``re.error: bad escape``.
    """
    quoted = shlex.quote(interpreter)

    def repl(_match: re.Match[str]) -> str:
        return quoted

    return re.sub(r"\bpython\b", repl, cmd, count=1)


def _bash_executable() -> str:
    found = shutil.which("bash")
    if found:
        return found
    if sys.platform == "win32":
        roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
        for root in roots:
            if not root:
                continue
            for rel in ("Git\\bin\\bash.exe", "Git\\usr\\bin\\bash.exe"):
                candidate = Path(root) / rel
                if candidate.is_file():
                    return str(candidate)
    return "bash"


def run_rule(rule_path: str | Path, demo_root: str | Path, impl: str | None = None) -> dict[str, Any]:
    rule_path, demo_root = Path(rule_path).resolve(), Path(demo_root).resolve()
    impl = (impl or os.environ.get("DEMO_FILTER_IMPL") or "fixed").strip().lower()
    probes = parse_probes(rule_path)
    py = _python_for(demo_root)
    env = dict(os.environ, DEMO_FILTER_IMPL=impl, PYTHONPATH=str(demo_root / "src"))
    mod = "demo_app.filter_buggy" if impl == "buggy" else "demo_app.filter"
    results = []
    for raw in probes:
        cmd = re.sub(r"DEMO_FILTER_IMPL=\w+ ", "", raw).replace("PYTHONPATH=src ", "")
        cmd = cmd.replace("from demo_app.filter import", f"from {mod} import")
        cmd = _substitute_python(cmd, py)
        p = subprocess.run(
            [_bash_executable(), "-c", "set -o pipefail; " + cmd],
            cwd=demo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        results.append({"probe": raw, "impl": impl, "exit_code": p.returncode, "ok": p.returncode == 0,
                        "stderr_tail": p.stderr[-400:]})
    ok = bool(probes) and all(r["ok"] for r in results)
    return {"rule": str(rule_path), "against": str(demo_root), "impl": impl, "ok": ok,
            "probes": results, "errors": [] if probes else ["规则中未找到 ## 验收探针"]}
