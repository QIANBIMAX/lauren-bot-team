"""W4: one Python scenario runner; shell scripts are wrappers only."""

from __future__ import annotations

from pathlib import Path

import pytest

from lauren_team_kit.scenarios import ScenarioError, scenario_c1, scenario_c2, scenario_c6, scenario_c7, scenario_c8, scenario_t1, scenario_t2, scenario_t3, scenario_t4


def test_c1_real_commit_one_round(tmp_path: Path) -> None:
    result = scenario_c1(tmp_path, task_id=None, team_id=None, force=False)
    assert result["ok"] is True
    assert result["merged"] is False
    assert len(result["commit"]) >= 7


def test_c2_fail_then_fix_uses_real_commit(tmp_path: Path) -> None:
    result = scenario_c2(tmp_path, task_id=None, team_id=None, force=False)
    assert result["historical_placeholder_sha"] is False
    assert result["commit"] != "c2fixed01"


def test_c6_resume_keeps_commit(tmp_path: Path) -> None:
    result = scenario_c6(tmp_path, task_id=None, team_id=None, force=False)
    assert result["ok"] is True


def test_c7_budget(tmp_path: Path) -> None:
    assert scenario_c7(tmp_path, task_id=None, team_id=None, force=False)["ok"] is True


def test_c8_publish_roundtrip(tmp_path: Path) -> None:
    result = scenario_c8(tmp_path, task_id=None, team_id=None, force=False)
    store = tmp_path / "lauren-team-kit" / "lessons" / "store" / f"{result['lesson_id']}.json"
    assert store.is_file()


def test_team_scenarios_do_not_claim_delegate(tmp_path: Path) -> None:
    assert scenario_t1(tmp_path, task_id=None, team_id=None, force=False)["ok"]
    t2 = scenario_t2(tmp_path, task_id=None, team_id=None, force=False)
    assert t2["omb_delegation"] == "blocked"
    assert t2["mode"] == "local"
    assert scenario_t3(tmp_path, task_id=None, team_id=None, force=False)["mode"] == "local"
    t4 = scenario_t4(tmp_path, task_id=None, team_id=None, force=False)
    assert t4["omb_delegation"] == "blocked"


def test_refuse_overwrite_without_force(tmp_path: Path) -> None:
    scenario_c1(tmp_path, task_id="keep-me", team_id=None, force=False)
    with pytest.raises(ScenarioError, match="不使用 --force"):
        scenario_c1(tmp_path, task_id="keep-me", team_id=None, force=False)
