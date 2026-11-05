from pathlib import Path
import re
import sys
import pytest
from lauren_team_kit.rule_check import _substitute_python, parse_probes, run_rule

ROOT = Path(__file__).resolve().parents[2]
RULE = ROOT / "lauren-team-kit/rules/filter-empty-query.md"
BASH_ONLY = ROOT / "lauren-team-kit/rules/c8-empty-safe.md"
DEMO = ROOT / "demo-app"
pytestmark = pytest.mark.skipif(not DEMO.is_dir(), reason="demo-app absent")


def _ensure_demo_data() -> None:
    data = DEMO / "data" / "tasks.json"
    if data.is_file():
        return
    sys.path.insert(0, str(DEMO / "src"))
    from demo_app.seed import seed

    seed(DEMO / "fixtures" / "basic.json", data)


def test_parse_probes():
    assert len(parse_probes(RULE)) == 3

def test_fixed_pass():
    _ensure_demo_data()
    report = run_rule(RULE, DEMO, "fixed")
    assert report["ok"] is True
    assert report["status"] == "pass"

def test_buggy_fail():
    _ensure_demo_data()
    report = run_rule(RULE, DEMO, "buggy")
    assert report["ok"] is False
    assert report["status"] == "fail"


def test_structured_passes_when_bash_cannot_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_demo_data()
    monkeypatch.setattr("lauren_team_kit.rule_check.bash_supported", lambda: False)
    report = run_rule(RULE, DEMO, "fixed")
    assert report["ok"] is True
    assert report["status"] == "pass"
    assert report["bash"]["status"] == "cannot_run"
    assert report["bash"]["ok"] is False


def test_bash_only_rule_is_cannot_run_not_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("lauren_team_kit.rule_check.bash_supported", lambda: False)
    report = run_rule(BASH_ONLY, tmp_path)
    assert report["ok"] is False
    assert report["status"] == "cannot_run"


def test_substitute_python_keeps_windows_backslashes():
    path = "C:\\hostedtoolcache\\windows\\Python\\python.exe"
    with pytest.raises(re.error):
        re.sub(r"\bpython\b", path, "python -m demo_app", count=1)
    out = _substitute_python("python -m demo_app", path)
    assert out == "'" + path + "' -m demo_app"
    assert "\\h" in out
