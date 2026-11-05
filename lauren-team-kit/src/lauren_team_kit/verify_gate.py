"""Hard gate for status 验证通过: must_run × checks + result/commits."""

from __future__ import annotations

from typing import Any


class VerifyGateError(ValueError):
    """Raised when transition to 验证通过 fails the hard gate."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__(self.format_errors(self.errors))

    @staticmethod
    def format_errors(errors: list[str]) -> str:
        if not errors:
            return "验证硬门未通过"
        if len(errors) == 1:
            return f"验证硬门拒绝 → 验证通过：{errors[0]}"
        body = "\n".join(f"  - {e}" for e in errors)
        return f"验证硬门拒绝 → 验证通过：\n{body}"


def _looks_like_git_sha(s: str) -> bool:
    if len(s) < 7:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in s)


def commits_match(a: Any, b: Any) -> bool:
    """True if two commit ids refer to the same revision.

    Rules: strip whitespace; empty never matches; equal OK; if both look like
    git SHAs, longer may startswith shorter when shorter length >= 7.
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    left = a.strip()
    right = b.strip()
    if not left or not right:
        return False
    if left == right:
        return True
    if _looks_like_git_sha(left) and _looks_like_git_sha(right):
        longer, shorter = (left, right) if len(left) >= len(right) else (right, left)
        if len(shorter) >= 7 and longer.lower().startswith(shorter.lower()):
            return True
    return False


def must_run_acceptance_ids(task: dict[str, Any]) -> list[str]:
    acceptance = task.get("acceptance")
    if not isinstance(acceptance, list):
        return []
    ids: list[str] = []
    for item in acceptance:
        if not isinstance(item, dict):
            continue
        if item.get("must_run") is True:
            aid = item.get("id")
            if isinstance(aid, str) and aid:
                ids.append(aid)
    return ids


def evaluate_verify_gate(task: dict[str, Any]) -> list[str]:
    """Return Chinese error strings; empty list means PASS.

    Rules before allowing → 验证通过 (or validating status already 验证通过):
    1. acceptance list present (non-empty)
    2. every must_run=true item has checks[] entry with same acceptance_id,
       executed=true, exit_code==0; if check has result, it must be pass
    3. verification.result == \"pass\"
    4. verification.bound_commit non-empty string
    5. artifact.commit non-empty string
    6. artifact.commit 与 verification.bound_commit 一致（短/长 SHA 可互认）
    """
    errors: list[str] = []
    failed_ids: list[str] = []

    acceptance = task.get("acceptance")
    if not isinstance(acceptance, list) or len(acceptance) < 1:
        errors.append("缺少 acceptance 列表（至少 1 项）")
        return errors

    must_ids = must_run_acceptance_ids(task)
    # also flag must_run items missing id
    for i, item in enumerate(acceptance):
        if isinstance(item, dict) and item.get("must_run") is True:
            if not isinstance(item.get("id"), str) or not item.get("id"):
                errors.append(f"acceptance[{i}] must_run=true 但缺少 id")

    verification = task.get("verification")
    bound: Any = None
    if not isinstance(verification, dict):
        errors.append("缺少 verification 对象")
        for aid in must_ids:
            failed_ids.append(aid)
            errors.append(f"must_run 验收项 {aid} 缺少 checks 记录（executed=true）")
        errors.append("verification.result 必须为 pass")
        errors.append("verification.bound_commit 必填且非空")
    else:
        result = verification.get("result")
        if result != "pass":
            errors.append(f"verification.result 必须为 pass，实际 {result!r}")
        # Trusted channel marker (T1); legacy tasks without trust still need trusted checks
        vtrust = verification.get("trust")
        if vtrust not in (None, "verified_run"):
            errors.append(
                f"verification.trust 必须为 verified_run 才可自动验收，实际 {vtrust!r}"
            )

        bound = verification.get("bound_commit")
        if not isinstance(bound, str) or not bound.strip():
            errors.append("verification.bound_commit 必填且非空")
            bound = None

        checks = verification.get("checks")
        if not isinstance(checks, list):
            errors.append("verification.checks 必须为 array")
            checks = []

        round_id = verification.get("round_id")
        ver_trust = verification.get("trust")

        by_id: dict[str, dict[str, Any]] = {}
        for c in checks:
            if not isinstance(c, dict) or not isinstance(c.get("acceptance_id"), str):
                continue
            # Only trusted checks in the current verification round count for the gate.
            trust = c.get("trust")
            if trust in (None, ""):
                # Legacy entries without trust stamp: accept only if overall
                # verification.trust is verified_run (seeded by new recorder).
                if ver_trust != "verified_run":
                    continue
            elif trust != "verified_run":
                continue
            if round_id and c.get("round_id") not in (None, round_id):
                continue
            by_id[c["acceptance_id"]] = c

        if must_ids and not by_id and checks:
            errors.append(
                "verification.checks 无当前轮次可信记录"
                "（diagnostic/imported_evidence 不计入自动验收）"
            )

        for aid in must_ids:
            c = by_id.get(aid)
            if c is None:
                failed_ids.append(aid)
                errors.append(
                    f"must_run 验收项 {aid} 缺少可信 checks 记录"
                    f"（需 verifier 通道 + trust=verified_run"
                    + (f" + round_id={round_id}" if round_id else "")
                    + "）"
                )
                continue
            if c.get("executed") is not True:
                failed_ids.append(aid)
                errors.append(
                    f"must_run 验收项 {aid} 的 check.executed 不为 true（实际 {c.get('executed')!r}）"
                )
                continue
            if "exit_code" not in c:
                failed_ids.append(aid)
                errors.append(f"must_run 验收项 {aid} 缺少 check.exit_code（必须为 0）")
            elif c.get("exit_code") != 0:
                failed_ids.append(aid)
                errors.append(
                    f"must_run 验收项 {aid} 的 check.exit_code 必须为 0（实际 {c.get('exit_code')!r}）"
                )
            if "result" in c and c.get("result") != "pass":
                failed_ids.append(aid)
                errors.append(
                    f"must_run 验收项 {aid} 的 check.result 必须为 pass（实际 {c.get('result')!r}）"
                )

    artifact = task.get("artifact")
    commit: Any = None
    if not isinstance(artifact, dict):
        errors.append("缺少 artifact 对象")
    else:
        commit = artifact.get("commit")
        if not isinstance(commit, str) or not commit.strip():
            errors.append("artifact.commit 必填且非空")
            commit = None

    if (
        isinstance(bound, str)
        and bound.strip()
        and isinstance(commit, str)
        and commit.strip()
        and not commits_match(commit, bound)
    ):
        errors.append(
            f"artifact.commit 与 verification.bound_commit 不一致"
            f"（artifact={commit.strip()!r}, bound={bound.strip()!r}）"
        )

    if failed_ids:
        # summary line for parent/logs
        uniq = list(dict.fromkeys(failed_ids))
        errors.append(f"未通过的 acceptance_id: {', '.join(uniq)}")

    return errors


def assert_verify_gate(task: dict[str, Any]) -> None:
    errors = evaluate_verify_gate(task)
    if errors:
        raise VerifyGateError(errors)


def gate_report(task: dict[str, Any]) -> dict[str, Any]:
    errors = evaluate_verify_gate(task)
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "ok": not errors,
        "must_run_ids": must_run_acceptance_ids(task),
        "errors": errors,
    }
