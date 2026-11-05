"""Machine-readable environment doctor for the native kit (W0).

Reports facts about this interpreter and machine. It does not print secrets,
rewrite git config, change execution policy, disable TLS verification, or
request administrator rights. Workbench / OMB / engine state is never probed.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "lauren-kit-doctor/0.1"

_WORKBENCH_HINT = (
    "工作台/OMB/引擎本次不探测。"
    "omb_delegate 真实桥接是独立事项，当前未接通，不能当成已可用。"
)
_LOCK_HINT_PRESENT = (
    "本解释器可导入 fcntl.flock（POSIX 建议锁）。"
    "这不是 Windows 锁验收。完整 W3（占用重试、仓库级集成锁、路径身份）仍未做。"
)
_LOCK_HINT_MSVCRT = (
    "本解释器没有 fcntl。Windows 读改写使用标准库 msvcrt.locking，不是 no-op。"
    "完整 W3（占用重试、仓库级集成锁、路径身份）仍未做。"
)
_LOCK_HINT_ABSENT = (
    "当前解释器没有可用文件锁。不能把缺失锁当成已互斥。完整 W3 未做。"
)


def collect_report(*, root: Path | str | None = None) -> dict[str, Any]:
    """Collect one doctor report. ``root`` is an optional delivery root to write-test."""
    py = _probe_python()
    package = _probe_package()
    git = _probe_git()
    writable = _probe_writable_dirs(root)
    lock = _probe_lock()
    utf8 = _probe_subprocess_utf8()
    long_path = _probe_long_path()
    bash = _probe_bash()
    workbench = _workbench()
    failures = _required_failures(
        py=py, package=package, git=git, writable=writable, utf8=utf8
    )
    hints = _hints(
        py=py,
        package=package,
        git=git,
        writable=writable,
        lock=lock,
        utf8=utf8,
        long_path=long_path,
        bash=bash,
        workbench=workbench,
        failures=failures,
    )
    return {
        "schema": SCHEMA,
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "ok": not failures,
        "required_failures": failures,
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
            "platform": platform.platform(),
        },
        "python": py,
        "package": package,
        "git": git,
        "writable_dirs": writable,
        "lock": lock,
        "subprocess_utf8": utf8,
        "long_path": long_path,
        "bash": bash,
        "workbench": workbench,
        "hints": hints,
    }


def format_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def exit_code(report: dict[str, Any]) -> int:
    return 0 if report.get("ok") else 1


def _probe_python() -> dict[str, Any]:
    info = sys.version_info
    ok = info >= (3, 11)
    hint = None
    if not ok:
        hint = "需要 Python 3.11 或更高。主测 3.12 通过不等于所有未来版本可用。"
    return {
        "ok": ok,
        "required": True,
        "version": platform.python_version(),
        "version_info": [info.major, info.minor, info.micro],
        "executable": sys.executable,
        "implementation": platform.python_implementation(),
        "hint": hint,
    }


def _probe_package() -> dict[str, Any]:
    try:
        import lauren_team_kit as kit

        version = getattr(kit, "__version__", None)
    except Exception as exc:
        return {
            "name": "lauren_team_kit",
            "import_ok": False,
            "required": True,
            "version": None,
            "error_type": type(exc).__name__,
            "hint": "无法导入 lauren_team_kit。请在 lauren-team-kit 目录执行 pip install -e .",
        }
    return {
        "name": "lauren_team_kit",
        "import_ok": True,
        "required": True,
        "version": version,
        "error_type": None,
        "hint": None,
    }


def _probe_git() -> dict[str, Any]:
    git = shutil.which("git")
    base: dict[str, Any] = {
        "present": False,
        "required": True,
        "path": git,
        "version": None,
        "merge_tree_write_tree": False,
        "hint": "未找到 git。请按平台安装 Git；本命令不会写入全局 git config。",
    }
    if not git:
        return base
    version_run = _run([git, "--version"])
    help_run = _run([git, "merge-tree", "-h"])
    version = None
    if version_run is not None and version_run.stdout:
        version = version_run.stdout.strip().splitlines()[0]
    help_text = ""
    if help_run is not None:
        help_text = f"{help_run.stdout or ''}\n{help_run.stderr or ''}"
    write_tree = "--write-tree" in help_text
    hint = None
    if version_run is None:
        hint = "已找到 git 但无法执行 --version。本命令不会修改 git 配置。"
    elif not write_tree:
        hint = (
            "Git 不支持 merge-tree --write-tree（约需 2.38+）。"
            "请升级 Git；不要用 git config --global 或关闭 TLS 校验来绕过。"
        )
    return {
        "present": version_run is not None,
        "required": True,
        "path": git,
        "version": version,
        "merge_tree_write_tree": write_tree,
        "hint": hint,
    }


def _probe_writable_dirs(root: Path | str | None) -> list[dict[str, Any]]:
    rows = [
        _probe_one_dir(Path(tempfile.gettempdir()), "temp", required=True),
        _probe_one_dir(Path.cwd(), "cwd", required=False),
    ]
    if root is not None and str(root).strip():
        rows.append(_probe_one_dir(Path(root), "root", required=True))
    return rows


def _probe_one_dir(path: Path, label: str, *, required: bool) -> dict[str, Any]:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return {
            "label": label,
            "path": str(path),
            "required": required,
            "exists": False,
            "writable": False,
            "hint": "路径无法解析。本命令不会提权。",
        }
    if not resolved.exists():
        return {
            "label": label,
            "path": str(resolved),
            "required": required,
            "exists": False,
            "writable": False,
            "hint": "路径不存在。本命令不会自动创建交付根，也不会提权。",
        }
    if not resolved.is_dir():
        return {
            "label": label,
            "path": str(resolved),
            "required": required,
            "exists": True,
            "writable": False,
            "hint": "不是目录，不能当作可写工作目录。",
        }
    try:
        with tempfile.NamedTemporaryFile(
            dir=resolved, prefix=".lauren-doctor-", delete=True
        ) as handle:
            handle.write(b"ok")
            handle.flush()
    except OSError:
        return {
            "label": label,
            "path": str(resolved),
            "required": required,
            "exists": True,
            "writable": False,
            "hint": "目录不可写。请检查权限；本命令不会提权。",
        }
    return {
        "label": label,
        "path": str(resolved),
        "required": required,
        "exists": True,
        "writable": True,
        "hint": None,
    }


def _probe_lock() -> dict[str, Any]:
    present = False
    try:
        import fcntl

        present = hasattr(fcntl, "flock")
    except ImportError:
        present = False
    if present:
        return {
            "fcntl_present": True,
            "capability": "fcntl",
            "cross_process_lock": "posix_flock",
            "required": False,
            "hint": _LOCK_HINT_PRESENT,
        }
    if sys.platform == "win32":
        msvcrt_ok = False
        try:
            import msvcrt

            msvcrt_ok = hasattr(msvcrt, "locking")
        except ImportError:
            msvcrt_ok = False
        if msvcrt_ok:
            return {
                "fcntl_present": False,
                "capability": "msvcrt",
                "cross_process_lock": "msvcrt_locking",
                "required": False,
                "hint": _LOCK_HINT_MSVCRT,
            }
    return {
        "fcntl_present": False,
        "capability": "unavailable",
        "cross_process_lock": "not_implemented",
        "required": False,
        "hint": _LOCK_HINT_ABSENT,
    }


def _probe_subprocess_utf8() -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.pop("GIT_SSL_NO_VERIFY", None)
    code = "print('中文UTF8')"
    proc = _run([sys.executable, "-c", code], env=env)
    if proc is None:
        return {
            "ok": False,
            "required": True,
            "sample_ok": False,
            "hint": "无法启动解释器子进程做 UTF-8 探测。本命令不会改控制台代码页。",
        }
    sample_ok = proc.returncode == 0 and "中文UTF8" in (proc.stdout or "")
    hint = None
    if not sample_ok:
        hint = (
            "子进程 UTF-8 往返失败。可在当前会话设置 PYTHONUTF8=1 后重试；"
            "本命令不会永久修改系统区域设置。"
        )
    return {
        "ok": sample_ok,
        "required": True,
        "returncode": proc.returncode,
        "sample_ok": sample_ok,
        "hint": hint,
    }


def _probe_long_path() -> dict[str, Any]:
    if sys.platform != "win32":
        return {
            "applicable": False,
            "status": "not_applicable",
            "enabled": None,
            "hint": "长路径策略只在 Windows 有意义。本机未探测，也未修改系统策略。",
        }
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "LongPathsEnabled")
        enabled = bool(int(value))
    except Exception:
        return {
            "applicable": True,
            "status": "unknown",
            "enabled": None,
            "hint": (
                "未能只读查询 LongPathsEnabled。请手工检查；"
                "遇到超长路径时再启用 Windows 长路径或缩短路径。本命令不改注册表。"
            ),
        }
    if enabled:
        hint = "已只读看到 LongPathsEnabled=1。本命令没有修改注册表。"
        status = "enabled"
    else:
        hint = (
            "LongPathsEnabled 未开启。路径过长时请启用 Windows 长路径或缩短路径；"
            "本命令不改注册表、不提权。"
        )
        status = "disabled"
    return {
        "applicable": True,
        "status": status,
        "enabled": enabled,
        "hint": hint,
    }


def _probe_bash() -> dict[str, Any]:
    path = shutil.which("bash")
    present = path is not None
    if present:
        hint = "检测到可选 bash。Demo Bash 场景不等于 Windows 原生验收。"
        status = "present"
    else:
        hint = "未检测到 bash（可选）。Windows 原生路径不得依赖 Git Bash 或 WSL。"
        status = "optional_missing"
    return {
        "optional": True,
        "present": present,
        "required": False,
        "path": path,
        "status": status,
        "hint": hint,
    }


def _workbench() -> dict[str, Any]:
    return {
        "probed": False,
        "omb_gui_import": "not_probed",
        "omb_delegate": "not_connected",
        "engine": "not_probed",
        "desktop_session": "not_probed",
        "hint": _WORKBENCH_HINT,
    }


def _required_failures(
    *,
    py: dict[str, Any],
    package: dict[str, Any],
    git: dict[str, Any],
    writable: list[dict[str, Any]],
    utf8: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if not py.get("ok"):
        failures.append("python")
    if not package.get("import_ok"):
        failures.append("package")
    if not git.get("present") or not git.get("merge_tree_write_tree"):
        failures.append("git")
    if not utf8.get("ok"):
        failures.append("subprocess_utf8")
    for row in writable:
        if row.get("required") and not row.get("writable"):
            failures.append(f"writable:{row.get('label')}")
    return failures


def _hints(
    *,
    py: dict[str, Any],
    package: dict[str, Any],
    git: dict[str, Any],
    writable: list[dict[str, Any]],
    lock: dict[str, Any],
    utf8: dict[str, Any],
    long_path: dict[str, Any],
    bash: dict[str, Any],
    workbench: dict[str, Any],
    failures: list[str],
) -> list[str]:
    ordered = [
        py.get("hint"),
        package.get("hint"),
        git.get("hint"),
        utf8.get("hint"),
        lock.get("hint"),
        long_path.get("hint"),
        bash.get("hint") if not bash.get("present") else None,
        workbench.get("hint"),
    ]
    for row in writable:
        if row.get("required") and not row.get("writable"):
            ordered.append(row.get("hint"))
    if not failures:
        ordered.append("必需项已满足。可选缺失和未探测工作台不算通过 OMB。")
    out: list[str] = []
    for item in ordered:
        if isinstance(item, str) and item and item not in out:
            out.append(item)
    return out


def _run(
    cmd: list[str],
    *,
    timeout: float = 10,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str] | None:
    child_env = os.environ.copy() if env is None else dict(env)
    child_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    child_env.setdefault("GIT_PAGER", "cat")
    child_env.pop("GIT_SSL_NO_VERIFY", None)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
            env=child_env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def main_report_json(*, root: Path | str | None = None) -> tuple[str, int]:
    report = collect_report(root=root)
    return format_report(report), exit_code(report)
