#!/usr/bin/env bash
# demo-c8 Lite L5：add → review → publish → store + rules
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TASK_ID=demo-c8
RUN_DIR="${ROOT}/workspace/runs/${TASK_ID}"
LOG_DIR="${RUN_DIR}/logs"
PY="${KIT_ROOT}/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
KIT=("$PY" -m lauren_team_kit)
mkdir -p "$LOG_DIR"
TRANSCRIPT="${LOG_DIR}/c8-lesson-publish-smoke.log"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }

RULE_FILE="${LOG_DIR}/draft-rule.md"
cat > "$RULE_FILE" <<'MD'
# 规则：c8-empty-safe（L5 发布演示）

来源：demo-c8 经验发布烟雾。

## 硬约束

- 空 query 必须安全（演示用占位）。

## 验收探针

```bash
true
```
MD

log "======== demo-c8 lesson publish smoke ========"
kit create --title "C8 经验发布" --task-id "$TASK_ID" --root "$ROOT" --force
kit lesson-add --task-id "$TASK_ID" --root "$ROOT" \
  --id c8-empty-safe --summary "C8 发布演示规则" --rule-file "$RULE_FILE" --actor developer \
  --probe-ref c8-empty-probe --probe "empty safe"
# 未批准不得发布
if "${KIT[@]}" lesson-publish --task-id "$TASK_ID" --root "$ROOT" --id c8-empty-safe --actor chief >>"$TRANSCRIPT" 2>&1; then
  log "ERROR: publish should fail before approve"; exit 1
fi
log "(publish blocked before approve — ok)"
PROBE_JSON='{"probe_id":"c8-empty-probe","passed":true,"stdout_summary":"ok","evidence":"checks/c8.log","at":"2026-11-05T11:00:00+08:00"}'
kit lesson-review --task-id "$TASK_ID" --root "$ROOT" --id c8-empty-safe --verdict approve --actor verifier --notes "smoke ok" \
  --probe-result-json "$PROBE_JSON"
kit lesson-publish --task-id "$TASK_ID" --root "$ROOT" --id c8-empty-safe --actor chief
test -f "${ROOT}/lauren-team-kit/lessons/store/c8-empty-safe.json"
test -f "${ROOT}/lauren-team-kit/rules/c8-empty-safe.md"
kit lesson-show --root "$ROOT" --id c8-empty-safe >/dev/null

"$PY" - "$RUN_DIR/task.json" <<'PY'
import json,sys
t=json.load(open(sys.argv[1],encoding="utf-8"))
pub=t["lessons"]["published"]
assert any(p.get("id")=="c8-empty-safe" for p in pub), pub
cands=t["lessons"]["candidates"]
assert any(c.get("id")=="c8-empty-safe" and c.get("status")=="published" for c in cands), cands
print("c8 assertions OK", pub[-1])
PY
log "C8 LESSON PUBLISH SMOKE OK transcript=$TRANSCRIPT"
