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
    2. every must_run=true item has checks[] entry with same acceptance_id and executed=true
    3. verification.result == \"pass\"
    4. verification.bound_commit non-empty string
    5. artifact.commit non-empty string
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

        bound = verification.get("bound_commit")
        if not isinstance(bound, str) or not bound.strip():
            errors.append("verification.bound_commit 必填且非空")

        checks = verification.get("checks")
        if not isinstance(checks, list):
            errors.append("verification.checks 必须为 array")
            checks = []

        by_id: dict[str, dict[str, Any]] = {}
        for c in checks:
            if isinstance(c, dict) and isinstance(c.get("acceptance_id"), str):
                by_id[c["acceptance_id"]] = c

        for aid in must_ids:
            c = by_id.get(aid)
            if c is None:
                failed_ids.append(aid)
                errors.append(f"must_run 验收项 {aid} 缺少 checks 记录")
            elif c.get("executed") is not True:
                failed_ids.append(aid)
                errors.append(
                    f"must_run 验收项 {aid} 的 check.executed 不为 true（实际 {c.get('executed')!r}）"
                )

    artifact = task.get("artifact")
    if not isinstance(artifact, dict):
        errors.append("缺少 artifact 对象")
    else:
        commit = artifact.get("commit")
        if not isinstance(commit, str) or not commit.strip():
            errors.append("artifact.commit 必填且非空")

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
