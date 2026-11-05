#!/usr/bin/env bash
# T2：Eng-A/B 各一条 拆解→handoff→ack→本地 commit→独立验收（OMB 标 blocked）
# 保留 t1_dual_task_smoke.sh 为旧协议烟雾；本脚本不覆盖其语义。
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "${KIT_ROOT}/.." && pwd)"
TEAM_ID=demo-t2
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
TRANSCRIPT="${LOG_DIR}/t2-handoff-smoke.log"
: >"$TRANSCRIPT"
log() { echo "$*" | tee -a "$TRANSCRIPT"; }
kit() { log "+ ${KIT[*]} $*"; "${KIT[@]}" "$@" 2>&1 | tee -a "$TRANSCRIPT"; }

json_field() {
  # usage: json_field FILE key — last JSON object line/file
  "$PY" - "$1" "$2" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
objs = []
# whole file or last {...} block
try:
    objs.append(json.loads(text))
except Exception:
    buf = []
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
        if depth:
            buf.append(ch)
        if ch == "}":
            depth -= 1
            if depth == 0 and buf:
                try:
                    objs.append(json.loads("".join(buf)))
                except Exception:
                    pass
                buf = []
if not objs:
    raise SystemExit(f"no json in {path}")
print(objs[-1][key])
PY
}

log "======== demo-t2 handoff smoke ========"
log "Asia/Shanghai start: $(date '+%Y-%m-%d %H:%M:%S %z')"

kit team-create --root "$ROOT" --team-id "$TEAM_ID" --title "T2 handoff" --force \
  --eng-stub Eng-A --eng-stub Eng-B

kit team-add-task --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-alpha \
  --title "Alpha 包" --actor Matcha --force
kit team-add-task --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-beta \
  --title "Beta 包" --actor Matcha --force

kit team-assign --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-alpha \
  --assignee Eng-A --assignee-role eng_coordinator --actor Matcha \
  --note "T2 Eng-A package"
kit team-assign --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-beta \
  --assignee Eng-B --assignee-role eng_coordinator --actor Matcha \
  --note "T2 Eng-B package" --depends-on demo-t2-alpha

ACC_A='[{"id":"A-alpha","description":"alpha ok","command":"true","must_run":true,"pass_criteria":"exit0"}]'
ACC_B='[{"id":"A-beta","description":"beta ok","command":"true","must_run":true,"pass_criteria":"exit0"}]'

kit team-eng-decompose --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-alpha \
  --actor Eng-A --goal "Alpha 包" --in-scope "alpha feature" \
  --acceptance-json "$ACC_A" --worktree "$ROOT/workspace/wt-alpha"
kit team-eng-decompose --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-beta \
  --actor Eng-B --goal "Beta 包" --in-scope "beta feature" \
  --acceptance-json "$ACC_B" --worktree "$ROOT/workspace/wt-beta"

HO_A_JSON=$(mktemp)
HO_B_JSON=$(mktemp)
"${KIT[@]}" team-handoff --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-alpha \
  --actor Eng-A --developer developer --mode local | tee -a "$TRANSCRIPT" | tee "$HO_A_JSON" >/dev/null
"${KIT[@]}" team-handoff --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-beta \
  --actor Eng-B --developer developer --mode local | tee -a "$TRANSCRIPT" | tee "$HO_B_JSON" >/dev/null
HO_A=$(json_field "$HO_A_JSON" handoff_id)
HO_B=$(json_field "$HO_B_JSON" handoff_id)
log "handoff_ids alpha=$HO_A beta=$HO_B"

kit team-ack-handoff --root "$ROOT" --team-id "$TEAM_ID" --handoff-id "$HO_A" --actor developer
kit team-ack-handoff --root "$ROOT" --team-id "$TEAM_ID" --handoff-id "$HO_B" --actor developer

kit team-omb-delegate --root "$ROOT" --team-id "$TEAM_ID" --handoff-id "$HO_A"

COMMIT_A=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
COMMIT_B=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
kit team-record-commit --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-alpha \
  --handoff-id "$HO_A" --commit "$COMMIT_A" --actor developer
kit team-record-commit --root "$ROOT" --team-id "$TEAM_ID" --task-id demo-t2-beta \
  --handoff-id "$HO_B" --commit "$COMMIT_B" --actor developer

kit transition --root "$ROOT" --task-id demo-t2-alpha --to 执行中 --actor Eng-A --note "eng track"
kit transition --root "$ROOT" --task-id demo-t2-beta --to 执行中 --actor Eng-B --note "eng track"
kit set-artifact --root "$ROOT" --task-id demo-t2-alpha --commit "$COMMIT_A" --actor developer --role developer
kit set-artifact --root "$ROOT" --task-id demo-t2-beta --commit "$COMMIT_B" --actor developer --role developer
kit transition --root "$ROOT" --task-id demo-t2-alpha --to 待验证 --actor developer --role developer
kit transition --root "$ROOT" --task-id demo-t2-beta --to 待验证 --actor developer --role developer

kit record-check --root "$ROOT" --task-id demo-t2-alpha --acceptance-id A-alpha \
  --executed true --exit-code 0 --bound-commit "$COMMIT_A" --result pass \
  --actor verifier --role verifier --log-path "$LOG_DIR/alpha.log"
kit record-check --root "$ROOT" --task-id demo-t2-beta --acceptance-id A-beta \
  --executed true --exit-code 0 --bound-commit "$COMMIT_B" --result pass \
  --actor verifier --role verifier --log-path "$LOG_DIR/beta.log"

kit team-handoff-status --root "$ROOT" --team-id "$TEAM_ID" --handoff-id "$HO_A" \
  --status done --actor verifier
kit team-handoff-status --root "$ROOT" --team-id "$TEAM_ID" --handoff-id "$HO_B" \
  --status done --actor verifier

set +e
kit set-artifact --root "$ROOT" --task-id demo-t2-alpha --commit "$COMMIT_A" \
  --actor 幕僚长 --role chief
rc=$?
set -e
if [[ $rc -eq 0 ]]; then
  log "UNEXPECTED: chief bypass succeeded"
  exit 1
fi
log "chief bypass refused (exit=$rc) OK"

"$PY" - "$RUN_DIR/team.json" \
  "${ROOT}/workspace/runs/demo-t2-alpha/task.json" \
  "${ROOT}/workspace/runs/demo-t2-beta/task.json" <<'PY'
import json, sys
team = json.load(open(sys.argv[1], encoding="utf-8"))
a = json.load(open(sys.argv[2], encoding="utf-8"))
b = json.load(open(sys.argv[3], encoding="utf-8"))
assert team["routing_policy"]["mode"] == "engineering_chain"
assert team["routing_policy"]["fast_path_enabled"] is False
assert "eng_stubs" in team["roles"]
assert team["roles"].get("eng_coordinators")
assert len(team.get("handoffs") or []) >= 2
assert a["verification"]["result"] == "pass"
assert b["verification"]["result"] == "pass"
assert a["artifact"]["commit"].startswith("aaa")
assert b["artifact"]["commit"].startswith("bbb")
omb_blocked = any(
    (h.get("omb_delegation") == "blocked")
    or ((h.get("omb_result") or {}).get("omb_delegation") == "blocked")
    for h in team["handoffs"]
)
assert omb_blocked, "expected omb_delegation=blocked on a handoff"
print("t2 assertions OK", [h["handoff_id"] for h in team["handoffs"]])
PY

log "T2 HANDOFF SMOKE OK transcript=$TRANSCRIPT"
log "Asia/Shanghai end: $(date '+%Y-%m-%d %H:%M:%S %z')"
