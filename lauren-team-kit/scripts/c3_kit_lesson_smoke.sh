#!/usr/bin/env bash
# Thin POSIX wrapper. The scenario lives in Python so Windows and Ubuntu
# call the same runner: python -m lauren_team_kit.scenarios c3
# Windows: lauren-team-kit/scripts/run-scenario.ps1 c3
# Does not pass --force unless you add it. Existing demo dirs are kept.
# POSIX shell is only this wrapper; the scenario itself does not require Bash.
set -euo pipefail
NAME="c3"
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
if [[ -n "${LAUREN_PYTHON:-}" && -x "${LAUREN_PYTHON}" ]]; then
  PY="$LAUREN_PYTHON"
elif [[ -x "${KIT_ROOT}/.venv/bin/python" ]]; then
  PY="${KIT_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  PY="$(command -v python)"
fi
exec "$PY" -m lauren_team_kit.scenarios "$NAME" --root "$ROOT" "$@"
