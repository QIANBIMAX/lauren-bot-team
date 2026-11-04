#!/usr/bin/env bash
# C2 Round2：fixed，空 query 安全 + pytest；须全过
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export DEMO_FILTER_IMPL=fixed
PY="${PYTHON:-python3}"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi

EV="${ROOT}/evidence/c2/round2"
CMD_DIR="${EV}/commands"
mkdir -p "$CMD_DIR"
FIX="${ROOT}/fixtures/basic.json"
DATA="${ROOT}/data/tasks.json"
mkdir -p "${ROOT}/data"
"$PY" -m demo_app seed --fixture "$FIX" --dest "$DATA" >/dev/null

TS="$(date '+%Y-%m-%dT%H:%M:%S%z')"
{
  echo "scenario=C2-round2-pass"
  echo "impl=fixed"
  echo "timestamp=${TS}"
  echo "cwd=${ROOT}"
  echo "python=${PY}"
} > "${EV}/meta.txt"

set +e
OUT="$("$PY" -m demo_app filter --data "$DATA" --impl fixed --query "" 2>"${CMD_DIR}/empty_query.stderr")"
RC=$?
set -e

{
  echo "cmd: DEMO_FILTER_IMPL=fixed $PY -m demo_app filter --data $DATA --impl fixed --query \"\""
  echo "exit_code=${RC}"
  echo "----- stdout -----"
  echo "${OUT}"
  echo "----- stderr -----"
  cat "${CMD_DIR}/empty_query.stderr"
} > "${CMD_DIR}/empty_query.txt"

EMPTY_OK=0
if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q '\[\]'; then
  EMPTY_OK=1
fi

set +e
"$PY" -m pytest -q tests/test_filter_empty_query.py tests/test_filter.py > "${CMD_DIR}/pytest.txt" 2>&1
PY_RC=$?
set -e

OVERALL="pass"
NOTE="empty query safe + pytest passed"
if [[ "$EMPTY_OK" -ne 1 || "$PY_RC" -ne 0 ]]; then
  OVERALL="fail"
  NOTE="empty_ok=${EMPTY_OK} pytest_rc=${PY_RC}"
fi

cat > "${EV}/report.json" <<JSON
{
  "scenario": "C2",
  "round": 2,
  "impl": "fixed",
  "result": "${OVERALL}",
  "expected": "pass",
  "exit_code_empty_query": ${RC},
  "pytest_exit_code": ${PY_RC},
  "note": "${NOTE}",
  "timestamp": "${TS}",
  "commands": ["commands/empty_query.txt", "commands/pytest.txt"],
  "meta": "meta.txt"
}
JSON

if [[ "$OVERALL" != "pass" ]]; then
  echo "C2 ROUND2 FAIL: ${NOTE}" >&2
  exit 1
fi
echo "C2 ROUND2 OK (fixed empty-query + pytest)"
exit 0
