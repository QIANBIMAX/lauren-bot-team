"""Demo-local merge: init integration branch + confirm-gated merge (never push)."""

from lauren_team_kit.merge.execute import (
    EXIT_AWAIT_CONFIRM,
    EXIT_FAIL,
    EXIT_OK,
    EXIT_USAGE,
    execute_merge,
    init_integration_branch,
    plan_merge,
)

__all__ = [
    "EXIT_AWAIT_CONFIRM",
    "EXIT_FAIL",
    "EXIT_OK",
    "EXIT_USAGE",
    "execute_merge",
    "init_integration_branch",
    "plan_merge",
]
