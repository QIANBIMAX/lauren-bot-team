#!/usr/bin/env bash
# C2 一键：round1 失败演示 → round2 修复再验
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "======== C2 Round1 (expect fail demonstrated) ========"
bash "${ROOT}/scripts/c2_round1_fail.sh"
echo
echo "======== C2 Round2 (expect pass) ========"
bash "${ROOT}/scripts/c2_round2_pass.sh"
echo
echo "======== C2 Summary ========"
echo "round1: $(python3 -c "import json;print(json.load(open('${ROOT}/evidence/c2/round1/report.json'))['result'])")"
echo "round2: $(python3 -c "import json;print(json.load(open('${ROOT}/evidence/c2/round2/report.json'))['result'])")"
echo "evidence: ${ROOT}/evidence/c2/round1/  ${ROOT}/evidence/c2/round2/"
echo "C2 REWORK DEMO OK"
