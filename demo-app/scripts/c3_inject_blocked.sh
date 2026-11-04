#!/usr/bin/env bash
# C3：注入同类空 query 缺陷（buggy），已发布规则探针必须拦住。
# 成功演示拦截 → exit 0；若 buggy 竟通过 → exit 1（规则泄漏）
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export DEMO_FILTER_IMPL=buggy
PY="${PYTHON:-python3}"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi

EV="${ROOT}/evidence/c3/blocked"
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
  echo "scenario=C3-inject-blocked"
  echo "impl=buggy"
  echo "rule=${RULE_REL}"
  echo "rule_exists=$([ -f "$RULE_ABS" ] && echo yes || echo no)"
  echo "timestamp=${TS}"
  echo "cwd=${ROOT}"
  echo "python=${PY}"
  echo "lesson=published filter-empty-query from C2"
} > "${EV}/meta.txt"

# Probe 1: CLI empty query (must NOT be safe under buggy)
set +e
OUT="$("$PY" -m demo_app filter --data "$DATA" --impl buggy --query "" 2>"${CMD_DIR}/cli_empty.stderr")"
CLI_RC=$?
set -e
{
  echo "cmd: DEMO_FILTER_IMPL=buggy $PY -m demo_app filter --data $DATA --impl buggy --query \"\""
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

# Probe 2: library call must return [] without raise (rule safety)
set +e
"$PY" - <<'PY' >"${CMD_DIR}/lib_safe.txt" 2>&1
from demo_app.filter_buggy import filter_tasks
assert filter_tasks([], query="") == []
assert filter_tasks([], query="   ") == []
print("lib_safe_ok")
PY
LIB_RC=$?
set -e
echo "exit_code=${LIB_RC}" >> "${CMD_DIR}/lib_safe.txt"

# Probe 3: published rule file must exist (experience landed)
RULE_OK=0
if [[ -f "$RULE_ABS" ]]; then
  RULE_OK=1
  echo "found: ${RULE_ABS}" > "${CMD_DIR}/rule_file.txt"
else
  echo "MISSING: ${RULE_ABS}" > "${CMD_DIR}/rule_file.txt"
fi

# blocked if CLI unsafe OR lib raises (expected for buggy)
CAUGHT=0
if [[ "$CLI_SAFE" -eq 0 || "$LIB_RC" -ne 0 ]]; then
  CAUGHT=1
fi

if [[ "$RULE_OK" -ne 1 ]]; then
  cat > "${EV}/report.json" <<JSON
{
  "scenario": "C3",
  "round": "blocked",
  "impl": "buggy",
  "result": "missing_rule",
  "expected": "blocked",
  "cli_safe": ${CLI_SAFE},
  "cli_exit": ${CLI_RC},
  "lib_exit": ${LIB_RC},
  "rule_ok": ${RULE_OK},
  "note": "published rule file missing — experience not reusable",
  "timestamp": "${TS}",
  "commands": ["commands/cli_empty.txt", "commands/lib_safe.txt", "commands/rule_file.txt"],
  "meta": "meta.txt",
  "rule": "${RULE_REL}"
}
JSON
  echo "C3 BLOCKED FAIL: published rule missing" >&2
  exit 1
fi

if [[ "$CAUGHT" -eq 1 ]]; then
  cat > "${EV}/report.json" <<JSON
{
  "scenario": "C3",
  "round": "blocked",
  "impl": "buggy",
  "result": "blocked",
  "expected": "blocked",
  "cli_safe": ${CLI_SAFE},
  "cli_exit": ${CLI_RC},
  "lib_exit": ${LIB_RC},
  "rule_ok": ${RULE_OK},
  "note": "published empty-query rule probes caught reintroduced defect",
  "timestamp": "${TS}",
  "commands": ["commands/cli_empty.txt", "commands/lib_safe.txt", "commands/rule_file.txt"],
  "meta": "meta.txt",
  "rule": "${RULE_REL}"
}
JSON
  echo "C3 BLOCKED OK (defect caught by published rule, cli_safe=${CLI_SAFE} lib_rc=${LIB_RC})"
  exit 0
fi

cat > "${EV}/report.json" <<JSON
{
  "scenario": "C3",
  "round": "blocked",
  "impl": "buggy",
  "result": "leak",
  "expected": "blocked",
  "cli_safe": ${CLI_SAFE},
  "cli_exit": ${CLI_RC},
  "lib_exit": ${LIB_RC},
  "rule_ok": ${RULE_OK},
  "note": "buggy passed rule probes — experience reuse failed",
  "timestamp": "${TS}",
  "commands": ["commands/cli_empty.txt", "commands/lib_safe.txt", "commands/rule_file.txt"],
  "meta": "meta.txt",
  "rule": "${RULE_REL}"
}
JSON
echo "C3 BLOCKED FAIL: rule leak — buggy unexpectedly safe" >&2
exit 1
