"""candidates → review → publish into lessons store (+ optional rule file).

T4: scope/probe on candidates; approve requires probe evidence; rules_version
aligned across store JSON and rule file; Eng load / Developer receive receipts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lauren_team_kit.protocol import _now_iso

STORE_REL = "lauren-team-kit/lessons/store"


class LessonError(ValueError):
    """Illegal lesson candidate / publish request."""


def _lessons(task: dict[str, Any]) -> dict[str, Any]:
    raw = task.get("lessons")
    if isinstance(raw, dict):
        out = dict(raw)
    else:
        out = {}
    out.setdefault("candidates", [])
    out.setdefault("published", [])
    if not isinstance(out["candidates"], list):
        out["candidates"] = []
    if not isinstance(out["published"], list):
        out["published"] = []
    return out


def _find_candidate(
    candidates: list[Any], lesson_id: str
) -> tuple[int, dict[str, Any]]:
    for i, c in enumerate(candidates):
        if isinstance(c, dict) and c.get("id") == lesson_id:
            return i, dict(c)
    raise LessonError(f"找不到 candidate id={lesson_id!r}")


def store_dir(root: Path | str) -> Path:
    return Path(root).resolve() / "lauren-team-kit" / "lessons" / "store"


def _normalize_scope(
    scope: dict[str, Any] | str | None,
    applies_to: dict[str, Any] | str | None,
) -> dict[str, Any]:
    raw = scope if scope is not None else applies_to
    if raw is None:
        return {"task_kind": "general"}
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {"task_kind": "general"}
        return {"task_kind": s}
    if isinstance(raw, dict):
        out = dict(raw)
        if not out:
            out["task_kind"] = "general"
        return out
    raise LessonError("scope/applies_to 须为 dict 或字符串")


def _normalize_probe(
    probe: dict[str, Any] | str | None,
    probe_ref: str | None,
) -> dict[str, Any]:
    """Require a real probe description or ref (non-empty)."""
    if isinstance(probe, dict):
        ref = (
            probe.get("ref")
            or probe.get("probe_ref")
            or probe.get("id")
            or probe_ref
        )
        desc = probe.get("description") or probe.get("command") or probe.get("assert_id")
        expected = probe.get("expected")
        if not (ref or desc):
            raise LessonError("probe 须含 ref/description/command/assert_id 之一")
        out: dict[str, Any] = {}
        if ref:
            out["ref"] = str(ref).strip()
        if desc:
            out["description"] = str(desc).strip()
        if expected is not None:
            out["expected"] = expected
        for k, v in probe.items():
            if k not in out and k not in ("probe_ref", "id"):
                out[k] = v
        return out
    if probe is not None and str(probe).strip():
        out = {"ref": str(probe).strip(), "description": str(probe).strip()}
        if probe_ref and str(probe_ref).strip():
            out["ref"] = str(probe_ref).strip()
        return out
    if probe_ref is not None and str(probe_ref).strip():
        return {"ref": str(probe_ref).strip()}
    raise LessonError("probe 或 probe_ref 必填（非空字符串或含 ref/description 的 dict）")


def _normalize_approve_evidence(
    *,
    probe_result: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    src = probe_result if probe_result is not None else evidence
    if src is None:
        raise LessonError(
            "批准审核须绑定探针证据：传 probe_result 或 evidence（含 probe_id/ref、"
            "passed=True、evidence 路径或 stdout 摘要、at）"
        )
    if not isinstance(src, dict):
        raise LessonError("probe_result/evidence 须为 dict")
    probe_id = (
        src.get("probe_id")
        or src.get("probe_ref")
        or src.get("ref")
        or src.get("id")
    )
    if not probe_id or not str(probe_id).strip():
        raise LessonError("审核证据须含 probe_id / probe_ref")
    if src.get("passed") is not True:
        raise LessonError("批准审核要求 probe_result.passed=True（不得仅传 approved=True）")
    ev_path = src.get("evidence") or src.get("evidence_path")
    stdout = src.get("stdout_summary") or src.get("stdout")
    if not ev_path and not stdout:
        raise LessonError("审核证据须含 evidence 路径或 stdout/stdout_summary 摘要")
    out = {
        "probe_id": str(probe_id).strip(),
        "passed": True,
        "at": src.get("at") or _now_iso(),
    }
    if ev_path:
        out["evidence"] = str(ev_path)
    if stdout:
        out["stdout_summary"] = str(stdout)[:2000]
    for k, v in src.items():
        if k not in out and k not in ("evidence_path", "stdout", "probe_ref", "ref", "id"):
            out[k] = v
    return out


def content_hash_of(rule_body: str | None) -> str:
    raw = rule_body if rule_body is not None else ""
    return hashlib.sha256(str(raw).encode("utf-8")).hexdigest()


def make_rules_version(content_hash: str, *, major: int = 1) -> str:
    return f"{major}-{content_hash[:16]}"


def add_candidate(
    task: dict[str, Any],
    *,
    lesson_id: str,
    summary: str,
    actor: str = "developer",
    rule_body: str | None = None,
    proposed_rule_path: str | None = None,
    tags: list[str] | None = None,
    scope: dict[str, Any] | str | None = None,
    applies_to: dict[str, Any] | str | None = None,
    probe: dict[str, Any] | str | None = None,
    probe_ref: str | None = None,
) -> dict[str, Any]:
    if not lesson_id or not str(lesson_id).strip():
        raise LessonError("lesson_id 必填")
    if not summary or not str(summary).strip():
        raise LessonError("summary 必填")
    lesson_id = str(lesson_id).strip()
    probe_doc = _normalize_probe(probe, probe_ref)
    scope_doc = _normalize_scope(scope, applies_to)

    task = dict(task)
    lessons = _lessons(task)
    for c in lessons["candidates"]:
        if isinstance(c, dict) and c.get("id") == lesson_id:
            raise LessonError(f"candidate 已存在: {lesson_id}")
    for p in lessons["published"]:
        if isinstance(p, dict) and p.get("id") == lesson_id:
            raise LessonError(f"已发布，勿重复提名: {lesson_id}")

    now = _now_iso()
    cand: dict[str, Any] = {
        "id": lesson_id,
        "summary": summary.strip(),
        "status": "proposed",
        "source_task": task.get("task_id"),
        "proposed_by": actor,
        "proposed_at": now,
        "scope": scope_doc,
        "applies_to": scope_doc,
        "probe": probe_doc,
        "probe_ref": probe_doc.get("ref") or probe_doc.get("description"),
    }
    if rule_body is not None:
        cand["rule_body"] = rule_body
    if proposed_rule_path:
        cand["proposed_rule_path"] = proposed_rule_path
    else:
        cand["proposed_rule_path"] = f"lauren-team-kit/rules/{lesson_id}.md"
    if tags:
        cand["tags"] = list(tags)
    lessons["candidates"] = list(lessons["candidates"]) + [cand]
    task["lessons"] = lessons
    task["updated_at"] = now
    hist = list(task.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "from": task.get("status"),
            "to": task.get("status"),
            "note": f"lesson-candidate add id={lesson_id}",
        }
    )
    task["history"] = hist
    return task


def review_candidate(
    task: dict[str, Any],
    lesson_id: str,
    *,
    approved: bool,
    actor: str = "verifier",
    notes: str | None = None,
    probe_result: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = dict(task)
    lessons = _lessons(task)
    idx, cand = _find_candidate(list(lessons["candidates"]), lesson_id)
    if cand.get("status") == "published":
        raise LessonError(f"candidate 已发布: {lesson_id}")
    now = _now_iso()
    if approved:
        ev = _normalize_approve_evidence(probe_result=probe_result, evidence=evidence)
        cand["probe_result"] = ev
        cand["review_evidence"] = ev
    else:
        # rejected: probe evidence optional
        if probe_result is not None or evidence is not None:
            src = probe_result if probe_result is not None else evidence
            if isinstance(src, dict):
                cand["probe_result"] = dict(src)
                cand["review_evidence"] = dict(src)
    cand["status"] = "approved" if approved else "rejected"
    cand["reviewed_by"] = actor
    cand["reviewed_at"] = now
    if notes:
        cand["review_notes"] = notes
    cands = list(lessons["candidates"])
    cands[idx] = cand
    lessons["candidates"] = cands
    task["lessons"] = lessons
    task["updated_at"] = now
    hist = list(task.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "from": task.get("status"),
            "to": task.get("status"),
            "note": f"lesson-review id={lesson_id} → {cand['status']}",
        }
    )
    task["history"] = hist
    return task


def _rule_file_text(
    body: str,
    *,
    lesson_id: str,
    rules_version: str,
    content_hash: str,
) -> str:
    meta = (
        f"<!-- lauren-lesson-meta "
        f"id={lesson_id} rules_version={rules_version} content_hash={content_hash} -->\n"
    )
    text = body if body.endswith("\n") else body + "\n"
    if "lauren-lesson-meta" in text:
        return text
    return meta + text


def publish_candidate(
    task: dict[str, Any],
    lesson_id: str,
    *,
    root: Path | str,
    actor: str = "chief",
    write_rule: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Publish an approved candidate into store (+ optional rules/*.md).

    Store JSON and rule file share the same rules_version / content_hash / version.
    Returns (updated_task, published_record).
    """
    root_p = Path(root).resolve()
    task = dict(task)
    lessons = _lessons(task)
    idx, cand = _find_candidate(list(lessons["candidates"]), lesson_id)
    if cand.get("status") != "approved":
        raise LessonError(
            f"仅 approved 可发布；当前 status={cand.get('status')!r} id={lesson_id}"
        )
    if not cand.get("probe_result") and not cand.get("review_evidence"):
        raise LessonError(
            f"candidate 缺少审核探针证据，拒绝发布: {lesson_id}"
        )

    now = _now_iso()
    rule_rel = cand.get("proposed_rule_path") or f"lauren-team-kit/rules/{lesson_id}.md"
    store_rel = f"{STORE_REL}/{lesson_id}.json"
    store_path = root_p / store_rel
    store_path.parent.mkdir(parents=True, exist_ok=True)

    body = cand.get("rule_body")
    chash = content_hash_of(body if isinstance(body, str) else None)
    rules_version = cand.get("rules_version") or make_rules_version(chash)

    record: dict[str, Any] = {
        "id": lesson_id,
        "summary": cand.get("summary"),
        "source_task": cand.get("source_task") or task.get("task_id"),
        "rule_path": rule_rel,
        "store_path": store_rel,
        "published_at": now,
        "published_by": actor,
        "reviewed_by": cand.get("reviewed_by"),
        "tags": cand.get("tags") or [],
        "scope": cand.get("scope") or cand.get("applies_to"),
        "applies_to": cand.get("applies_to") or cand.get("scope"),
        "probe": cand.get("probe"),
        "probe_ref": cand.get("probe_ref"),
        "probe_result": cand.get("probe_result") or cand.get("review_evidence"),
        "rules_version": rules_version,
        "content_hash": chash,
        "version": rules_version,
    }
    store_doc = dict(record)
    if body is not None:
        store_doc["rule_body"] = body
    store_doc["candidate_snapshot"] = {
        k: cand[k]
        for k in (
            "proposed_by",
            "proposed_at",
            "review_notes",
            "status",
            "scope",
            "probe",
            "probe_ref",
        )
        if k in cand
    }
    store_path.write_text(
        json.dumps(store_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if write_rule and body:
        rule_path = root_p / rule_rel
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        rule_path.write_text(
            _rule_file_text(
                str(body),
                lesson_id=lesson_id,
                rules_version=rules_version,
                content_hash=chash,
            ),
            encoding="utf-8",
        )

    published = [
        p
        for p in lessons["published"]
        if not (isinstance(p, dict) and p.get("id") == lesson_id)
    ]
    published.append(
        {
            "id": lesson_id,
            "source_task": record["source_task"],
            "rule_path": rule_rel,
            "summary": record["summary"],
            "store_path": store_rel,
            "published_at": now,
            "rules_version": rules_version,
            "content_hash": chash,
            "version": rules_version,
            "scope": record.get("scope"),
            "probe_ref": record.get("probe_ref"),
        }
    )
    cands = list(lessons["candidates"])
    cand["status"] = "published"
    cand["published_at"] = now
    cand["rules_version"] = rules_version
    cand["content_hash"] = chash
    cand["version"] = rules_version
    cands[idx] = cand
    lessons["candidates"] = cands
    lessons["published"] = published
    task["lessons"] = lessons
    task["updated_at"] = now
    hist = list(task.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "from": task.get("status"),
            "to": task.get("status"),
            "note": f"lesson-publish id={lesson_id} store={store_rel} ver={rules_version}",
        }
    )
    task["history"] = hist
    return task, record


def list_store(root: Path | str) -> list[dict[str, Any]]:
    d = store_dir(root)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def load_from_store(root: Path | str, lesson_id: str) -> dict[str, Any]:
    p = store_dir(root) / f"{lesson_id}.json"
    if not p.is_file():
        raise LessonError(f"store 中无此经验: {lesson_id} ({p})")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LessonError(f"store 文件损坏: {p}")
    return data


def _append_receipt(host: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    host = dict(host)
    receipts = [dict(r) for r in (host.get("rule_receipts") or []) if isinstance(r, dict)]
    receipts.append(entry)
    host["rule_receipts"] = receipts
    # Mirror under lessons for task hosts
    lessons = host.get("lessons")
    if isinstance(lessons, dict):
        lessons = dict(lessons)
        lr = [dict(r) for r in (lessons.get("rule_receipts") or []) if isinstance(r, dict)]
        lr.append(dict(entry))
        lessons["rule_receipts"] = lr
        host["lessons"] = lessons
    # Optional: stamp matching handoff
    hid = entry.get("handoff_id")
    if hid and isinstance(host.get("handoffs"), list):
        handoffs = []
        for h in host["handoffs"]:
            if isinstance(h, dict) and h.get("handoff_id") == hid:
                h2 = dict(h)
                rr = [dict(r) for r in (h2.get("rule_receipts") or []) if isinstance(r, dict)]
                rr.append(dict(entry))
                h2["rule_receipts"] = rr
                handoffs.append(h2)
            else:
                handoffs.append(h)
        host["handoffs"] = handoffs
    host["updated_at"] = entry.get("at") or _now_iso()
    return host


def record_rule_load(
    host: dict[str, Any],
    *,
    eng: str,
    lesson_id: str,
    rules_version: str,
    actor: str,
) -> dict[str, Any]:
    """Eng 后续开发包记录已加载适用规则版本（挂 rule_receipts[]）。"""
    if not lesson_id or not str(lesson_id).strip():
        raise LessonError("lesson_id 必填")
    if not rules_version or not str(rules_version).strip():
        raise LessonError("rules_version 必填")
    if not eng or not str(eng).strip():
        raise LessonError("eng 必填")
    now = _now_iso()
    entry = {
        "kind": "load",
        "lesson_id": str(lesson_id).strip(),
        "rules_version": str(rules_version).strip(),
        "eng": str(eng).strip(),
        "actor": actor,
        "at": now,
    }
    host = _append_receipt(host, entry)
    hist = list(host.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "note": f"rule_load lesson={lesson_id} ver={rules_version} eng={eng}",
        }
    )
    host["history"] = hist
    return host


def record_rule_receive(
    host: dict[str, Any],
    *,
    developer: str,
    lesson_id: str,
    rules_version: str,
    actor: str,
    handoff_id: str | None = None,
) -> dict[str, Any]:
    """Developer 实际接收规则有记录（可挂 team.handoffs / task.lessons / rule_receipts）。"""
    if not lesson_id or not str(lesson_id).strip():
        raise LessonError("lesson_id 必填")
    if not rules_version or not str(rules_version).strip():
        raise LessonError("rules_version 必填")
    if not developer or not str(developer).strip():
        raise LessonError("developer 必填")
    now = _now_iso()
    entry: dict[str, Any] = {
        "kind": "receive",
        "lesson_id": str(lesson_id).strip(),
        "rules_version": str(rules_version).strip(),
        "developer": str(developer).strip(),
        "actor": actor,
        "at": now,
    }
    if handoff_id:
        entry["handoff_id"] = handoff_id
    host = _append_receipt(host, entry)
    hist = list(host.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "note": (
                f"rule_receive lesson={lesson_id} ver={rules_version} "
                f"developer={developer}"
                + (f" handoff={handoff_id}" if handoff_id else "")
            ),
        }
    )
    host["history"] = hist
    return host


