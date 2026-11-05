"""Unified authorization for task/team operations (T1).

Local CLI may claim --actor + --role; claimed role is trusted only for
authorization against the permission matrix. Trusted verification evidence
requires role=verifier and trust_level in {verified_run, cli_claimed} with
checks stamped trust=verified_run. Diagnostic/imported evidence never
satisfies verify-gate must_run.

Same principal must not write both development artifact.commit and
trusted verification pass fields in one call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

RoleName = Literal[
    "chief",
    "developer",
    "verifier",
    "nancy",
    "matcha",
    "eng_stub",
    "merge_bot",
    "requester",
    "unknown",
]

TrustLevel = Literal[
    "cli_claimed",  # local CLI --actor/--role
    "verified_run",  # future OMB / trusted runner
    "diagnostic",  # explicitly untrusted evidence
    "system",  # merge engine / kit internals
]

# Well-known actor → role aliases (case-insensitive). Explicit --role wins.
_ACTOR_ROLE_ALIASES: dict[str, RoleName] = {
    "chief": "chief",
    "幕僚长": "chief",
    "developer": "developer",
    "开发助手": "developer",
    "verifier": "verifier",
    "验证助手": "verifier",
    "nancy": "nancy",
    "matcha": "matcha",
    "merge": "merge_bot",
    "merge_bot": "merge_bot",
    "user": "requester",
    "eng-a": "eng_stub",
    "eng-b": "eng_stub",
    "eng_a": "eng_stub",
    "eng_b": "eng_stub",
}

# Status transitions: who may drive the task into `to_status`.
_TRANSITION_ROLES: dict[str, frozenset[str]] = {
    "执行中": frozenset({"chief", "developer", "eng_stub", "matcha", "system"}),
    "待验证": frozenset({"chief", "developer", "eng_stub"}),
    "验证通过": frozenset({"verifier"}),
    "需修改": frozenset({"verifier", "chief"}),
    "待合并": frozenset({"chief", "merge_bot", "system"}),
    "已完成": frozenset({"chief", "merge_bot", "system"}),
    "合并失败": frozenset({"chief", "merge_bot", "system"}),
    "受阻": frozenset({"chief", "developer", "verifier", "matcha", "eng_stub", "system"}),
    "已取消": frozenset({"chief", "requester"}),
    "待执行": frozenset({"chief", "system"}),
}

# Nancy: read-only progress / escalate — never drive execution statuses.
_NANCY_FORBIDDEN_STATUSES = frozenset(
    {
        "执行中",
        "待验证",
        "验证通过",
        "需修改",
        "待合并",
        "已完成",
        "合并失败",
    }
)


class AuthzError(PermissionError):
    """Raised when a principal is not allowed to perform an operation."""


@dataclass(frozen=True)
class Principal:
    actor: str
    role: RoleName
    trust_level: TrustLevel = "cli_claimed"

    @property
    def is_verifier_channel(self) -> bool:
        return self.role == "verifier" and self.trust_level in (
            "verified_run",
            "cli_claimed",
            "system",
        )

    @property
    def can_write_trusted_checks(self) -> bool:
        return self.is_verifier_channel and self.trust_level != "diagnostic"


def normalize_role(role: str | None) -> RoleName | None:
    if role is None:
        return None
    r = str(role).strip().lower().replace("-", "_")
    aliases = {
        "chief": "chief",
        "developer": "developer",
        "verifier": "verifier",
        "nancy": "nancy",
        "matcha": "matcha",
        "eng_stub": "eng_stub",
        "eng": "eng_stub",
        "engstub": "eng_stub",
        "merge_bot": "merge_bot",
        "merge": "merge_bot",
        "requester": "requester",
        "system": "merge_bot",  # treated as merge/system ops via trust
        "profile_chief": "chief",
        "profile_developer": "developer",
        "profile_verifier": "verifier",
        "profile_nancy": "nancy",
        "profile_matcha": "matcha",
    }
    if r in aliases:
        return aliases[r]  # type: ignore[return-value]
    if r in ("幕僚长",):
        return "chief"
    if r in ("开发助手",):
        return "developer"
    if r in ("验证助手",):
        return "verifier"
    return None


def infer_role_from_actor(actor: str) -> RoleName:
    key = (actor or "").strip().lower()
    if not key:
        return "unknown"
    if key in _ACTOR_ROLE_ALIASES:
        return _ACTOR_ROLE_ALIASES[key]
    # Eng-* pattern
    if key.startswith("eng"):
        return "eng_stub"
    return "unknown"


def resolve_principal(
    *,
    actor: str | None = None,
    role: str | None = None,
    profile: str | None = None,
    trust_level: TrustLevel | None = None,
    principal: Principal | None = None,
) -> Principal:
    if principal is not None:
        return principal
    if not actor or not str(actor).strip():
        raise AuthzError("操作需要执行身份 actor（或 Principal）")
    actor_s = str(actor).strip()
    role_name = normalize_role(role) or normalize_role(profile)
    if role_name is None:
        role_name = infer_role_from_actor(actor_s)
    if role_name == "unknown":
        raise AuthzError(
            f"无法解析角色：actor={actor_s!r}；请传 --role/--profile "
            f"（chief|developer|verifier|nancy|matcha|eng_stub|merge_bot）"
        )
    tl: TrustLevel = trust_level or "cli_claimed"
    return Principal(actor=actor_s, role=role_name, trust_level=tl)


def authorize_transition(principal: Principal, to_status: str) -> None:
    if principal.role == "nancy" and to_status in _NANCY_FORBIDDEN_STATUSES:
        raise AuthzError(
            f"Nancy（actor={principal.actor}）不得推进任务到 {to_status}；"
            "只读进度请用 team-status / team-summarize"
        )
    allowed = _TRANSITION_ROLES.get(to_status)
    if allowed is None:
        # Unknown target — state machine will reject; authz lets it through
        return
    # system trust can act as merge_bot/system roles
    role = principal.role
    if principal.trust_level == "system":
        role = "system" if "system" in allowed else role
    if role not in allowed and principal.role not in allowed:
        raise AuthzError(
            f"{principal.actor}（role={principal.role}）不得将任务迁移到 {to_status}；"
            f"允许角色: {', '.join(sorted(allowed))}"
        )


def authorize_record_check(
    principal: Principal,
    *,
    diagnostic: bool,
    wants_trusted_pass: bool,
    wants_artifact: bool,
) -> str:
    """Return trust stamp: verified_run | diagnostic | imported_evidence."""
    if wants_artifact and wants_trusted_pass and not diagnostic:
        raise AuthzError(
            "同一操作不得同时写 artifact.commit 与可信验收（result/executed pass）；"
            "请开发者 set-artifact，验证者 record-check（verifier 通道）"
        )

    # Nancy: never write check/artifact fields that look like acceptance
    if principal.role == "nancy":
        raise AuthzError(
            f"Nancy（actor={principal.actor}）不得 record-check / 手填验收；"
            "只读进度请用 team-status / team-summarize"
        )

    # Explicit diagnostic → never trusted for gate
    if diagnostic or principal.trust_level == "diagnostic":
        if wants_artifact:
            authorize_set_artifact(principal)
        return "diagnostic"

    if wants_trusted_pass:
        if not principal.can_write_trusted_checks:
            raise AuthzError(
                f"{principal.actor}（role={principal.role}）不是 verifier 信任通道，"
                "不得写入可信验收；可用 diagnostic=True 仅作诊断证据"
            )
        return "verified_run"

    # Non-pass bookkeeping without claiming trust
    return "diagnostic"


def authorize_set_artifact(principal: Principal) -> None:
    if principal.role == "verifier":
        raise AuthzError("verifier 不得写开发产物 artifact.commit（职责分离）")
    if principal.role not in ("developer", "chief"):
        raise AuthzError(
            f"{principal.actor}（role={principal.role}）不得写 artifact.commit"
        )


def authorize_eng_status_note(
    *,
    principal: Principal,
    task_id: str,
    assignee: str | None,
) -> None:
    if principal.role != "eng_stub":
        raise AuthzError(
            f"{principal.actor}（role={principal.role}）不得 eng_status_note"
        )
    if not assignee or not str(assignee).strip():
        raise AuthzError(
            f"任务 {task_id} 尚无 assignee；Eng 备注仅允许当前负责人写入"
        )
    if principal.actor.strip().lower() != str(assignee).strip().lower():
        raise AuthzError(
            f"{principal.actor} 不是任务 {task_id} 的当前负责人"
            f"（assignee={assignee}）；Eng 不得给他人任务写操作性备注"
        )


def authorize_budget(principal: Principal, op: str) -> None:
    if op == "set_budget" and principal.role not in ("chief",):
        raise AuthzError(f"{principal.actor}（role={principal.role}）不得 set_budget")
    if op == "record_tokens" and principal.role not in (
        "developer",
        "chief",
        "eng_stub",
        "verifier",
    ):
        raise AuthzError(
            f"{principal.actor}（role={principal.role}）不得 record_tokens"
        )


def authorize_lesson(principal: Principal, op: str) -> None:
    if op == "review" and principal.role not in ("verifier", "chief"):
        raise AuthzError(f"{principal.actor}（role={principal.role}）不得 lesson-review")
    if op == "publish" and principal.role not in ("chief",):
        raise AuthzError(
            f"{principal.actor}（role={principal.role}）不得 lesson-publish"
        )
    if op == "add" and principal.role not in (
        "developer",
        "verifier",
        "eng_stub",
        "chief",
        "matcha",
    ):
        raise AuthzError(f"{principal.actor}（role={principal.role}）不得 lesson-add")


def authorize_merge(principal: Principal) -> None:
    if principal.role not in ("chief", "merge_bot") and principal.trust_level != "system":
        raise AuthzError(
            f"{principal.actor}（role={principal.role}）不得执行 merge；"
            "仅 chief / merge_bot / system"
        )


def roles_for_docs() -> dict[str, Any]:
    return {
        "transition": {k: sorted(v) for k, v in _TRANSITION_ROLES.items()},
        "nancy_forbidden_statuses": sorted(_NANCY_FORBIDDEN_STATUSES),
    }
