#!/usr/bin/env bash
# T4：失败经验反馈 + E2E 烟雾（kit 本地 / mode=simulated；OMB 多助手标 blocked）
# 不覆盖 t1_dual_task_smoke.sh（旧协议/状态）。完整场景见 tests/test_t4_e2e.py。
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TEAM_ID=demo-t4
RUN_DIR="${ROOT}/workspace/runs/${TEAM_ID}"
LOG_DIR="${RUN_DIR}/logs"
# Python 探测：$LAUREN_KIT_PYTHON → /workspace/.t{4,3,2,1}-venv → KIT .venv（须能 import lauren_team_kit）→ python3
resolve_kit_py() {
  local c
  if [[ -n "${LAUREN_KIT_PYTHON:-}" && -x "${LAUREN_KIT_PYTHON}" ]]; then
    echo "$LAUREN_KIT_PYTHON"; return
  fi
  for c in /workspace/.t4-venv/bin/python /workspace/.t3-venv/bin/python \
           /workspace/.t2-venv/bin/python /workspace/.t1-venv/bin/python \
           "${KIT_ROOT}/.venv/bin/python"; do
    if [[ -x "$c" ]] && "$c" -c "import lauren_team_kit" 2>/dev/null; then
      echo "$c"; return
    fi
  done
  command -v python3
}
PY="$(resolve_kit_py)"
KIT=("$PY" -m lauren_team_kit)
mkdir -p "$LOG_DIR" "${ROOT}/lauren-team-kit/lessons/store" "${ROOT}/lauren-team-kit/rules"
TRANSCRIPT="${LOG_DIR}/t4-e2e-smoke.log"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }

log "======== demo-t4 e2e smoke (simulated) ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"
log "PY=$PY"

# Prefer pytest for full matrix; this smoke covers lesson probe path + Nancy todo
kit team-create --root "$ROOT" --team-id "$TEAM_ID" --title "T4 e2e" --force \
  --eng-stub Eng-A --eng-stub Eng-B

kit team-todo-add --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --text "T4 烟雾待办：跟进规则发布" --source user

TASK_ID=demo-t4-lesson
kit create --title "T4 lesson host" --task-id "$TASK_ID" --root "$ROOT" --force
RULE_FILE="${LOG_DIR}/t4-rule.md"
cat > "$RULE_FILE" <<'MD'
# t4-smoke-guard
空输入必须返回 []。
MD
LESSON_ID=t4-smoke-guard
kit lesson-add --task-id "$TASK_ID" --root "$ROOT" \
  --id "$LESSON_ID" --summary "空输入必须 []" \
  --rule-file "$RULE_FILE" --actor developer \
  --applies-to filter --probe-ref t4-smoke-probe --probe "empty→[]"

# approve without probe must fail
set +e
kit lesson-review --task-id "$TASK_ID" --root "$ROOT" \
  --id "$LESSON_ID" --verdict approve --actor verifier --notes "bare"
rc=$?
set -e
[[ $rc -ne 0 ]] || { log "ERROR: approve without probe should fail"; exit 1; }
log "(approve-without-probe failed as expected)"

PROBE_JSON='{"probe_id":"t4-smoke-probe","passed":true,"stdout_summary":"[]","evidence":"checks/t4.log","at":"2026-11-05T11:00:00+08:00"}'
kit lesson-review --task-id "$TASK_ID" --root "$ROOT" \
  --id "$LESSON_ID" --verdict approve --actor verifier --notes "probe ok" \
  --probe-result-json "$PROBE_JSON"
kit lesson-publish --task-id "$TASK_ID" --root "$ROOT" --id "$LESSON_ID" --actor chief

VER="$("$PY" - <<PY
import json
from pathlib import Path
p=Path("$ROOT")/"lauren-team-kit/lessons/store/${LESSON_ID}.json"
d=json.loads(p.read_text(encoding="utf-8"))
print(d["rules_version"])
PY
)"
kit lesson-rule-load --root "$ROOT" --team-id "$TEAM_ID" \
  --id "$LESSON_ID" --eng Eng-A --rules-version "$VER" --actor Eng-A
kit lesson-rule-receive --root "$ROOT" --team-id "$TEAM_ID" \
  --id "$LESSON_ID" --developer developer --rules-version "$VER" --actor developer

REC_JSON='{"probe_id":"t4-smoke-probe","passed":false,"stdout_summary":"TypeError"}'
kit lesson-recurrence --root "$ROOT" --team-id "$TEAM_ID" \
  --id "$LESSON_ID" --probe-result-json "$REC_JSON" --actor verifier

kit team-summarize --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --note "T4 烟雾汇总"

"$PY" - "$ROOT/workspace/runs/${TEAM_ID}/team.json" "$ROOT" "$LESSON_ID" <<'PY'
import json, sys
from pathlib import Path
team = json.load(open(sys.argv[1], encoding="utf-8"))
root = Path(sys.argv[2])
lid = sys.argv[3]
assert any(t.get("text", "").startswith("T4") for t in (team.get("todos") or []))
receipts = team.get("rule_receipts") or []
assert any(r.get("kind") == "load" for r in receipts), receipts
assert any(r.get("kind") == "receive" for r in receipts), receipts
store = json.loads((root / "lauren-team-kit/lessons/store" / f"{lid}.json").read_text(encoding="utf-8"))
assert store.get("rules_version") and store.get("content_hash")
rule = (root / store["rule_path"]).read_text(encoding="utf-8")
assert store["rules_version"] in rule
events = team.get("recurrence_events") or []
assert any(e.get("recurrence_blocked") for e in events), events
print("t4 smoke assertions OK")
PY

# Full matrix via pytest if available
if "$PY" -c "import pytest" 2>/dev/null; then
  log "+ pytest tests/test_t4_e2e.py -q"
  (cd "$KIT_ROOT" && "$PY" -m pytest -q tests/test_t4_e2e.py) | tee -a "$TRANSCRIPT"
fi

log "T4 E2E SMOKE OK transcript=$TRANSCRIPT"
log "Asia/Shanghai end: $(date '+%Y-%m-%d %H:%M:%S %z')"
