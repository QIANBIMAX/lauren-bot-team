"""candidates → review → publish into lessons store (+ optional rule file)."""

from __future__ import annotations

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


def add_candidate(
    task: dict[str, Any],
    *,
    lesson_id: str,
    summary: str,
    actor: str = "developer",
    rule_body: str | None = None,
    proposed_rule_path: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    if not lesson_id or not str(lesson_id).strip():
        raise LessonError("lesson_id 必填")
    if not summary or not str(summary).strip():
        raise LessonError("summary 必填")
    lesson_id = str(lesson_id).strip()
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
) -> dict[str, Any]:
    task = dict(task)
    lessons = _lessons(task)
    idx, cand = _find_candidate(list(lessons["candidates"]), lesson_id)
    if cand.get("status") == "published":
        raise LessonError(f"candidate 已发布: {lesson_id}")
    now = _now_iso()
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


def publish_candidate(
    task: dict[str, Any],
    lesson_id: str,
    *,
    root: Path | str,
    actor: str = "chief",
    write_rule: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Publish an approved candidate into store (+ optional rules/*.md).

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

    now = _now_iso()
    rule_rel = cand.get("proposed_rule_path") or f"lauren-team-kit/rules/{lesson_id}.md"
    store_rel = f"{STORE_REL}/{lesson_id}.json"
    store_path = root_p / store_rel
    store_path.parent.mkdir(parents=True, exist_ok=True)

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
    }
    # Persist full payload in store (including rule_body for regression demos)
    store_doc = dict(record)
    if cand.get("rule_body") is not None:
        store_doc["rule_body"] = cand["rule_body"]
    store_doc["candidate_snapshot"] = {
        k: cand[k]
        for k in ("proposed_by", "proposed_at", "review_notes", "status")
        if k in cand
    }
    store_path.write_text(
        json.dumps(store_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if write_rule and cand.get("rule_body"):
        rule_path = root_p / rule_rel
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        if not rule_path.is_file():
            rule_path.write_text(str(cand["rule_body"]), encoding="utf-8")

    # Update task lessons
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
        }
    )
    cands = list(lessons["candidates"])
    cand["status"] = "published"
    cand["published_at"] = now
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
            "note": f"lesson-publish id={lesson_id} store={store_rel}",
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
