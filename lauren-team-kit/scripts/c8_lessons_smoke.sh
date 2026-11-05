#!/usr/bin/env bash
# demo-c8 Lite L5：经验候选 → 审核 → 发布 → store 可读
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TASK_ID=demo-c8
RUN_DIR="${ROOT}/workspace/runs/${TASK_ID}"
LOG_DIR="${RUN_DIR}/logs"
PY="${KIT_ROOT}/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
KIT=("$PY" -m lauren_team_kit)
mkdir -p "$LOG_DIR" "${RUN_DIR}/artifacts" "${RUN_DIR}/checks" "${KIT_ROOT}/lessons/store"
TRANSCRIPT="${LOG_DIR}/c8-lessons-smoke.log"
RULE_DRAFT="${RUN_DIR}/artifacts/demo-l5-rule-draft.md"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }

log "======== demo-c8 lessons smoke ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

kit create --title "C8 经验发布" --task-id "$TASK_ID" --root "$ROOT" --force

cat > "$RULE_DRAFT" <<'MD'
# demo-c8-guard

空 query 必须返回 []，不得抛异常。来源：demo-c8 烟雾。
MD

LESSON_ID=demo-c8-guard
kit lesson-add --task-id "$TASK_ID" --root "$ROOT" \
  --id "$LESSON_ID" \
  --summary "空 query 必须返回 []" \
  --rule-file "$RULE_DRAFT" \
  --rule-path "lauren-team-kit/rules/demo-c8-guard.md" \
  --tag smoke --actor developer \
  --applies-to filter --probe-ref demo-c8-empty-probe --probe "空 query → []"

# 未审核不得发布
set +e
kit lesson-publish --task-id "$TASK_ID" --root "$ROOT" --id "$LESSON_ID" --actor chief
rc=$?
set -e
[[ $rc -ne 0 ]] || { log "ERROR: publish before review should fail"; exit 1; }
log "(publish-before-review failed as expected)"

PROBE_JSON='{"probe_id":"demo-c8-empty-probe","passed":true,"stdout_summary":"[]","evidence":"checks/c8-empty.log","at":"2026-11-05T11:00:00+08:00"}'
kit lesson-review --task-id "$TASK_ID" --root "$ROOT" \
  --id "$LESSON_ID" --verdict approve --actor verifier --notes "有效且不误伤" \
  --probe-result-json "$PROBE_JSON"

kit lesson-publish --task-id "$TASK_ID" --root "$ROOT" --id "$LESSON_ID" --actor chief

kit lesson-show --root "$ROOT" --id "$LESSON_ID"
kit lesson-list --root "$ROOT"

log ""; log "======== Assert store + task.published ========"
"$PY" - "$RUN_DIR/task.json" "$ROOT" "$LESSON_ID" <<'PY'
import json, sys
from pathlib import Path
t = json.load(open(sys.argv[1], encoding="utf-8"))
root = Path(sys.argv[2])
lid = sys.argv[3]
pubs = (t.get("lessons") or {}).get("published") or []
assert any(p.get("id") == lid for p in pubs), pubs
store = root / "lauren-team-kit" / "lessons" / "store" / f"{lid}.json"
assert store.is_file(), store
doc = json.loads(store.read_text(encoding="utf-8"))
assert doc["id"] == lid
assert "空 query" in (doc.get("summary") or "")
assert doc.get("rule_body") or (root / doc["rule_path"]).is_file()
assert doc.get("rules_version") and doc.get("content_hash")
assert doc["rules_version"] == doc.get("version")
assert doc["rules_version"] in (root / doc["rule_path"]).read_text(encoding="utf-8")
rule = root / doc["rule_path"]
assert rule.is_file(), rule
# history has candidate/review/publish
notes = "\n".join(h.get("note","") for h in t.get("history") or [])
assert "lesson-candidate add" in notes
assert "lesson-review" in notes
assert "lesson-publish" in notes
print("c8 assertions OK; store=", store)
PY

log "C8 LESSONS SMOKE OK transcript=$TRANSCRIPT"
log "Asia/Shanghai end: $(date '+%Y-%m-%d %H:%M:%S %z')"
