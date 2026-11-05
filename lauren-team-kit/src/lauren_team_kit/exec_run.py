"""Structured acceptance execution (W1).

Recommended checks use ``exec.kind=argv`` with cwd, env, and timeout passed to
``subprocess`` directly. ``{python}`` (and a bare interpreter token in argv[0])
is replaced with :func:`resolve_interpreter`, which returns a real interpreter
path. It does not invent a project virtualenv path or return a bare name.

A legacy ``command`` string is type ``shell``. It is not split on ``&&``,
pipes, or quotes. POSIX shell runs only when one is actually available.
Windows does not search Git Bash. Outcomes are ``start_fail``, ``exit``,
``nonzero``, ``timeout``, ``cancel``, and ``unknown``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

OUTCOMES = ("start_fail", "exit", "nonzero", "timeout", "cancel", "unknown")
_BARE_INTERPRETERS = {
    "python",
    "python3",
    "py",
    ".venv/bin/python",
    ".venv\\Scripts\\python.exe",
}
_SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd)")
_TAIL = 2000


class InterpreterError(RuntimeError):
    """No real Python interpreter could be resolved."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resolve_interpreter(explicit: str | None = None) -> str:
    """Return a filesystem path to a Python interpreter.

    Order: ``explicit`` file, ``LAUREN_PYTHON`` file, ``sys.executable``,
    then ``python3`` / ``python`` / ``py`` on ``PATH``. Never invents a
    project virtualenv relative path.
    """
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return str(path.resolve())
        raise InterpreterError(f"指定解释器不存在: {explicit}")
    env_py = os.environ.get("LAUREN_PYTHON")
    if env_py:
        path = Path(env_py)
        if path.is_file():
            return str(path.resolve())
        raise InterpreterError(f"LAUREN_PYTHON 不是已存在的解释器文件: {env_py}")
    current = Path(sys.executable)
    if str(current) and current.is_file():
        return str(current.resolve())
    import shutil

    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found and Path(found).is_file():
            return str(Path(found).resolve())
    raise InterpreterError("找不到 Python 解释器")


def select_posix_shell(
    *,
    platform: str | None = None,
    environ: dict[str, str] | None = None,
    which: Callable[[str], str | None] | None = None,
    is_file: Callable[[str], bool] | None = None,
) -> str | None:
    """POSIX shell path, or None when this host must not run a shell command.

    On Windows the only opt-in is ``LAUREN_POSIX_SHELL`` pointing at a real
    file. ``PATH`` bash and ``Git\\bin\\bash.exe`` are ignored so a native
    run cannot silently become Git Bash.
    """
    import shutil

    system = platform or sys.platform
    env = os.environ if environ is None else environ
    which_fn = which or shutil.which
    file_fn = is_file or (lambda p: Path(p).is_file())
    explicit = env.get("LAUREN_POSIX_SHELL")
    if system == "win32":
        if explicit and file_fn(explicit):
            return explicit
        return None
    if explicit and file_fn(explicit):
        return explicit
    for name in ("bash", "sh"):
        found = which_fn(name)
        if found and file_fn(found):
            return found
    return None


def command_kind(item: dict[str, Any]) -> str:
    """``argv`` only when the record says so. Legacy strings stay ``shell``."""
    spec = item.get("exec")
    if isinstance(spec, dict) and spec.get("kind") in ("argv", "shell"):
        return str(spec["kind"])
    return "shell"


