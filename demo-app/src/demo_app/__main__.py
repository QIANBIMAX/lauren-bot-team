"""CLI：python -m demo_app <filter|list|seed> ...

DEMO_FILTER_IMPL / --impl：buggy|fixed（默认 fixed）。C2 用 buggy 演示预置缺陷。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

from demo_app.filter import load_tasks
from demo_app.seed import default_data_path, seed


def _resolve_data(path: str | None) -> Path:
    if path:
        return Path(path)
    return default_data_path()


def _resolve_impl(explicit: str | None) -> str:
    raw = (explicit or os.environ.get("DEMO_FILTER_IMPL") or "fixed").strip().lower()
    if raw not in {"fixed", "buggy"}:
        raise SystemExit(f"invalid filter impl: {raw!r} (want fixed|buggy)")
    return raw


def _filter_fn(impl: str) -> Callable[..., list]:
    if impl == "buggy":
        from demo_app.filter_buggy import filter_tasks as fn
    else:
        from demo_app.filter import filter_tasks as fn
    return fn


def cmd_seed(ns: argparse.Namespace) -> int:
    out = seed(Path(ns.fixture), Path(ns.dest) if ns.dest else None)
    print(out)
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    data = _resolve_data(ns.data)
    if not data.exists():
        print(f"data not found: {data}", file=sys.stderr)
        return 2
    tasks = load_tasks(str(data))
    print(json.dumps(tasks, ensure_ascii=False, indent=2))
    return 0


def cmd_filter(ns: argparse.Namespace) -> int:
    data = _resolve_data(ns.data)
    if not data.exists():
        print(f"data not found: {data}", file=sys.stderr)
        return 2
    impl = _resolve_impl(getattr(ns, "impl", None))
    tasks = load_tasks(str(data))
    # --query 未传 → None；显式传空串 → ""（fixed 安全空列表；buggy 抛异常）
    query = ns.query  # may be None
    filtered = _filter_fn(impl)(tasks, status=ns.status, query=query)
    print(json.dumps(filtered, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m demo_app")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seed", help="load fixture into data/tasks.json")
    s.add_argument("--fixture", required=True)
    s.add_argument("--dest", default=None)
    s.set_defaults(func=cmd_seed)

    s = sub.add_parser("list", help="list all tasks as JSON")
    s.add_argument("--data", default=None)
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("filter", help="filter by status and/or keyword")
    s.add_argument("--data", default=None)
    s.add_argument("--status", default=None, help="e.g. open | done")
    s.add_argument(
        "--query",
        default=None,
        help='keyword; empty string: fixed→[]; buggy→ValueError; omit for status-only',
    )
    s.add_argument(
        "--impl",
        default=None,
        choices=["fixed", "buggy"],
        help="filter implementation (default: DEMO_FILTER_IMPL or fixed)",
    )
    s.set_defaults(func=cmd_filter)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
