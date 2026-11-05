#!/usr/bin/env bash
# T3：Nancy 持久待办 / 阶段拆分 / 阻塞去重解除 / 客观备注
# 不覆盖 t1/t2 烟雾语义。
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TEAM_ID=demo-t3
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
mkdir -p "$LOG_DIR"
TRANSCRIPT="${LOG_DIR}/t3-nancy-smoke.log"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }

log "======== demo-t3 nancy smoke ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

kit team-create --root "$ROOT" --team-id "$TEAM_ID" --title "T3 nancy" --force \
  --eng-stub Eng-A --eng-stub Eng-B

kit team-add-task --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t3-a \
  --title "Alpha" --actor Matcha --force
kit team-assign --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t3-a \
  --assignee Eng-A --actor Matcha --note "T3 package"

kit team-todo-add --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --text "跟进 demo-t3-a 待合并情况" --source user

kit transition --task-id demo-t3-a --root "$ROOT" --to 执行中 --actor Eng-A --note "start"
kit block --task-id demo-t3-a --root "$ROOT" \
  --code WAITING_DEV --message "等 developer" \
  --recovery-hint "handoff 后解除" --resume-point 执行中 --actor Matcha

kit team-summarize --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --note "任务待合并，尚未完成"
kit team-summarize --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --note "再次汇总；同一阻塞不应重复升级"

kit team-blocker-resolve --root "$ROOT" --team-id "$TEAM_ID" \
  --task-id demo-t3-a --reason-code WAITING_DEV --actor Nancy --note "已安排"

kit resume --task-id demo-t3-a --root "$ROOT" --actor Matcha \
  --to 执行中 --clear-blocker-code WAITING_DEV

kit team-summarize --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --note "阻塞已解除，不应再报警"

# Force pending_merge status for count split check (authoritative task write in smoke only)
"$PY" - "$ROOT/workspace/runs/demo-t3-a/task.json" <<'PY'
import json, sys
p = sys.argv[1]
t = json.load(open(p, encoding="utf-8"))
t["status"] = "待合并"
json.dump(t, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("forced status=待合并")
PY

kit team-summarize --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --note "待合并分列核对"

kit team-todo-list --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy >"${LOG_DIR}/todos.json"

"$PY" - "$RUN_DIR/team.json" <<'PY'
import json, sys
team = json.load(open(sys.argv[1], encoding="utf-8"))
todos = team.get("todos") or []
assert any(t.get("todo_id") == "todo-001" for t in todos), todos
open_esc = [
    e for e in (team.get("blockers_escalated") or [])
    if (e.get("status") or e.get("lifecycle") or "open") == "open"
]
assert open_esc == [], open_esc
# last summary counts
s = (team.get("summaries") or [])[-1]
assert s["counts"]["pending_merge"] == 1, s["counts"]
assert s["counts"]["completed"] == 0, s["counts"]
assert "doneish" not in s["counts"]
assert "尚未完成" in s["text"]
assert "任务待合并，尚未完成" in (team.get("summaries") or [])[0]["text"]
# reload persistence
team2 = json.load(open(sys.argv[1], encoding="utf-8"))
assert team2["todos"][0]["text"]
view = team2.get("execution_view") or []
assert view and view[0].get("responsible") == "Eng-A"
print("t3 assertions OK", s["counts"])
PY

log "T3 NANCY SMOKE OK transcript=$TRANSCRIPT"
log "Asia/Shanghai end: $(date '+%Y-%m-%d %H:%M:%S %z')"
