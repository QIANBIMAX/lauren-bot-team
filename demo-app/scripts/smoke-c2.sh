#!/usr/bin/env bash
# C2 独立烟雾（不拖慢 C1 smoke.sh）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "${ROOT}/scripts/c2_rework_demo.sh"
