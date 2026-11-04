"""按 status / keyword / limit 筛选任务。

硬规则（对齐 M0 C1/C2）：空 query（"" 或仅空白）必须安全返回空列表，不抛异常。
query=None 表示不做关键词过滤（可仅按 status 筛）。

limit：
  None  → 不限制（现有行为）
  0     → 返回 []
  >0    → 最多返回 N 条（保持筛选顺序）
  <0    → ValueError
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence


def filter_tasks(
    tasks: Sequence[Mapping[str, Any]],
    *,
    status: Optional[str] = None,
    query: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """筛选任务列表。

    Args:
        tasks: 任务映射序列，至少含 title / status；可选 description。
        status: 若给定，仅保留 status 相等的任务。
        query: 关键词；None=不按关键词过滤；空串/空白=安全返回 []。
        limit: 最多返回条数；None=不限制；0=[]；正整数截断；负数拒绝。

    Returns:
        新列表（元素为 dict 浅拷贝视角下的原映射转 dict）。
    """
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError(f"limit must be int or None, got {type(limit).__name__}")
        if limit < 0:
            raise ValueError(f"limit must be >= 0 or None, got {limit}")

    if query is not None and str(query).strip() == "":
        return []

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

    if limit is None:
        return result
    if limit == 0:
        return []
    return result[:limit]


def load_tasks(path: str) -> list[dict[str, Any]]:
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "tasks" in data:
        tasks = data["tasks"]
    elif isinstance(data, list):
        tasks = data
    else:
        raise ValueError(f"unsupported fixture shape: {type(data)}")
    if not isinstance(tasks, Iterable):
        raise ValueError("tasks must be iterable")
    return [dict(t) for t in tasks]
