"""W6: runtime schema is packaged, and install scripts do not widen policy."""

from __future__ import annotations

import json
from pathlib import Path

from lauren_team_kit.protocol import schema_path

ROOT = Path(__file__).resolve().parents[2]


def test_schema_copies_match_and_runtime_uses_package_data() -> None:
    paths = [
        ROOT / "lauren-team-kit" / "contracts" / "task-protocol.schema.json",
        ROOT / "lauren-team-kit" / "schemas" / "task-protocol.schema.json",
        ROOT / "lauren-team-kit" / "src" / "lauren_team_kit" / "data" / "task-protocol.schema.json",
    ]
    parsed = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert parsed[0] == parsed[1] == parsed[2]
    assert schema_path().resolve() == paths[2].resolve()
    assert "exec" in parsed[0]["properties"]["acceptance"]["items"]["properties"]


def test_bootstrap_scripts_stay_inside_the_clone() -> None:
    sh = (ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "bootstrap.ps1").read_text(encoding="utf-8")
    scenario = (ROOT / "lauren-team-kit" / "scripts" / "run-scenario.ps1").read_text(encoding="utf-8")
    for text in (sh, ps1, scenario):
        assert "Set-ExecutionPolicy" not in text
        assert "sk-" not in text
        assert "safe.directory" not in text
    assert "not overwritten" in sh or "not overwritten" in ps1
    assert "reuse existing .venv" in sh
    assert "reuse existing .venv" in ps1
