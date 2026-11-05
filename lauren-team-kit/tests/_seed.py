"""Shared helpers to seed trusted verification evidence after T1 authz."""

from __future__ import annotations

from typing import Any

from lauren_team_kit.protocol import record_check, set_artifact_commit


def seed_trusted_pass(
    task: dict[str, Any],
    *,
    commit: str,
    acceptance_id: str = "A1",
    executed: bool = True,
    exit_code: int = 0,
    result: str = "pass",
) -> dict[str, Any]:
    task = set_artifact_commit(
        task, commit=commit, actor="developer", role="developer"
    )
    task = record_check(
        task,
        acceptance_id=acceptance_id,
        executed=executed,
        exit_code=exit_code,
        bound_commit=commit,
        result=result,
        actor="verifier",
        role="verifier",
    )
    return task
