#!/usr/bin/env python3
"""Lite-E: static check for clean Lite import pack (no OMB GUI claimed).

Checks:
- lauren-lite.botmrr.md present with chief/developer/verifier only (no Team roles)
- instructions + SOUL stubs exist for the triangle
- team.manifest.md mentions the three roles
- optional mausteam.json parses and lists the three agents
- schema file present

Exit 0 + "LITE PACK OK" on success; non-zero with FAIL lines otherwise.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "lauren-omb-pack"
BOTMRR = PACK / "lauren-lite.botmrr.md"
MANIFEST = PACK / "team.manifest.md"
MAUSTEAM = PACK / "team.mausteam.json"
SCHEMA = ROOT / "lauren-team-kit" / "contracts" / "task-protocol.schema.json"

REQUIRED_AGENTS = ("chief", "developer", "verifier")
FORBIDDEN_IN_LITE = ("nancy", "matcha", "eng-a", "eng-b", "eng_a", "eng_b", "Nancy", "Matcha")


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"OK: {msg}")


def _extract_agent_keys(botmrr_text: str) -> list[str]:
    """Best-effort: collect `key:` under agents list without full YAML dep."""
    keys: list[str] = []
    in_agents = False
    for line in botmrr_text.splitlines():
        if re.match(r"^agents:\s*$", line):
            in_agents = True
            continue
        if in_agents:
            if re.match(r"^[a-zA-Z]", line) and not line.startswith(" "):
                # top-level key ended agents block
                break
            m = re.match(r"^\s+-\s+key:\s+(\S+)\s*$", line)
            if m:
                keys.append(m.group(1).strip())
    return keys


def main() -> int:
    errors = 0

    if not BOTMRR.is_file():
        _fail(f"missing {BOTMRR.relative_to(ROOT)}")
        return 1
    text = BOTMRR.read_text(encoding="utf-8")
    if "botmrr:" not in text or "id: lauren-lite" not in text:
        _fail("lauren-lite.botmrr.md missing botmrr header / id lauren-lite")
        errors += 1
    else:
        _ok("botmrr header id=lauren-lite")

    keys = _extract_agent_keys(text)
    if set(keys) != set(REQUIRED_AGENTS):
        _fail(f"agents keys={keys!r}, expected exactly {list(REQUIRED_AGENTS)}")
        errors += 1
    else:
        _ok(f"agents triangle: {', '.join(keys)}")

    low = text.lower()
    for bad in FORBIDDEN_IN_LITE:
        # bulletin may mention Team as out-of-scope; allow "Team" word but not agent keys as members
        pass
    # Hard: agents list must not include forbidden keys
    for k in keys:
        if k.lower().replace("_", "-") in {"nancy", "matcha", "eng-a", "eng-b"}:
            _fail(f"Lite botmrr must not include Team role agent key={k}")
            errors += 1

    for role in REQUIRED_AGENTS:
        inst = PACK / "bots" / f"{role}.instructions.md"
        soul = PACK / "bots" / role / "SOUL.md"
        if not inst.is_file():
            _fail(f"missing {inst.relative_to(ROOT)}")
            errors += 1
        else:
            _ok(f"instructions {role}")
        if not soul.is_file():
            _fail(f"missing {soul.relative_to(ROOT)}")
            errors += 1
        else:
            _ok(f"SOUL {role}")

    if not MANIFEST.is_file():
        _fail(f"missing {MANIFEST.relative_to(ROOT)}")
        errors += 1
    else:
        mtxt = MANIFEST.read_text(encoding="utf-8")
        for role in REQUIRED_AGENTS:
            if role not in mtxt:
                _fail(f"team.manifest.md missing role mention: {role}")
                errors += 1
        else:
            _ok("team.manifest.md lists triangle")

    if MAUSTEAM.is_file():
        try:
            data = json.loads(MAUSTEAM.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            _fail(f"team.mausteam.json invalid JSON: {e}")
            errors += 1
        else:
            # tolerate several shapes: agents list of dicts with key/id/name
            agents = data.get("agents") or data.get("bots") or []
            found: set[str] = set()
            if isinstance(agents, list):
                for a in agents:
                    if isinstance(a, dict):
                        k = a.get("key") or a.get("id") or a.get("role")
                        if k:
                            found.add(str(k))
                    elif isinstance(a, str):
                        found.add(a)
            missing = [r for r in REQUIRED_AGENTS if r not in found and r not in json.dumps(data)]
            # soft: if structure unknown but file mentions keys in raw text
            raw = MAUSTEAM.read_text(encoding="utf-8")
            if all(r in raw for r in REQUIRED_AGENTS):
                _ok("team.mausteam.json mentions triangle")
            else:
                _fail(f"team.mausteam.json does not clearly list {REQUIRED_AGENTS}; found={sorted(found)}")
                errors += 1
    else:
        _fail(f"missing optional-compat file {MAUSTEAM.relative_to(ROOT)}")
        errors += 1

    if not SCHEMA.is_file():
        _fail(f"missing schema {SCHEMA.relative_to(ROOT)}")
        errors += 1
    else:
        _ok("task-protocol.schema.json present")

    # Desensitization smoke: pack should not embed obvious private Mac user paths
    private_hits = re.findall(r"/Users/[^/\\s]+/(?:Desktop|Documents|Downloads)/", text)
    # allow generic mentions in comments? botmrr should be clean
    if private_hits:
        _fail(f"botmrr contains private-looking paths: {private_hits[:3]}")
        errors += 1
    else:
        _ok("botmrr no private /Users/... path literals")

    if errors:
        print(f"LITE PACK FAIL ({errors} error(s))", file=sys.stderr)
        return 1
    print("LITE PACK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
