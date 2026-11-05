#!/usr/bin/env bash
# =============================================================================
# 【历史样例 / HISTORICAL SAMPLE — 非正式验收】Lite-D L8
# 本脚本保留作 C2 接线烟雾与 run 目录演示；使用占位 commit（c2fixed01），
# 与真实 Git merge-precheck 不匹配。正式验收请用 pytest：
#   lauren-team-kit/tests/test_lite_d.py::test_l8_fail_fix_reverify_real_merge
# 勿把本脚本 exit 0 当作「真实 commit / 真实合并」通过。
# =============================================================================
# C2 kit 接线烟雾：round1 硬门失败→需修改；round2 record-check 通过→验证通过（不真 merge）
set -euo pipefail

KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TASK_ID=demo-c2
RUN_DIR="${ROOT}/workspace/runs/${TASK_ID}"
LOG_DIR="${RUN_DIR}/logs"
PY="${KIT_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
KIT=("$PY" -m lauren_team_kit)

mkdir -p "$LOG_DIR" "${RUN_DIR}/artifacts/c2" "${RUN_DIR}/checks"
TRANSCRIPT="${LOG_DIR}/c2-kit-rework-smoke.log"
FAIL_LOG="${LOG_DIR}/verify-gate-fail.log"
: >"$TRANSCRIPT"

log() { echo "$*" | tee -a "$TRANSCRIPT"; }

kit() {
  log "+ ${KIT[*]} $*"
  "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"
}

kit_expect_fail() {
  log "+ (expect fail) ${KIT[*]} $*"
  set +e
  "${KIT[@]}" "$@" >"${FAIL_LOG}.tmp" 2>&1
  rc=$?
  set -e
  cat "${FAIL_LOG}.tmp" | tee -a "$TRANSCRIPT" | tee -a "$FAIL_LOG"
  rm -f "${FAIL_LOG}.tmp"
  if [[ $rc -eq 0 ]]; then
    log "ERROR: expected non-zero, got 0"
    exit 1
  fi
  log "(failed as expected, rc=$rc)"
}

log "======== C2 kit rework smoke ========"
log "ROOT=$ROOT"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

# --- create / reset task ---
kit create --title "C2 空 query 失败返工" --task-id "$TASK_ID" --root "$ROOT" --force

# Patch acceptance for C2 (create_task defaults to A1)
"$PY" - <<PY
import json
from pathlib import Path
p = Path("${RUN_DIR}/task.json")
t = json.loads(p.read_text(encoding="utf-8"))
t["title"] = "C2 空 query 失败返工"
t["scope"] = {
    "goal": "演示 buggy 空 query 失败 → 需修改 → fixed 再验通过",
    "in_scope": ["kit record-check/verify-gate/transition", "demo-app evidence/c2 指针"],
    "out_of_scope": ["真 merge", "OMB 真机", "改 filter 业务逻辑"],
}
t["acceptance"] = [
    {
        "id": "C2-R1-FAIL-DEMO",
        "description": "Round1 观测：buggy 空 query 应失败（演示用，非硬门）",
        "command": "bash demo-app/scripts/c2_round1_fail.sh",
        "must_run": False,
        "pass_criteria": "脚本 exit 0 且 evidence/c2/round1/report.json result=fail（观测）",
    },
    {
        "id": "C2-EMPTY-QUERY",
        "description": "fixed 空 query 安全返回 []",
        "command": "bash demo-app/scripts/c2_round2_pass.sh",
        "must_run": True,
        "pass_criteria": "exit_code==0 且 round2 report result=pass",
    },
    {
        "id": "C2-PYTEST",
        "description": "demo-app pytest（含 empty query）通过",
        "command": "cd demo-app && .venv/bin/python -m pytest -q",
        "must_run": True,
        "pass_criteria": "exit_code==0",
    },
]
p.write_text(json.dumps(t, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("patched acceptance → C2-R1-FAIL-DEMO / C2-EMPTY-QUERY / C2-PYTEST")
PY
log "patched task acceptance"

# Pointers to demo-app evidence
ln -sfn ../../../../demo-app/evidence/c2/round1 "${RUN_DIR}/artifacts/c2/round1"
ln -sfn ../../../../demo-app/evidence/c2/round2 "${RUN_DIR}/artifacts/c2/round2"
cat >"${RUN_DIR}/artifacts/c2/README.md" <<MD
# demo-c2 artifacts → demo-app/evidence/c2

- \`round1/\` → \`demo-app/evidence/c2/round1/\`（symlink）
- \`round2/\` → \`demo-app/evidence/c2/round2/\`（symlink）
MD

# ========== Round A: fail gate ==========
log ""
log "======== Round A: fail gate → 需修改 ========"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 执行中 --actor chief --note "C2 round1 start"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 待验证 --actor developer --note "submit buggy for verify"

# optional: record executed=false for must_run (still must fail gate)
kit record-check --task-id "$TASK_ID" --root "$ROOT" \
  --acceptance-id C2-EMPTY-QUERY --executed false --result fail --notes "round1 buggy"

: >"$FAIL_LOG"
kit_expect_fail verify-gate --task-id "$TASK_ID" --root "$ROOT"
kit_expect_fail transition --task-id "$TASK_ID" --root "$ROOT" --to 验证通过 --actor verifier

kit transition --task-id "$TASK_ID" --root "$ROOT" --to 需修改 --actor verifier --note "empty query gate failed"
# copy round1 pointer note into checks
cp -f "${ROOT}/demo-app/evidence/c2/round1/report.json" "${RUN_DIR}/checks/round1-report.json" 2>/dev/null || true

# ========== Round B: rework pass ==========
log ""
log "======== Round B: rework → 验证通过 ========"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 执行中 --actor developer --note "fix empty query"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 待验证 --actor developer --note "resubmit fixed"

COMMIT=c2fixed01
kit record-check --task-id "$TASK_ID" --root "$ROOT" \
  --acceptance-id C2-EMPTY-QUERY --executed true --exit-code 0 \
  --result pass --bound-commit "$COMMIT" --artifact-commit "$COMMIT" \
  --log-path "workspace/runs/demo-c2/artifacts/c2/round2/report.json" \
  --notes "round2 fixed empty-query"

kit record-check --task-id "$TASK_ID" --root "$ROOT" \
  --acceptance-id C2-PYTEST --executed true --exit-code 0 \
  --result pass --bound-commit "$COMMIT" --artifact-commit "$COMMIT" \
  --notes "pytest green incl empty-query"

kit verify-gate --task-id "$TASK_ID" --root "$ROOT"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 验证通过 --actor verifier --note "C2 hard gate pass"
kit merge-precheck --task-id "$TASK_ID" --root "$ROOT"

cp -f "${ROOT}/demo-app/evidence/c2/round2/report.json" "${RUN_DIR}/checks/round2-report.json" 2>/dev/null || true

STATUS=$("$PY" -c "import json;print(json.load(open('${RUN_DIR}/task.json'))['status'])")
log ""
log "final status=$STATUS"
log "transcript: $TRANSCRIPT"
log "fail log: $FAIL_LOG"
if [[ "$STATUS" != "验证通过" ]]; then
  log "ERROR: expected 验证通过"
  exit 1
fi
log "C2 KIT REWORK SMOKE OK"
