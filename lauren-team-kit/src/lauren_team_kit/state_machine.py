"""Task status transitions for lauren-task-protocol/0.1."""

from __future__ import annotations

from typing import Iterable

ALLOWED: dict[str, frozenset[str]] = {
    "待执行": frozenset({"执行中", "已取消", "受阻"}),
    "执行中": frozenset({"待验证", "需修改", "受阻", "已取消"}),
    "待验证": frozenset({"验证通过", "需修改", "受阻"}),
    "验证通过": frozenset({"待合并", "需修改"}),
    "待合并": frozenset({"已完成", "合并失败"}),
    "合并失败": frozenset({"待合并", "需修改", "已取消"}),
    "需修改": frozenset({"执行中", "已取消", "受阻"}),
    "受阻": frozenset({"待执行", "执行中", "待验证", "已取消"}),
    "已完成": frozenset(),
    "已取消": frozenset(),
}

TERMINAL = frozenset({"已完成", "已取消"})

ALL_STATUSES = frozenset(ALLOWED.keys())


class IllegalTransitionError(ValueError):
    """Raised when a status change is not allowed."""


def can_transition(from_status: str, to_status: str) -> bool:
    if from_status not in ALLOWED:
        return False
    return to_status in ALLOWED[from_status]


def allowed_targets(from_status: str) -> frozenset[str]:
    return ALLOWED.get(from_status, frozenset())


def apply_transition(from_status: str, to_status: str) -> str:
    if from_status not in ALLOWED:
        raise IllegalTransitionError(f"未知状态: {from_status!r}")
    if to_status not in ALL_STATUSES:
        raise IllegalTransitionError(f"未知目标状态: {to_status!r}")
    if to_status not in ALLOWED[from_status]:
        targets = ", ".join(sorted(ALLOWED[from_status])) or "(终态，无出边)"
        raise IllegalTransitionError(
            f"非法迁移: {from_status} → {to_status}；允许: {targets}"
        )
    return to_status


def assert_known_statuses(statuses: Iterable[str]) -> None:
    unknown = [s for s in statuses if s not in ALL_STATUSES]
    if unknown:
        raise IllegalTransitionError(f"未知状态: {unknown}")
