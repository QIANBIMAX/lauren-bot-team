"""Subprocess entry for cross-process lock tests.

Invoked as ``python -m lauren_team_kit.lock_probe hold|bump ...`` so the child
is a real second process on Windows (spawn) and POSIX alike.
"""

from __future__ import annotations

import sys

from lauren_team_kit.atomic_io import bump_json_counter, hold_lock_until
from lauren_team_kit.protocol import update_task


def append_task_notes(task_json: str, prefix: str, times: int) -> None:
    """Append ``times`` history notes under the task file lock."""
    for index in range(times):
        note = f"{prefix}-{index}"

        def mut(current: dict, note: str = note) -> dict:
            updated = dict(current)
            history = list(updated.get("history") or [])
            history.append(
                {
                    "at": note,
                    "actor": "proc",
                    "to": updated.get("status"),
                    "note": note,
                }
            )
            updated["history"] = history
            return updated

        update_task(task_json, mut)


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
    if cmd == "notes":
        if len(args) != 4:
            print("notes TASK PREFIX TIMES", file=sys.stderr)
            return 2
        append_task_notes(args[1], args[2], int(args[3]))
        return 0
    print(f"unknown {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
