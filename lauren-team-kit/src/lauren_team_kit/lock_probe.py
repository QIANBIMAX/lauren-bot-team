"""Subprocess entry for cross-process lock tests.

Invoked as ``python -m lauren_team_kit.lock_probe hold|bump ...`` so the child
is a real second process on Windows (spawn) and POSIX alike.
"""

from __future__ import annotations

import sys

from lauren_team_kit.atomic_io import bump_json_counter, hold_lock_until


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: lock_probe hold|bump ...", file=sys.stderr)
        return 2
    cmd = args[0]
    if cmd == "hold":
        if len(args) != 4:
            print("hold LOCK START RELEASE", file=sys.stderr)
            return 2
        hold_lock_until(args[1], args[2], args[3])
        return 0
    if cmd == "bump":
        if len(args) != 3:
            print("bump PATH TIMES", file=sys.stderr)
            return 2
        bump_json_counter(args[1], int(args[2]))
        return 0
    print(f"unknown {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
