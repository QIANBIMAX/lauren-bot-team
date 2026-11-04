#!/usr/bin/env bash
# C3 一键：注入缺陷被规则拦住 → fixed 对照通过
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "======== C3 Inject (expect blocked) ========"
bash "${ROOT}/scripts/c3_inject_blocked.sh"
echo
echo "======== C3 Clean (expect pass) ========"
bash "${ROOT}/scripts/c3_clean_pass.sh"
echo
echo "======== C3 Summary ========"
echo "blocked: $(python3 -c "import json;print(json.load(open('${ROOT}/evidence/c3/blocked/report.json'))['result'])")"
echo "clean:   $(python3 -c "import json;print(json.load(open('${ROOT}/evidence/c3/clean/report.json'))['result'])")"
echo "rule:    lauren-team-kit/rules/filter-empty-query.md"
echo "evidence: ${ROOT}/evidence/c3/blocked/  ${ROOT}/evidence/c3/clean/"
echo "C3 LESSON REUSE DEMO OK"
