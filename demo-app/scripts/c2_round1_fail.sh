#!/usr/bin/env bash
# C2 Round1：强制 buggy，空 query 必须失败；成功演示失败 → exit 0
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export DEMO_FILTER_IMPL=buggy
PY="${PYTHON:-python3}"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi

EV="${ROOT}/evidence/c2/round1"
CMD_DIR="${EV}/commands"
mkdir -p "$CMD_DIR"
FIX="${ROOT}/fixtures/basic.json"
DATA="${ROOT}/data/tasks.json"
mkdir -p "${ROOT}/data"
"$PY" -m demo_app seed --fixture "$FIX" --dest "$DATA" >/dev/null

TS="$(date '+%Y-%m-%dT%H:%M:%S%z')"
META_FILE="${EV}/meta.txt"
REPORT="${EV}/report.json"
CMD_LOG="${CMD_DIR}/empty_query.txt"

{
  echo "scenario=C2-round1-fail"
  echo "impl=buggy"
  echo "timestamp=${TS}"
  echo "cwd=${ROOT}"
  echo "python=${PY}"
} > "$META_FILE"

set +e
OUT="$("$PY" -m demo_app filter --data "$DATA" --impl buggy --query "" 2>"${CMD_DIR}/empty_query.stderr")"
RC=$?
set -e

{
  echo "cmd: DEMO_FILTER_IMPL=buggy $PY -m demo_app filter --data $DATA --impl buggy --query \"\""
  echo "exit_code=${RC}"
  echo "----- stdout -----"
  echo "${OUT}"
  echo "----- stderr -----"
  cat "${CMD_DIR}/empty_query.stderr"
} > "$CMD_LOG"

# 期望失败：非 0，或 stdout 不是安全空列表
FAILED=0
if [[ "$RC" -ne 0 ]]; then
  FAILED=1
elif ! echo "$OUT" | grep -q '\[\]'; then
  # 若意外 exit 0 但无 []，也算「坏」
  FAILED=1
else
  # exit 0 且得到 [] → buggy 未生效，演示失败
  FAILED=0
fi

if [[ "$FAILED" -eq 1 ]]; then
  cat > "$REPORT" <<JSON
{
  "scenario": "C2",
  "round": 1,
  "impl": "buggy",
  "result": "fail",
  "expected": "fail",
  "exit_code": ${RC},
  "note": "empty query raised / non-zero — preset defect demonstrated",
  "timestamp": "${TS}",
  "commands": ["commands/empty_query.txt"],
  "meta": "meta.txt"
}
JSON
  echo "C2 ROUND1 OK (failure demonstrated, exit_code=${RC})"
  exit 0
fi

cat > "$REPORT" <<JSON
{
  "scenario": "C2",
  "round": 1,
  "impl": "buggy",
  "result": "unexpected_pass",
  "expected": "fail",
  "exit_code": ${RC},
  "note": "buggy impl returned [] with exit 0 — defect not active",
  "timestamp": "${TS}",
  "commands": ["commands/empty_query.txt"],
  "meta": "meta.txt"
}
JSON
echo "C2 ROUND1 FAIL: buggy impl unexpectedly passed" >&2
exit 1