def evaluate_recurrence(
    root: Path | str,
    lesson_id: str,
    *,
    probe_result: dict[str, Any],
) -> dict[str, Any]:
    """Run (or record) a probe against a published lesson for anti-recurrence.

    If probe_result.passed is False → recurrence_blocked=True (假回归被挡住).
    """
    doc = load_from_store(root, lesson_id)
    probe = doc.get("probe")
    pref = doc.get("probe_ref")
    if not probe and not pref:
        raise LessonError(f"已发布经验无探针，无法防复发: {lesson_id}")
    if not isinstance(probe_result, dict):
        raise LessonError("probe_result 须为 dict")
    passed = probe_result.get("passed") is True
    now = _now_iso()
    return {
        "lesson_id": lesson_id,
        "rules_version": doc.get("rules_version") or doc.get("version"),
        "content_hash": doc.get("content_hash"),
        "probe_ref": (
            (probe.get("ref") if isinstance(probe, dict) else None)
            or pref
            or probe_result.get("probe_id")
            or probe_result.get("probe_ref")
        ),
        "probe_passed": passed,
        "recurrence_blocked": (not passed),
        "rule_check": "hit" if not passed else "clear",
        "at": now,
        "stdout_summary": probe_result.get("stdout_summary")
        or probe_result.get("stdout"),
        "evidence": probe_result.get("evidence") or probe_result.get("evidence_path"),
    }


def record_recurrence(
    host: dict[str, Any],
    recurrence: dict[str, Any],
    *,
    actor: str = "verifier",
) -> dict[str, Any]:
    host = dict(host)
    events = [dict(e) for e in (host.get("recurrence_events") or []) if isinstance(e, dict)]
    entry = dict(recurrence)
    entry.setdefault("actor", actor)
    entry.setdefault("at", _now_iso())
    events.append(entry)
    host["recurrence_events"] = events
    host["updated_at"] = entry["at"]
    hist = list(host.get("history") or [])
    hist.append(
        {
            "at": entry["at"],
            "actor": actor,
            "note": (
                f"recurrence lesson={recurrence.get('lesson_id')} "
                f"blocked={recurrence.get('recurrence_blocked')}"
            ),
        }
    )
    host["history"] = hist
    return host
