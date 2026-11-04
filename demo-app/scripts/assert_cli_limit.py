"""CLI --limit 1 → 1 row; --limit -1 → nonzero exit."""
from __future__ import annotations

import json
import os
import subprocess
import sys

py = sys.executable
env = {**os.environ, "PYTHONPATH": "src"}
data = "fixtures/basic.json"

r1 = subprocess.run(
    [py, "-m", "demo_app", "filter", "--data", data, "--query", "发票", "--limit", "1"],
    capture_output=True,
    text=True,
    env=env,
)
if r1.returncode != 0:
    print(r1.stderr, file=sys.stderr)
    raise SystemExit(f"limit 1 failed: {r1.returncode}")
rows = json.loads(r1.stdout)
if len(rows) != 1:
    raise SystemExit(f"expected 1 row, got {len(rows)}: {rows}")

r2 = subprocess.run(
    [py, "-m", "demo_app", "filter", "--data", data, "--limit", "-1"],
    capture_output=True,
    text=True,
    env=env,
)
if r2.returncode == 0:
    raise SystemExit("expected nonzero exit for --limit -1")
print("cli limit ok")
