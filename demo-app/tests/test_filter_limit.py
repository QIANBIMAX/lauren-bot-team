"""C5：filter_tasks / CLI --limit 行为。"""

from __future__ import annotations

from pathlib import Path

import pytest

from demo_app import __main__ as cli
from demo_app.filter import filter_tasks, load_tasks

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "basic.json"


@pytest.fixture
def tasks():
    return load_tasks(str(FIXTURE))


def test_limit_none_unlimited(tasks):
    assert filter_tasks(tasks, query="发票", limit=None) == filter_tasks(tasks, query="发票")


def test_limit_zero_returns_empty(tasks):
    assert filter_tasks(tasks, limit=0) == []
    assert filter_tasks(tasks, status="open", limit=0) == []
    assert filter_tasks(tasks, query="发票", limit=0) == []


def test_limit_one_keeps_order(tasks):
    full = filter_tasks(tasks, query="发票")
    assert len(full) >= 2
    got = filter_tasks(tasks, query="发票", limit=1)
    assert len(got) == 1
    assert got[0] == full[0]


def test_limit_larger_than_result(tasks):
    full = filter_tasks(tasks, status="open")
    got = filter_tasks(tasks, status="open", limit=len(full) + 10)
    assert got == full


def test_limit_negative_raises(tasks):
    with pytest.raises(ValueError, match="limit"):
        filter_tasks(tasks, limit=-1)
    with pytest.raises(ValueError, match="limit"):
        filter_tasks(tasks, query="发票", limit=-3)


def test_empty_query_still_safe_with_limit(tasks):
    assert filter_tasks(tasks, query="", limit=5) == []
    assert filter_tasks(tasks, query="   ", limit=0) == []


def test_cli_limit_one(capsys, tmp_path):
    data = tmp_path / "tasks.json"
    data.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    rc = cli.main(["filter", "--data", str(data), "--query", "发票", "--limit", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    import json

    rows = json.loads(out)
    assert len(rows) == 1
    assert "发票" in rows[0]["title"]


def test_cli_limit_zero(capsys, tmp_path):
    data = tmp_path / "tasks.json"
    data.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    rc = cli.main(["filter", "--data", str(data), "--status", "open", "--limit", "0"])
    assert rc == 0
    import json

    assert json.loads(capsys.readouterr().out) == []


def test_cli_limit_negative_exits_nonzero(capsys, tmp_path):
    data = tmp_path / "tasks.json"
    data.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    rc = cli.main(["filter", "--data", str(data), "--limit", "-1"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "limit" in err.lower()
