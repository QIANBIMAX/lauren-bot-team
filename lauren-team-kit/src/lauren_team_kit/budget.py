"""Lite L4: budget / timeout / retry hard gates — exceed → 受阻 with BUDGET_*."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lauren_team_kit.protocol import _now_iso, transition_task
from lauren_team_kit.resume import block_task

BUDGET_ATTEMPTS = "BUDGET_ATTEMPTS"
BUDGET_DURATION = "BUDGET_DURATION"
BUDGET_TOKENS = "BUDGET_TOKENS"

_HINTS = {
    BUDGET_ATTEMPTS: "抬高 max_attempts（set-budget）或结束任务；勿盲目重试",
    BUDGET_DURATION: "抬高 max_duration_sec 或拆分子任务后 resume",
    BUDGET_TOKENS: "抬高 max_tokens 或停止高消耗调用后 resume",
}


class BudgetError(ValueError):
    """Raised when a budget gate trips and auto_block is False."""


def _parse_iso(s: str) -> datetime:
    raw = str(s).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def set_budget(
    task: dict[str, Any],
    *,
    max_attempts: int | None = None,
    max_duration_sec: int | None = None,
    max_tokens: int | None = None,
    actor: str = "chief",
    allow_raise: bool = False,
) -> dict[str, Any]:
    """Attach / update hard budget limits on a task.

    Raising an existing max_* requires allow_raise=True (CLI: --allow-raise).
    First-time set / lower / same value does not.
    """
    if max_attempts is None and max_duration_sec is None and max_tokens is None:
        raise BudgetError("set-budget 至少指定 max_attempts / max_duration_sec / max_tokens 之一")
    task = dict(task)
    b: dict[str, Any] = (
        dict(task["budget"]) if isinstance(task.get("budget"), dict) else {}
    )

    def _would_raise(key: str, new_val: int) -> bool:
        if key not in b:
            return False
        try:
            return int(new_val) > int(b[key])
        except (TypeError, ValueError):
            return False

    raising_keys: list[str] = []
    if max_attempts is not None and _would_raise("max_attempts", int(max_attempts)):
        raising_keys.append("max_attempts")
    if max_duration_sec is not None and _would_raise(
        "max_duration_sec", int(max_duration_sec)
    ):
        raising_keys.append("max_duration_sec")
    if max_tokens is not None and _would_raise("max_tokens", int(max_tokens)):
        raising_keys.append("max_tokens")
    if raising_keys and not allow_raise:
        raise BudgetError(
            "抬高预算须显式 --allow-raise（幕僚长确认）; "
            f"拟抬高: {', '.join(raising_keys)}"
        )

    if max_attempts is not None:
        if int(max_attempts) < 1:
            raise BudgetError("max_attempts 须 ≥ 1")
        b["max_attempts"] = int(max_attempts)
    if max_duration_sec is not None:
        if int(max_duration_sec) < 1:
            raise BudgetError("max_duration_sec 须 ≥ 1")
        b["max_duration_sec"] = int(max_duration_sec)
    if max_tokens is not None:
        if int(max_tokens) < 1:
            raise BudgetError("max_tokens 须 ≥ 1")
        b["max_tokens"] = int(max_tokens)
    b.setdefault("attempts_used", 0)
    b.setdefault("tokens_used", 0)
    task["budget"] = b
    now = _now_iso()
    task["updated_at"] = now
    hist = list(task.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "from": task.get("status"),
            "to": task.get("status"),
            "note": f"set-budget { {k: b[k] for k in ('max_attempts','max_duration_sec','max_tokens') if k in b} }",
        }
    )
    task["history"] = hist
    return task


def evaluate_budget(
    task: dict[str, Any], *, pending_attempt: bool = False
) -> dict[str, Any]:
    """Check caps without mutating. pending_attempt=True simulates entering 执行中."""
    raw = task.get("budget")
    if not isinstance(raw, dict):
        return {"ok": True, "violations": [], "budget": None}
    has_limit = any(k in raw for k in ("max_attempts", "max_duration_sec", "max_tokens"))
    if not has_limit:
        return {"ok": True, "violations": [], "budget": dict(raw)}

    violations: list[dict[str, Any]] = []
    attempts_used = int(raw.get("attempts_used") or 0)
    tokens_used = int(raw.get("tokens_used") or 0)

    if "max_attempts" in raw:
        max_a = int(raw["max_attempts"])
        projected = attempts_used + (1 if pending_attempt else 0)
        if projected > max_a:
            violations.append(
                {
                    "code": BUDGET_ATTEMPTS,
                    "message": (
                        f"执行轮次超限: attempts_used={attempts_used}"
                        f"{'+1' if pending_attempt else ''} > max_attempts={max_a}"
                    ),
                    "recovery_hint": _HINTS[BUDGET_ATTEMPTS],
                }
            )

    if "max_duration_sec" in raw and raw.get("started_at"):
        max_d = int(raw["max_duration_sec"])
        try:
            started = _parse_iso(str(raw["started_at"]))
            elapsed = (datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()
            if elapsed > max_d:
                violations.append(
                    {
                        "code": BUDGET_DURATION,
                        "message": (
                            f"墙钟超时: elapsed≈{int(elapsed)}s > "
                            f"max_duration_sec={max_d}"
                        ),
                        "recovery_hint": _HINTS[BUDGET_DURATION],
                    }
                )
        except (TypeError, ValueError):
            pass

    if "max_tokens" in raw:
        max_t = int(raw["max_tokens"])
        if tokens_used > max_t:
            violations.append(
                {
                    "code": BUDGET_TOKENS,
                    "message": f"token 超限: tokens_used={tokens_used} > max_tokens={max_t}",
                    "recovery_hint": _HINTS[BUDGET_TOKENS],
                }
            )

    return {
        "ok": not violations,
        "violations": violations,
        "budget": {
            "max_attempts": raw.get("max_attempts"),
            "max_duration_sec": raw.get("max_duration_sec"),
            "max_tokens": raw.get("max_tokens"),
            "attempts_used": attempts_used,
            "tokens_used": tokens_used,
            "started_at": raw.get("started_at"),
        },
    }


def record_tokens(
    task: dict[str, Any], *, tokens: int, actor: str = "developer"
) -> dict[str, Any]:
    if int(tokens) < 0:
        raise BudgetError("tokens 不可为负")
    task = dict(task)
    b: dict[str, Any] = (
        dict(task["budget"]) if isinstance(task.get("budget"), dict) else {}
    )
    b["tokens_used"] = int(b.get("tokens_used") or 0) + int(tokens)
    task["budget"] = b
    now = _now_iso()
    task["updated_at"] = now
    hist = list(task.get("history") or [])
    hist.append(
        {
            "at": now,
            "actor": actor,
            "from": task.get("status"),
            "to": task.get("status"),
            "note": f"record-tokens +{int(tokens)} → tokens_used={b['tokens_used']}",
        }
    )
    task["history"] = hist
    return task


def transition_with_budget(
    task: dict[str, Any],
    *,
    to_status: str,
    actor: str,
    note: str | None = None,
    auto_block: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """transition_task with L4 gates on entry to 执行中.

    On violate + auto_block: move to 受阻 (resume_point=待执行), return report action=blocked.
    On violate + not auto_block: raise BudgetError.
    """
    entering_exec = to_status == "执行中"
    if entering_exec:
        report = evaluate_budget(task, pending_attempt=True)
        if not report["ok"]:
            if not auto_block:
                codes = ",".join(v["code"] for v in report["violations"])
                raise BudgetError(
                    f"预算硬门拒绝进入执行中: {codes}; "
                    + "; ".join(v["message"] for v in report["violations"])
                )
            primary = report["violations"][0]
            blocked = block_task(
                task,
                code=primary["code"],
                message=primary["message"],
                recovery_hint=primary.get("recovery_hint") or _HINTS.get(primary["code"], "调整预算后 resume"),
                resume_point="待执行",
                actor=actor,
                reason=primary["message"],
            )
            return blocked, {
                "ok": False,
                "action": "blocked",
                "violations": report["violations"],
                "budget": report.get("budget"),
            }

        updated = transition_task(task, to_status=to_status, actor=actor, note=note)
        raw = updated.get("budget")
        if isinstance(raw, dict) and any(
            k in raw for k in ("max_attempts", "max_duration_sec", "max_tokens")
        ):
            b = dict(raw)
            b["attempts_used"] = int(b.get("attempts_used") or 0) + 1
            if not b.get("started_at"):
                b["started_at"] = _now_iso()
            updated = dict(updated)
            updated["budget"] = b
        ok_rep = evaluate_budget(updated, pending_attempt=False)
        ok_rep["action"] = "ok"
        return updated, ok_rep

    updated = transition_task(task, to_status=to_status, actor=actor, note=note)
    return updated, {"ok": True, "action": "ok", "violations": []}
