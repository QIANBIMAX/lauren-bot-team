import pytest

from lauren_team_kit.state_machine import (
    ALLOWED,
    IllegalTransitionError,
    apply_transition,
    can_transition,
)


def test_happy_path_create_to_verify():
    assert can_transition("待执行", "执行中")
    assert apply_transition("执行中", "待验证") == "待验证"


def test_terminals_have_no_exits():
    assert ALLOWED["已完成"] == frozenset()
    assert ALLOWED["已取消"] == frozenset()
    with pytest.raises(IllegalTransitionError):
        apply_transition("已完成", "执行中")


def test_illegal_rejected():
    with pytest.raises(IllegalTransitionError) as ei:
        apply_transition("待执行", "已完成")
    assert "非法迁移" in str(ei.value)


def test_unknown_status():
    with pytest.raises(IllegalTransitionError):
        apply_transition("不存在", "执行中")
