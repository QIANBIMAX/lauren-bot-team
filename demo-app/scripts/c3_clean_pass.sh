#!/usr/bin/env bash
# C3：fixed 实现必须通过同一已发布规则探针（不得误伤）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export DEMO_FILTER_IMPL=fixed
PY="${PYTHON:-python3}"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi

EV="${ROOT}/evidence/c3/clean"
CMD_DIR="${EV}/commands"
mkdir -p "$CMD_DIR"
FIX="${ROOT}/fixtures/basic.json"
DATA="${ROOT}/data/tasks.json"
mkdir -p "${ROOT}/data"
"$PY" -m demo_app seed --fixture "$FIX" --dest "$DATA" >/dev/null

RULE_REL="lauren-team-kit/rules/filter-empty-query.md"
RULE_ABS="$(cd "${ROOT}/.." && pwd)/${RULE_REL}"
TS="$(date '+%Y-%m-%dT%H:%M:%S%z')"
{
  echo "scenario=C3-clean-pass"
  echo "impl=fixed"
  echo "rule=${RULE_REL}"
  echo "rule_exists=$([ -f "$RULE_ABS" ] && echo yes || echo no)"
  echo "timestamp=${TS}"
  echo "cwd=${ROOT}"
  echo "python=${PY}"
} > "${EV}/meta.txt"

set +e
OUT="$("$PY" -m demo_app filter --data "$DATA" --impl fixed --query "" 2>"${CMD_DIR}/cli_empty.stderr")"
CLI_RC=$?
set -e
{
  echo "cmd: DEMO_FILTER_IMPL=fixed $PY -m demo_app filter --data $DATA --impl fixed --query \"\""
  echo "exit_code=${CLI_RC}"
  echo "----- stdout -----"
  echo "${OUT}"
  echo "----- stderr -----"
  cat "${CMD_DIR}/cli_empty.stderr"
} > "${CMD_DIR}/cli_empty.txt"

CLI_SAFE=0
if [[ "$CLI_RC" -eq 0 ]] && echo "$OUT" | grep -q '\[\]'; then
  CLI_SAFE=1
fi

set +e
"$PY" - <<'PY' >"${CMD_DIR}/lib_safe.txt" 2>&1
from demo_app.filter import filter_tasks
assert filter_tasks([], query="") == []
assert filter_tasks([], query="   ") == []
print("lib_safe_ok")
PY
LIB_RC=$?
set -e
echo "exit_code=${LIB_RC}" >> "${CMD_DIR}/lib_safe.txt"

RULE_OK=0
[[ -f "$RULE_ABS" ]] && RULE_OK=1
echo "rule_ok=${RULE_OK} path=${RULE_ABS}" > "${CMD_DIR}/rule_file.txt"

OVERALL="pass"
NOTE="fixed passes published empty-query rule probes"
if [[ "$CLI_SAFE" -ne 1 || "$LIB_RC" -ne 0 || "$RULE_OK" -ne 1 ]]; then
  OVERALL="fail"
  NOTE="cli_safe=${CLI_SAFE} lib_rc=${LIB_RC} rule_ok=${RULE_OK}"
fi

cat > "${EV}/report.json" <<JSON
{
  "scenario": "C3",
  "round": "clean",
  "impl": "fixed",
  "result": "${OVERALL}",
  "expected": "pass",
  "cli_safe": ${CLI_SAFE},
  "cli_exit": ${CLI_RC},
  "lib_exit": ${LIB_RC},
  "rule_ok": ${RULE_OK},
  "note": "${NOTE}",
  "timestamp": "${TS}",
  "commands": ["commands/cli_empty.txt", "commands/lib_safe.txt", "commands/rule_file.txt"],
  "meta": "meta.txt",
  "rule": "${RULE_REL}"
}
JSON

if [[ "$OVERALL" != "pass" ]]; then
  echo "C3 CLEAN FAIL: ${NOTE}" >&2
  exit 1
fi
echo "C3 CLEAN OK (fixed passes published rule)"
exit 0