def acceptance_fingerprint(acceptance: Any) -> str:
    payload = json.dumps(acceptance, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def redact_text(value: str) -> str:
    if value.startswith("sk-") or _SECRET.search(value):
        return "***"
    return value


def redact_argv(argv: list[str]) -> list[str]:
    return [redact_text(part) for part in argv]


def redact_env(env: dict[str, str]) -> dict[str, str]:
    return {key: ("***" if _SECRET.search(key) else value) for key, value in env.items()}


def prepare_argv(argv: list[str]) -> tuple[list[str], str]:
    interpreter = resolve_interpreter()
    out: list[str] = []
    for index, arg in enumerate(argv):
        if arg == "{python}" or (index == 0 and arg in _BARE_INTERPRETERS):
            out.append(interpreter)
        else:
            out.append(arg)
    return out, interpreter


def _tail(text: str | None) -> str:
    if not text:
        return ""
    return text[-_TAIL:]


def _base_result(**extra: Any) -> dict[str, Any]:
    row = {
        "outcome": "unknown",
        "executed": False,
        "exit_code": None,
        "argv": None,
        "cwd": None,
        "interpreter": None,
        "command_type": None,
        "env": {},
        "started_at": None,
        "finished_at": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "reason": None,
        "cancel_tree": None,
        "split_attempted": False,
    }
    row.update(extra)
    return row


def _stop_child(proc: subprocess.Popen[str], *, group: bool) -> str:
    if group and sys.platform != "win32":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            return "posix_process_group"
        except OSError:
            proc.terminate()
            return "posix_process_group"
    proc.terminate()
    return "direct_child_only"


def _drain(proc: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        out, err = proc.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    return out or "", err or ""


def run_acceptance_item(
    item: dict[str, Any],
    *,
    base: Path | str,
    cancel: Callable[[], bool] | None = None,
    platform: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one acceptance item. Does not guess-split shell command strings."""
    base_path = Path(base)
    kind = command_kind(item)
    spec = item.get("exec") if isinstance(item.get("exec"), dict) else {}
    command = item.get("command") if isinstance(item.get("command"), str) else ""
    spec_env = spec.get("env") if isinstance(spec.get("env"), dict) else {}
    clean_env = {str(k): str(v) for k, v in spec_env.items()}
    recorded_env = redact_env(clean_env)

    raw_cwd = spec.get("cwd") if isinstance(spec.get("cwd"), str) and spec.get("cwd") else "."
    cwd_path = Path(raw_cwd)
    if not cwd_path.is_absolute():
        cwd_path = base_path / cwd_path
    try:
        cwd_resolved = cwd_path.resolve()
    except OSError as exc:
        return _base_result(
            outcome="start_fail",
            command_type=kind,
            env=recorded_env,
            reason=f"cwd 无法解析: {exc}",
            finished_at=_now(),
        )
    if not cwd_resolved.is_dir():
        return _base_result(
            outcome="start_fail",
            command_type=kind,
            cwd=str(cwd_resolved),
            env=recorded_env,
            reason=f"cwd 不是目录: {cwd_resolved}",
            finished_at=_now(),
        )

    timeout = spec.get("timeout_sec", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        return _base_result(
            outcome="start_fail",
            command_type=kind,
            cwd=str(cwd_resolved),
            env=recorded_env,
            reason="timeout_sec 必须为正数",
            finished_at=_now(),
        )

    if cancel and cancel():
        return _base_result(
            outcome="cancel",
            command_type=kind,
            cwd=str(cwd_resolved),
            env=recorded_env,
            reason="取消于启动前",
            cancel_tree="not_started",
            finished_at=_now(),
        )

    interpreter: str | None = None
    try:
        if kind == "argv":
            raw_argv = spec.get("argv")
            if not isinstance(raw_argv, list) or not raw_argv or not all(isinstance(x, str) for x in raw_argv):
                return _base_result(
                    outcome="start_fail",
                    command_type="argv",
                    cwd=str(cwd_resolved),
                    env=recorded_env,
                    reason="exec.argv 必须为非空字符串数组",
                    finished_at=_now(),
                )
            argv, interpreter = prepare_argv(list(raw_argv))
        else:
            if not command.strip():
                return _base_result(
                    outcome="start_fail",
                    command_type="shell",
                    cwd=str(cwd_resolved),
                    env=recorded_env,
                    reason="shell 验收缺少 command",
                    finished_at=_now(),
                )
            shell = select_posix_shell(platform=platform, environ=environ)
            if not shell:
                return _base_result(
                    outcome="start_fail",
                    command_type="shell",
                    cwd=str(cwd_resolved),
                    env=recorded_env,
                    reason="没有可用的 POSIX shell；Windows 原生不会改走 Git Bash",
                    finished_at=_now(),
                )
            argv = [shell, "-c", command]
    except InterpreterError as exc:
        return _base_result(
            outcome="start_fail",
            command_type=kind,
            cwd=str(cwd_resolved),
            env=recorded_env,
            reason=str(exc),
            finished_at=_now(),
        )

    child_env = os.environ.copy()
    child_env.update(clean_env)
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    child_env.setdefault("PYTHONUTF8", "1")
    started = _now()
    popen_kwargs: dict[str, Any] = {}
    use_group = sys.platform != "win32"
    if use_group:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd_resolved),
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **popen_kwargs,
        )
    except FileNotFoundError as exc:
        return _base_result(
            outcome="start_fail",
            executed=False,
            command_type=kind,
            argv=redact_argv(argv),
            cwd=str(cwd_resolved),
            interpreter=interpreter,
            env=recorded_env,
            started_at=started,
            finished_at=_now(),
            reason=f"无法启动: {exc}",
        )
    except OSError as exc:
        return _base_result(
            outcome="start_fail",
            command_type=kind,
            argv=redact_argv(argv),
            cwd=str(cwd_resolved),
            interpreter=interpreter,
            env=recorded_env,
            started_at=started,
            finished_at=_now(),
            reason=f"启动失败: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 — unified unknown outcome
        return _base_result(
            outcome="unknown",
            command_type=kind,
            argv=redact_argv(argv),
            cwd=str(cwd_resolved),
            interpreter=interpreter,
            env=recorded_env,
            started_at=started,
            finished_at=_now(),
            reason=f"无法判定: {type(exc).__name__}: {exc}",
        )

    deadline = time.monotonic() + float(timeout)
    outcome = "unknown"
    tree: str | None = None
    while True:
        if cancel and cancel():
            tree = _stop_child(proc, group=use_group)
            outcome = "cancel"
            break
        code = proc.poll()
        if code is not None:
            outcome = "exit" if code == 0 else "nonzero"
            break
        if time.monotonic() >= deadline:
            tree = _stop_child(proc, group=use_group)
            outcome = "timeout"
            break
        time.sleep(0.02)
    stdout, stderr = _drain(proc)
    exit_code: int | None
    if outcome in ("timeout", "cancel"):
        exit_code = None
    else:
        exit_code = proc.returncode
    return _base_result(
        outcome=outcome,
        executed=True,
        exit_code=exit_code,
        argv=redact_argv(argv),
        cwd=str(cwd_resolved),
        interpreter=interpreter,
        command_type=kind,
        env=recorded_env,
        started_at=started,
        finished_at=_now(),
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
        reason=None if outcome in ("exit", "nonzero") else outcome,
        cancel_tree=tree,
    )


def run_must_run_round(
    task: dict[str, Any],
    *,
    base: Path | str,
    cancel: Callable[[], bool] | None = None,
    actor: str = "verifier",
    role: str = "verifier",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run every ``must_run`` item in one new verification round, then summarize.

    One failing or missing item keeps the round from passing. Checks share
    ``round_id`` and ``acceptance_fingerprint``.
    """
    from lauren_team_kit.protocol import record_check

    acceptance = task.get("acceptance") if isinstance(task.get("acceptance"), list) else []
    items = [
        item
        for item in acceptance
        if isinstance(item, dict) and item.get("must_run") is True and isinstance(item.get("id"), str)
    ]
    fingerprint = acceptance_fingerprint(acceptance)
    results: list[dict[str, Any]] = []
    first = True
    for item in items:
        result = run_acceptance_item(item, base=base, cancel=cancel)
        results.append({"id": item["id"], **result})
        task = record_check(
            task,
            acceptance_id=item["id"],
            executed=bool(result["executed"]),
            exit_code=result.get("exit_code"),
            notes=result.get("reason"),
            actor=actor,
            role=role,
            new_round=first,
            exec_meta={
                "outcome": result["outcome"],
                "argv": result.get("argv"),
                "cwd": result.get("cwd"),
                "interpreter": result.get("interpreter"),
                "command_type": result.get("command_type"),
                "started_at": result.get("started_at"),
                "finished_at": result.get("finished_at"),
                "stdout_tail": result.get("stdout_tail") or "",
                "stderr_tail": result.get("stderr_tail") or "",
                "acceptance_fingerprint": fingerprint,
            },
        )
        first = False
    ok = bool(items) and all(row["outcome"] == "exit" for row in results)
    verification = dict(task.get("verification") or {})
    verification["acceptance_fingerprint"] = fingerprint
    verification["result"] = "pass" if ok else "fail"
    task["verification"] = verification
    round_id = verification.get("round_id")
    summary = {
        "ok": ok,
        "round_id": round_id,
        "acceptance_fingerprint": fingerprint,
        "must_run": [item["id"] for item in items],
        "failed_ids": [row["id"] for row in results if row["outcome"] != "exit"],
        "results": results,
    }
    if len(items) < 1:
        summary["ok"] = False
        summary["reason"] = "没有 must_run 验收项"
    return task, summary
