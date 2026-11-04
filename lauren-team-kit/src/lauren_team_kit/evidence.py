"""Evidence directory layout under workspace/runs/<task_id>/."""

from __future__ import annotations

from pathlib import Path

SUBDIRS = ("logs", "artifacts", "checks")


def evidence_relpath(task_id: str) -> str:
    return f"workspace/runs/{task_id}/"


def ensure_evidence_dir(root: Path | str, task_id: str) -> Path:
    """Create workspace/runs/<task_id>/{logs,artifacts,checks}/.gitkeep (idempotent)."""
    root_p = Path(root).resolve()
    base = root_p / "workspace" / "runs" / task_id
    base.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
    return base
