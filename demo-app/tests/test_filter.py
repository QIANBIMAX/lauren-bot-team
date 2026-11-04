from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo_app.filter import filter_tasks, load_tasks

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "basic.json"


@pytest.fixture
def tasks():
    return load_tasks(str(FIXTURE))


def test_keyword_hit_chinese_invoice(tasks):
    got = filter_tasks(tasks, query="发票")
    titles = [t["title"] for t in got]
    assert "报销发票核对" in titles
    assert "发票模板更新" in titles
    assert "会议室预约" not in titles


def test_status_filter_open(tasks):
    got = filter_tasks(tasks, status="open")
    assert all(t["status"] == "open" for t in got)
    assert any(t["id"] == "t2" for t in got)
    assert all(t["id"] != "t3" for t in got)


def test_status_and_keyword(tasks):
    got = filter_tasks(tasks, status="open", query="发票")
    assert len(got) == 1
    assert got[0]["id"] == "t1"


def test_empty_query_safe_returns_empty(tasks):
    assert filter_tasks(tasks, query="") == []
    assert filter_tasks(tasks, query="   ") == []
    assert filter_tasks(tasks, status="open", query="") == []


def test_none_query_allows_status_only(tasks):
    got = filter_tasks(tasks, status="done", query=None)
    assert len(got) >= 1
    assert all(t["status"] == "done" for t in got)
    assert all(t["id"] != "t2" for t in got)


def test_fixture_has_invoice_and_statuses():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    titles = [t["title"] for t in raw["tasks"]]
    assert any("发票" in t for t in titles)
    statuses = {t["status"] for t in raw["tasks"]}
    assert statuses >= {"open", "done"}
