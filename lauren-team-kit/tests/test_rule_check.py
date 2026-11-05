from pathlib import Path
import re
import pytest
from lauren_team_kit.rule_check import _substitute_python, parse_probes, run_rule

ROOT = Path(__file__).resolve().parents[2]
RULE = ROOT / "lauren-team-kit/rules/filter-empty-query.md"
DEMO = ROOT / "demo-app"
pytestmark = pytest.mark.skipif(not DEMO.is_dir(), reason="demo-app absent")

def test_parse_probes():
    assert len(parse_probes(RULE)) == 3

def test_fixed_pass():
    assert run_rule(RULE, DEMO, "fixed")["ok"]

def test_buggy_fail():
    assert not run_rule(RULE, DEMO, "buggy")["ok"]


def test_substitute_python_keeps_windows_backslashes():
    path = "C:\\hostedtoolcache\\windows\\Python\\python.exe"
    with pytest.raises(re.error):
        re.sub(r"\bpython\b", path, "python -m demo_app", count=1)
    out = _substitute_python("python -m demo_app", path)
    assert out == "'" + path + "' -m demo_app"
    assert "\\h" in out
