"""Read-only Git diagnostics (W3).

Records version, ``core.autocrlf``, ``safe.directory`` and ``merge-tree``
support. Never runs ``git config`` writes, ``--global`` sets, or
``safe.directory=*``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

Runner = Callable[..., Any]


def _which_git() -> str | None:
    return shutil.which("git")


def _parse_show_origin(stdout: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in (stdout or "").splitlines():
        if not line.strip():
            continue
        if "\t" in line:
            origin, value = line.split("\t", 1)
            rows.append({"origin": origin.strip(), "value": value.strip()})
        else:
            rows.append({"origin": "", "value": line.strip()})
    return rows


def read_git_diagnostics(
    repo: Path | str | None = None,
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Collect Git facts. ``runner`` defaults to ``subprocess.run``.

    A missing key is reported as absent. This function does not create config.
    """
    run = runner or subprocess.run
    git = _which_git()
    report: dict[str, Any] = {
        "present": False,
        "required": True,
        "path": git,
        "version": None,
        "merge_tree_write_tree": False,
        "autocrlf": {"value": None, "origin": None, "local_value": None},
        "safe_directory": {
            "entries": [],
            "observed_unrestricted": False,
        },
        "config_rewritten": False,
        "hint": "未找到 git。请按平台安装 Git；本命令不会写入 git config。",
    }
    if not git:
        return report

    version_run = _invoke(run, [git, "--version"])
    help_run = _invoke(run, [git, "merge-tree", "-h"])
    auto_run = _invoke(run, [git, "config", "--show-origin", "--get", "core.autocrlf"])
    safe_run = _invoke(
        run, [git, "config", "--show-origin", "--get-all", "safe.directory"]
    )

    version = None
    if version_run is not None and version_run.stdout:
        version = version_run.stdout.strip().splitlines()[0]
    help_text = ""
    if help_run is not None:
        help_text = f"{help_run.stdout or ''}\n{help_run.stderr or ''}"
    write_tree = "--write-tree" in help_text

    auto_rows = _parse_show_origin(version_out(auto_run))
    safe_rows = _parse_show_origin(version_out(safe_run))
    unrestricted = any(row["value"] == "*" for row in safe_rows)

    local_value = None
    repo_path = _repo_or_none(repo)
    if repo_path is not None:
        local_run = _invoke(
            run,
            [
                git,
                "-C",
                str(repo_path),
                "config",
                "--local",
                "--show-origin",
                "--get",
                "core.autocrlf",
            ],
        )
        local_rows = _parse_show_origin(version_out(local_run))
        if local_rows:
            local_value = local_rows[-1]["value"]

    hint = None
    if version_run is None:
        hint = "已找到 git 但无法执行 --version。本命令不会修改 git 配置。"
    elif not write_tree:
        hint = (
            "Git 不支持 merge-tree --write-tree（约需 2.38+）。"
            "请升级 Git；不要用 git config --global 或关闭 TLS 校验来绕过。"
        )
    elif unrestricted:
        hint = (
            "观察到 safe.directory=*。本命令没有设置它，也不会写入 safe.directory=*。"
        )

    report.update(
        {
            "present": version_run is not None,
            "path": git,
            "version": version,
            "merge_tree_write_tree": write_tree,
            "autocrlf": {
                "value": auto_rows[-1]["value"] if auto_rows else None,
                "origin": auto_rows[-1]["origin"] if auto_rows else None,
                "local_value": local_value,
            },
            "safe_directory": {
                "entries": safe_rows,
                "observed_unrestricted": unrestricted,
            },
            "config_rewritten": False,
            "hint": hint,
        }
    )
    return report


def git_common_dir(worktree: Path | str, *, runner: Runner | None = None) -> Path:
    """Absolute ``git rev-parse --git-common-dir`` for this worktree.

    Linked worktrees share the main repository's common dir, so a merge lock
    placed there is one lock for every worktree of that repo.
    """
    run = runner or subprocess.run
    git = _which_git() or "git"
    wt = Path(worktree)
    absolute = _invoke(
        run,
        [git, "-C", str(wt), "rev-parse", "--path-format=absolute", "--git-common-dir"],
    )
    text = ""
    if absolute is not None and absolute.returncode == 0:
        text = (absolute.stdout or "").strip()
    if not text:
        relative = _invoke(run, [git, "-C", str(wt), "rev-parse", "--git-common-dir"])
        if relative is None or relative.returncode != 0:
            detail = ""
            if relative is not None:
                detail = (relative.stderr or relative.stdout or "").strip()
            raise OSError(f"无法解析 git common-dir: {wt} {detail}".strip())
        text = (relative.stdout or "").strip()
    path = Path(text)
    if not path.is_absolute():
        path = (wt.resolve() / path).resolve()
    else:
        path = path.resolve()
    return path


def _repo_or_none(repo: Path | str | None) -> Path | None:
    if repo is None or not str(repo).strip():
        return None
    path = Path(repo)
    if not path.exists():
        return None
    return path


def version_out(proc: Any) -> str:
    if proc is None:
        return ""
    if getattr(proc, "returncode", 1) not in (0,):
        return ""
    return proc.stdout or ""


def _invoke(run: Runner, cmd: list[str]) -> Any:
    try:
        return run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except TypeError:
        # doctor._run does not accept every subprocess keyword.
        try:
            return run(cmd)
        except (OSError, subprocess.TimeoutExpired):
            return None
    except (OSError, subprocess.TimeoutExpired):
        return None
