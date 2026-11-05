"""Lite-E: static pack validation + checklist docs present."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "lauren-team-kit"
SCRIPT = KIT / "scripts" / "validate_lite_pack.py"


def test_validate_lite_pack_script_ok():
    assert SCRIPT.is_file(), "validate_lite_pack.py missing"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(KIT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "LITE PACK OK" in proc.stdout


def test_lite_e_docs_present():
    for rel in (
        "docs/lite-release-checklist.md",
        "docs/lite-failure-recovery.md",
        "docs/platforms.md",
        "docs/compatibility.md",
    ):
        p = ROOT / rel
        assert p.is_file(), f"missing {rel}"
    checklist = (ROOT / "docs/lite-release-checklist.md").read_text(encoding="utf-8")
    assert "§六" in checklist or "六" in checklist
    assert "预览限制" in checklist
    assert "OMB GUI" in checklist
    recovery = (ROOT / "docs/lite-failure-recovery.md").read_text(encoding="utf-8")
    for needle in ("jsonschema", "预算", "取消", "resume"):
        assert needle in recovery
