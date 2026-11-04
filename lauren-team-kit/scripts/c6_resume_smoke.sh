#!/usr/bin/env bash
# demo-c6 Lite L3：中断/受阻 → resume，不重复提交 artifact
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TASK_ID=demo-c6
RUN_DIR="${ROOT}/workspace/runs/${TASK_ID}"
LOG_DIR="${RUN_DIR}/logs"
PY="${KIT_ROOT}/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
KIT=("$PY" -m lauren_team_kit)
mkdir -p "$LOG_DIR" "${RUN_DIR}/artifacts" "${RUN_DIR}/checks"
TRANSCRIPT="${LOG_DIR}/c6-resume-smoke.log"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }

log "======== demo-c6 resume smoke ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

kit create --title "C6 中断恢复" --task-id "$TASK_ID" --root "$ROOT" --force

FAKE_SHA="c6resume01deadbeef"

log ""; log "======== Scene A: 执行中 → block(kill) → resume → 执行中 ========"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 执行中 --actor chief --note "start work"
# 模拟已有提交，中断后不应要求重提
kit record-check --task-id "$TASK_ID" --root "$ROOT" \
  --acceptance-id A1 --executed false --notes "not run yet" \
  --artifact-commit "$FAKE_SHA"
OUT_A=$(kit block --task-id "$TASK_ID" --root "$ROOT" \
  --code KILL --message "模拟进程被杀" \
  --recovery-hint "重新拉起后 resume，勿重复 commit" \
  --resume-point 执行中 --actor chief)
echo "$OUT_A" | grep -q '"status": "受阻"' || { log "ERROR: expected 受阻"; exit 1; }
OUT_AR=$(kit resume --task-id "$TASK_ID" --root "$ROOT" --actor chief)
echo "$OUT_AR" | grep -q 'already_have_artifact=true' || { log "ERROR: expected already_have_artifact"; exit 1; }
echo "$OUT_AR" | grep -q '"status": "执行中"' || { log "ERROR: expected 执行中 after resume"; exit 1; }

log ""; log "======== Scene B: 待验证 → block(env) → resume → 待验证 ========"
kit transition --task-id "$TASK_ID" --root "$ROOT" --to 待验证 --actor developer --note "submit for verify"
OUT_B=$(kit block --task-id "$TASK_ID" --root "$ROOT" \
  --code MISSING_DEP --message "缺 pytest" \
  --recovery-hint "安装 pytest 后 resume 到待验证，勿把未跑检查标 pass" \
  --resume-point 待验证 --actor verifier)
echo "$OUT_B" | grep -q '"status": "受阻"' || { log "ERROR: expected 受阻 (B)"; exit 1; }
OUT_BR=$(kit resume --task-id "$TASK_ID" --root "$ROOT" --actor chief)
echo "$OUT_BR" | grep -q '"status": "待验证"' || { log "ERROR: expected 待验证 after resume"; exit 1; }
echo "$OUT_BR" | grep -q 'already_have_artifact=true' || { log "ERROR: expected already_have_artifact (B)"; exit 1; }

log ""; log "======== Assert history + artifact intact ========"
"$PY" - "$RUN_DIR/task.json" "$FAKE_SHA" <<'PY'
import json, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
sha = sys.argv[2]
notes = [h.get("note", "") for h in t.get("history") or []]
joined = "\n".join(notes)
assert "block code=KILL" in joined, notes
assert "block code=MISSING_DEP" in joined, notes
assert any("resume → 执行中" in n for n in notes), notes
assert any("resume → 待验证" in n for n in notes), notes
art = (t.get("artifact") or {}).get("commit")
assert art == sha, f"artifact cleared or duplicated unexpectedly: {art!r}"
# 未跑检查不得标 pass
ver = t.get("verification") or {}
assert ver.get("result") != "pass", ver
checks = ver.get("checks") or []
for c in checks:
    if c.get("acceptance_id") == "A1":
        assert c.get("executed") is False
        assert c.get("result") != "pass"
assert t["status"] == "待验证"
print("history+artifact assertions OK; status=", t["status"])
PY

log "final OK transcript=$TRANSCRIPT"
log "Asia/Shanghai end: $(date '+%Y-%m-%d %H:%M:%S %z')"
