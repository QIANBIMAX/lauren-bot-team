"""C2：空 query 在 fixed / buggy 两实现下的对照测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from demo_app.filter import filter_tasks as filter_fixed
from demo_app.filter import load_tasks
from demo_app.filter_buggy import filter_tasks as filter_buggy

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "basic.json"


@pytest.fixture
def tasks():
    return load_tasks(str(FIXTURE))


def test_fixed_empty_query_returns_empty(tasks):
    assert filter_fixed(tasks, query="") == []
    assert filter_fixed(tasks, query="   ") == []
    assert filter_fixed(tasks, status="open", query="") == []


def test_buggy_empty_query_raises(tasks):
    with pytest.raises(ValueError, match="empty query"):
        filter_buggy(tasks, query="")
    with pytest.raises(ValueError, match="empty query"):
        filter_buggy(tasks, query="   ")
    with pytest.raises(ValueError, match="empty query"):
        filter_buggy(tasks, status="open", query="")


def test_buggy_normal_query_still_filters(tasks):
    got = filter_buggy(tasks, status="open", query="发票")
    assert len(got) == 1
    assert got[0]["id"] == "t1"
