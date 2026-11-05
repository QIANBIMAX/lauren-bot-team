#!/usr/bin/env bash
# Thin install entry for Linux and macOS. Touches only this clone:
# creates .venv when missing, and does not delete an existing one.
# Does not set git config, execution policy, or proxy variables.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ -n "${LAUREN_PYTHON:-}" && -x "${LAUREN_PYTHON}" ]]; then
  PY="$LAUREN_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  PY="$(command -v python)"
fi
if [[ -d .venv ]]; then
  echo "reuse existing .venv (not overwritten)"
else
  "$PY" -m venv .venv
fi
if [[ -x .venv/bin/python ]]; then
  VENV_PY="$ROOT/.venv/bin/python"
elif [[ -x .venv/Scripts/python.exe ]]; then
  VENV_PY="$ROOT/.venv/Scripts/python.exe"
else
  echo "venv has no python interpreter" >&2
  exit 1
fi
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install "$ROOT/lauren-team-kit"
echo "doctor: $VENV_PY -m lauren_team_kit doctor"
echo "scenario: $VENV_PY -m lauren_team_kit.scenarios c1 --root $ROOT"
echo "dev tests (optional): $VENV_PY -m pip install 'pytest>=7' && cd lauren-team-kit && $VENV_PY -m pytest -q"
