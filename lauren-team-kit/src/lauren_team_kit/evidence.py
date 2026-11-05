"""Evidence directory layout under workspace/runs/<stable-dir-id>/."""

from __future__ import annotations

from pathlib import Path

from lauren_team_kit.paths import assert_no_case_collision, stable_dir_id

SUBDIRS = ("logs", "artifacts", "checks")


def evidence_relpath(task_id: str) -> str:
    return f"workspace/runs/{stable_dir_id(task_id)}/"


def ensure_evidence_dir(root: Path | str, task_id: str) -> Path:
    """Create workspace/runs/<dir-id>/{logs,artifacts,checks}/.gitkeep (idempotent).

    The directory id is :func:`stable_dir_id`, not the display title. A
    case-only collision with an existing run directory is an error.
    """
    root_p = Path(root).resolve()
    name = stable_dir_id(task_id)
    parent = root_p / "workspace" / "runs"
    parent.mkdir(parents=True, exist_ok=True)
    assert_no_case_collision(parent, name)
    base = parent / name
    base.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        d = base / sub
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
    return base
