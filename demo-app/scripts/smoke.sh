#!/usr/bin/env bash
# Demo C1 筛选烟雾：含中文关键词；空 query 必须 exit 0 且输出 []
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
PY="${PYTHON:-python3}"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi

FIX="${ROOT}/fixtures/basic.json"
DATA="${ROOT}/data/tasks.json"
mkdir -p "${ROOT}/data"
"$PY" -m demo_app seed --fixture "$FIX" --dest "$DATA"

echo "== filter open + 发票 =="
OUT="$("$PY" -m demo_app filter --data "$DATA" --status open --query "发票")"
echo "$OUT" | grep -q "发票"
echo "$OUT" | grep -q "报销发票核对"

echo "== filter done 不含 open-only-task =="
OUT2="$("$PY" -m demo_app filter --data "$DATA" --status done)"
echo "$OUT2" | grep -vq "open-only-task" || {
  # grep -v 对整段 JSON：若含 open-only-task 则失败
  if echo "$OUT2" | grep -q "open-only-task"; then
    echo "FAIL: open-only-task appeared in done filter" >&2
    exit 1
  fi
}

echo "== empty query safe =="
OUT3="$("$PY" -m demo_app filter --data "$DATA" --query "")"
echo "$OUT3" | grep -q '\[\]'

echo "SMOKE OK"
