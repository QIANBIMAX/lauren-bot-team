"""Exit 0 iff filter_tasks(..., limit=-1) raises ValueError mentioning limit."""
from __future__ import annotations

from demo_app.filter import filter_tasks, load_tasks

tasks = load_tasks("fixtures/basic.json")
try:
    filter_tasks(tasks, limit=-1)
except ValueError as exc:
    if "limit" in str(exc).lower():
        raise SystemExit(0)
    raise SystemExit(f"unexpected ValueError: {exc}") from exc
raise SystemExit("expected ValueError for limit=-1")
