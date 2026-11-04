#!/usr/bin/env bash
# demo-c7 Lite L4：预算硬门（attempts / tokens）超限 → 受阻 BUDGET_*
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TASK_ID=demo-c7
RUN_DIR="${ROOT}/workspace/runs/${TASK_ID}"
LOG_DIR="${RUN_DIR}/logs"
PY="${KIT_ROOT}/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
KIT=("$PY" -m lauren_team_kit)
mkdir -p "$LOG_DIR" "${RUN_DIR}/artifacts" "${RUN_DIR}/checks"
TRANSCRIPT="${LOG_DIR}/c7-budget-smoke.log"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }
kit_expect_fail() {
  local label="$1"; shift
  log "+ (expect fail: $label) ${KIT[*]} $*"
  set +e
  out=$("${KIT[@]}" "$@" 2>&1)
  rc=$?
  set -e
  echo "$out" | tee -a "$TRANSCRIPT"
  [[ $rc -ne 0 ]] || { log "ERROR: expected non-zero for $label"; exit 1; }
  log "(failed as expected, rc=$rc)"
  printf '%s\n' "$out"
}

log "======== demo-c7 budget smoke ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

kit create --title "C7 预算硬门" --task-id "$TASK_ID" --root "$ROOT" --force
kit set-budget --task-id "$TASK_ID" --root "$ROOT" --max-attempts 2 --max-tokens 100 --actor chief

log ""; log "======== Scene A: 第 3 次进入执行中 → BUDGET_ATTEMPTS ========"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 执行中 --actor chief --note "attempt1"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 需修改 --actor verifier --note "fail1"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 执行中 --actor developer --note "attempt2"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 需修改 --actor verifier --note "fail2"
OUT_A=$(kit_expect_fail attempts3 transition --task-id "$TASK_ID" --root "$ROOT" --to 执行中 --actor developer --note "attempt3")
echo "$OUT_A" | grep -q 'BUDGET_ATTEMPTS' || { log "ERROR: expected BUDGET_ATTEMPTS"; exit 1; }
echo "$OUT_A" | grep -q '受阻' || { log "ERROR: expected 受阻"; exit 1; }

log ""; log "======== Scene B: tokens 超额 → BUDGET_TOKENS ========"
TASK_B=demo-c7-tokens
kit create --title "C7 tokens" --task-id "$TASK_B" --root "$ROOT" --force
kit set-budget --task-id "$TASK_B" --root "$ROOT" --max-tokens 50 --max-attempts 5 --actor chief
kit record-tokens --task-id "$TASK_B" --root "$ROOT" --tokens 40 --actor developer
kit check-budget --task-id "$TASK_B" --root "$ROOT"
kit record-tokens --task-id "$TASK_B" --root "$ROOT" --tokens 20 --actor developer
OUT_B=$(kit_expect_fail tokens transition --task-id "$TASK_B" --root "$ROOT" --to 执行中 --actor chief)
echo "$OUT_B" | grep -q 'BUDGET_TOKENS' || { log "ERROR: expected BUDGET_TOKENS"; exit 1; }

log ""; log "======== Assert A task.json ========"
"$PY" - "${RUN_DIR}/task.json" <<'PY'
import json, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
assert t["status"] == "受阻", t["status"]
assert t["budget"]["attempts_used"] == 2, t["budget"]
assert t["budget"]["max_attempts"] == 2
codes = [b.get("code") for b in t.get("blockers") or []]
assert "BUDGET_ATTEMPTS" in codes, codes
assert t["resume"]["resume_point"] == "待执行"
ver = t.get("verification") or {}
assert ver.get("result") != "pass", ver
print("c7 assertions OK", t["status"], t["budget"])
PY

log ""; log "======== Scene C: 抬预算须 --allow-raise ========"
TASK_C=demo-c7-raise
kit create --title "C7 raise" --task-id "$TASK_C" --root "$ROOT" --force
kit set-budget --task-id "$TASK_C" --root "$ROOT" --max-attempts 1 --actor chief
OUT_C=$(kit_expect_fail raise set-budget --task-id "$TASK_C" --root "$ROOT" --max-attempts 3 --actor chief)
echo "$OUT_C" | grep -q 'allow-raise' || { log "ERROR: expected allow-raise refusal"; exit 1; }
kit set-budget --task-id "$TASK_C" --root "$ROOT" --max-attempts 3 --allow-raise --actor chief

log "C7 BUDGET SMOKE OK transcript=$TRANSCRIPT"
log "Asia/Shanghai end: $(date '+%Y-%m-%d %H:%M:%S %z')"
