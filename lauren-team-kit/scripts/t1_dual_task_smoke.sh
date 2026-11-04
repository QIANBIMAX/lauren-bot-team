#!/usr/bin/env bash
# demo-t1 Team v0.2：双任务 + Nancy 汇总 + Matcha 指派（Eng stub）
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TEAM_ID=demo-t1
RUN_DIR="${ROOT}/workspace/runs/${TEAM_ID}"
LOG_DIR="${RUN_DIR}/logs"
PY="${KIT_ROOT}/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
KIT=("$PY" -m lauren_team_kit)
mkdir -p "$LOG_DIR"
TRANSCRIPT="${LOG_DIR}/t1-dual-task-smoke.log"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }

log "======== demo-t1 Team dual-task smoke ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

kit team-create --root "$ROOT" --team-id "$TEAM_ID" --title "T1 双任务演示" --force \
  --eng-stub Eng-A --eng-stub Eng-B

kit team-add-task --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t1-alpha \
  --title "Alpha：协议文档校对" --actor Matcha --force
kit team-add-task --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t1-beta \
  --title "Beta：烟雾脚本接线" --actor Matcha --force

kit team-assign --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t1-alpha \
  --assignee Eng-A --actor Matcha --note "stub track only"
kit team-assign --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t1-beta \
  --assignee Eng-B --actor Matcha --note "stub track only"

# Advance children into 执行中 without fake verify
kit transition --task-id demo-t1-alpha --root "$ROOT" --to 执行中 --actor Eng-A --note "stub start"
kit transition --task-id demo-t1-beta --root "$ROOT" --to 执行中 --actor Eng-B --note "stub start"
# Simulate one blocker on beta → escalate via Nancy summarize
kit block --task-id demo-t1-beta --root "$ROOT" \
  --code WAITING_ENG --message "Eng stub 等待真实实现" \
  --recovery-hint "Full Eng 不在本切片；保持 stub" \
  --resume-point 执行中 --actor Matcha

kit team-summarize --root "$ROOT" --team-id "$TEAM_ID" --actor Nancy \
  --note "双任务进行中；beta 受阻已升级"
kit team-status --root "$ROOT" --team-id "$TEAM_ID" >"${LOG_DIR}/team-status.json"

"$PY" - "$RUN_DIR/team.json" "${ROOT}/workspace/runs/demo-t1-alpha/task.json" "${ROOT}/workspace/runs/demo-t1-beta/task.json" <<'PY'
import json, sys
team = json.load(open(sys.argv[1], encoding="utf-8"))
a = json.load(open(sys.argv[2], encoding="utf-8"))
b = json.load(open(sys.argv[3], encoding="utf-8"))
assert team["schema_version"] == "lauren-team-run/0.2"
assert team["child_task_ids"] == ["demo-t1-alpha", "demo-t1-beta"]
assert len(team["assignments"]) == 2
assert len(team["summaries"]) >= 1
assert team["summaries"][-1]["by"] == "Nancy"
assert a["status"] == "执行中"
assert a["team"]["assignee"] == "Eng-A"
assert b["status"] == "受阻"
assert b["team"]["assignee"] == "Eng-B"
# no fake verify pass
assert (a.get("verification") or {}).get("result") != "pass"
assert (b.get("verification") or {}).get("result") != "pass"
assert team.get("blockers_escalated"), "expected Nancy escalate"
print("t1 assertions OK", team["child_task_ids"], b["status"])
PY

log "T1 DUAL-TASK SMOKE OK transcript=$TRANSCRIPT"
log "Asia/Shanghai end: $(date '+%Y-%m-%d %H:%M:%S %z')"
