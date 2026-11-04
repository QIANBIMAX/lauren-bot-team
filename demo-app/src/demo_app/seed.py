"""将 fixture 复制/写出到工作数据文件。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def default_data_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "tasks.json"


def seed(fixture: Path, dest: Path | None = None) -> Path:
    dest = dest or default_data_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture, dest)
    # normalize: always write {"tasks": [...]}
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        payload = {"tasks": raw}
    elif isinstance(raw, dict) and "tasks" in raw:
        payload = raw
    else:
        raise ValueError("fixture must be list or {tasks: [...]}")
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="demo_app seed")
    p.add_argument("--fixture", required=True, help="path to fixtures/*.json")
    p.add_argument("--dest", default=None, help="output tasks.json path")
    args = p.parse_args(argv)
    out = seed(Path(args.fixture), Path(args.dest) if args.dest else None)
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
