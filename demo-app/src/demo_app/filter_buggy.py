"""故意有缺陷的筛选实现（C2 round1 预置缺陷）。

空 / 空白 query 时抛出未捕获的 ValueError，模拟修复前行为。
正常关键词与 status 过滤逻辑与 filter.py 一致，便于对照。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


def filter_tasks(
    tasks: Sequence[Mapping[str, Any]],
    *,
    status: Optional[str] = None,
    query: Optional[str] = None,
) -> list[dict[str, Any]]:
    """有缺陷的筛选：空 query 抛异常（非安全返回 []）。"""
    if query is not None and str(query).strip() == "":
        raise ValueError("empty query is not allowed (buggy preset for C2)")

    result: list[dict[str, Any]] = []
    for raw in tasks:
        item = dict(raw)
        if status is not None and item.get("status") != status:
            continue
        if query is not None:
            q = str(query)
            hay = f"{item.get('title', '')} {item.get('description', '')}"
            if q not in hay:
                continue
        result.append(item)
    return result
