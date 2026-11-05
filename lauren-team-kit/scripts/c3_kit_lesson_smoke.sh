#!/usr/bin/env bash
# =============================================================================
# 【历史样例 / HISTORICAL SAMPLE — 非正式验收】Lite-D L8
# 本脚本保留作 C3 经验复用烟雾；使用占位 commit（c3lesson01），
# 与真实 Git merge-precheck 不匹配；并依赖既有 run 目录/seed。正式验收请用 pytest：
#   lauren-team-kit/tests/test_lite_d.py（L7 回执/正反样例 + L8 真实 commit 闭环）
# 勿把本脚本 exit 0 当作「真实 commit / 真实合并」通过。
# =============================================================================
# C3 kit 经验复用烟雾：buggy 注入被规则拦→需修改；fixed 过规则→record-check→验证通过（不真 merge）
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TASK_ID=demo-c3
RUN_DIR="${ROOT}/workspace/runs/${TASK_ID}"
LOG_DIR="${RUN_DIR}/logs"
RULE="lauren-team-kit/rules/filter-empty-query.md"
PY="${KIT_ROOT}/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
KIT=("$PY" -m lauren_team_kit)
mkdir -p "$LOG_DIR" "${RUN_DIR}/artifacts/c3" "${RUN_DIR}/checks"
TRANSCRIPT="${LOG_DIR}/c3-kit-lesson-smoke.log"
FAIL_LOG="${LOG_DIR}/verify-gate-fail.log"
RULE_FAIL_LOG="${LOG_DIR}/check-rule-fail.log"
: >"$TRANSCRIPT"; : >"$FAIL_LOG"; : >"$RULE_FAIL_LOG"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }
kit_expect_fail() {
  local out="$1"; shift
  log "+ (expect fail) ${KIT[*]} $*"
  set +e; "${KIT[@]}" "$@" >"${out}.tmp" 2>&1; rc=$?; set -e
  tee -a "$TRANSCRIPT" <"${out}.tmp" >>"$out"; rm -f "${out}.tmp"
  [[ $rc -ne 0 ]] || { log "ERROR: expected non-zero"; exit 1; }
  log "(failed as expected, rc=$rc)"
}
log "======== C3 kit lesson smoke ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

# reset from seed（保留 lessons.published）
SEED="${RUN_DIR}/task.seed.json"
[[ -f "$SEED" ]] || cp "${RUN_DIR}/task.json" "$SEED"
kit create --title "C3 经验复用" --task-id $TASK_ID --root "$ROOT" --force
"$PY" - "$SEED" "${RUN_DIR}/task.json" <<'PY'
import json,sys
seed=json.load(open(sys.argv[1],encoding="utf-8")); t=json.load(open(sys.argv[2],encoding="utf-8"))
t["title"]=seed["title"]
t["scope"]={k:seed[k] for k in ("goal","in_scope","out_of_scope") if k in seed} or seed.get("scope",{})
t["merge_policy"]=seed.get("merge_policy",t.get("merge_policy"))
acc=[]
for a in seed["acceptance"]:
    a=dict(a); a.setdefault("pass_criteria","exit_code==0"); acc.append(a)
t["acceptance"]=acc
t["lessons"]=seed["lessons"]
assert t["lessons"]["published"], "lessons.published missing"
open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(t,ensure_ascii=False,indent=2)+"\n")
print("demo-c3 from seed; lessons.published =",[l["id"] for l in t["lessons"]["published"]])
PY
ln -sfn ../../../../demo-app/evidence/c3/blocked "${RUN_DIR}/artifacts/c3/blocked"
ln -sfn ../../../../demo-app/evidence/c3/clean "${RUN_DIR}/artifacts/c3/clean"

log ""; log "======== Round blocked: buggy 注入 → 需修改 ========"
kit transition --task-id $TASK_ID --root "$ROOT" --to 执行中 --actor chief --note "C3 inject buggy"
kit transition --task-id $TASK_ID --root "$ROOT" --to 待验证 --actor developer --note "submit (buggy injected)"
kit_expect_fail "$RULE_FAIL_LOG" check-rule --root "$ROOT" --rule "$RULE" --against demo-app --impl buggy
kit_expect_fail "$RULE_FAIL_LOG" preflight --task-id $TASK_ID --root "$ROOT" --rules "$RULE" --against demo-app --impl buggy
# 不 record-check pass
kit_expect_fail "$FAIL_LOG" verify-gate --task-id $TASK_ID --root "$ROOT"
kit_expect_fail "$FAIL_LOG" transition --task-id $TASK_ID --root "$ROOT" --to 验证通过 --actor verifier
kit transition --task-id $TASK_ID --root "$ROOT" --to 需修改 --actor verifier --note "filter-empty-query rule blocked buggy"
cp -f "${ROOT}/demo-app/evidence/c3/blocked/report.json" "${RUN_DIR}/checks/blocked-report.json" 2>/dev/null || true

log ""; log "======== Round clean: fixed → 验证通过 ========"
kit transition --task-id $TASK_ID --root "$ROOT" --to 执行中 --actor developer --note "revert to fixed"
kit transition --task-id $TASK_ID --root "$ROOT" --to 待验证 --actor developer --note "resubmit fixed"
kit check-rule --root "$ROOT" --rule "$RULE" --against demo-app --impl fixed
kit preflight --task-id $TASK_ID --root "$ROOT" --rules "$RULE" --against demo-app --impl fixed
COMMIT=c3lesson01
for AID in C3-RULE-FILE C3-BLOCK-BUGGY C3-CLEAN-FIXED; do
  kit record-check --task-id $TASK_ID --root "$ROOT" --acceptance-id $AID --executed true --exit-code 0 \
    --result pass --bound-commit $COMMIT --artifact-commit $COMMIT --notes "C3 probes ok"
done
kit verify-gate --task-id $TASK_ID --root "$ROOT"
kit transition --task-id $TASK_ID --root "$ROOT" --to 验证通过 --actor verifier --note "C3 lesson reuse pass"
kit merge-precheck --task-id $TASK_ID --root "$ROOT"
cp -f "${ROOT}/demo-app/evidence/c3/clean/report.json" "${RUN_DIR}/checks/clean-report.json" 2>/dev/null || true

STATUS=$("$PY" -c "import json;t=json.load(open('${RUN_DIR}/task.json'));assert t['lessons']['published'];print(t['status'])")
log "final status=$STATUS"; log "transcript: $TRANSCRIPT"; log "fail logs: $FAIL_LOG $RULE_FAIL_LOG"
[[ "$STATUS" == "验证通过" ]] || { log "ERROR"; exit 1; }
log "C3 KIT LESSON SMOKE OK"
