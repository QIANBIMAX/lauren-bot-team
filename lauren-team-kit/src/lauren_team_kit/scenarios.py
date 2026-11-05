"""Python scenario runner for Lite C1–C3/C6–C8 and Team T1–T4.

Shell scripts are thin wrappers around this module. Each run uses a new id
unless the caller passes ``--task-id`` / ``--team-id``. Existing directories
are not overwritten unless ``--force`` is set. Commits created here are real
git commits in the task worktree. ``omb_delegate`` stays blocked/simulated.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from lauren_team_kit.cli import main as kit_main
from lauren_team_kit.handoff import omb_delegate
from lauren_team_kit.protocol import load_task, save_task, task_path_for
from lauren_team_kit.team import load_team, team_path_for
from lauren_team_kit.worktree_ops import ensure_task_worktree


class ScenarioError(RuntimeError):
    """A scenario assertion failed. This is not a pass."""


def _kit(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = int(kit_main(argv))
    return code, out.getvalue() + err.getvalue()


def _ok(argv: list[str], what: str) -> str:
    code, text = _kit(argv)
    if code != 0:
        raise ScenarioError(f"{what} 失败 rc={code}\n{text}")
    return text


def _fail(argv: list[str], what: str) -> str:
    code, text = _kit(argv)
    if code == 0:
        raise ScenarioError(f"{what} 应当失败却成功\n{text}")
    return text


def _new_id(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


def _task_id(prefix: str, requested: str | None, *, root: Path, force: bool) -> str:
    if not requested:
        return _new_id(prefix)
    path = task_path_for(root, requested)
    if path.exists() and not force:
        raise ScenarioError(f"拒绝覆盖已有演示 {path}；默认不使用 --force")
    return requested


def _team_id(prefix: str, requested: str | None, *, root: Path, force: bool) -> str:
    if not requested:
        return _new_id(prefix)
    path = team_path_for(root, requested)
    if path.exists() and not force:
        raise ScenarioError(f"拒绝覆盖已有团队 {path}；默认不使用 --force")
    return requested


def _fast(item_id: str, code: int) -> dict[str, Any]:
    return {
        "id": item_id,
        "description": item_id,
        "command": f"python -c exit {code}",
        "exec": {
            "kind": "argv",
            "argv": ["{python}", "-c", f"import sys; sys.exit({code})"],
            "cwd": ".",
            "timeout_sec": 30,
        },
        "must_run": True,
        "pass_criteria": "exit_code==0",
    }


def _set_acceptance(root: Path, task_id: str, items: list[dict[str, Any]]) -> None:
    path = task_path_for(root, task_id)
    task = load_task(path)
    task["acceptance"] = items
    save_task(path, task)


def _load(root: Path, task_id: str) -> dict[str, Any]:
    return load_task(task_path_for(root, task_id))


def _real_commit(root: Path, task_id: str, message: str) -> str:
    path = task_path_for(root, task_id)
    task = load_task(path)
    task, report = ensure_task_worktree(task, root=root)
    save_task(path, task)
    worktree = Path(str(report["path"]))
    note = worktree / "SCENARIO.md"
    note.write_text(f"{message}\n{uuid.uuid4().hex}\n", encoding="utf-8")
    for args in (
        ["git", "-C", str(worktree), "add", "SCENARIO.md"],
        ["git", "-C", str(worktree), "commit", "-m", message],
    ):
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ScenarioError(f"git {' '.join(args)} 失败: {(proc.stderr or proc.stdout).strip()}")
    rev = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    sha = (rev.stdout or "").strip()
    if rev.returncode != 0 or not sha:
        raise ScenarioError(f"无法读取提交: {(rev.stderr or '').strip()}")
    return sha


def _pass_gate(root: Path, task_id: str, *, actor_dev: str = "developer") -> str:
    """Real commit + one passing argv round. Does not merge."""
    task = _load(root, task_id)
    if task["status"] == "待执行":
        _ok(
            ["transition", "--task-id", task_id, "--root", str(root), "--to", "执行中", "--actor", "chief", "--note", "start"],
            "进入执行中",
        )
    elif task["status"] == "需修改":
        _ok(
            ["transition", "--task-id", task_id, "--root", str(root), "--to", "执行中", "--actor", actor_dev, "--note", "rework"],
            "返工进入执行中",
        )
    sha = _real_commit(root, task_id, f"scenario {task_id}")
    _ok(
        ["set-artifact", "--task-id", task_id, "--root", str(root), "--commit", sha, "--actor", actor_dev, "--role", "developer"],
        "set-artifact",
    )
    if _load(root, task_id)["status"] == "执行中":
        _ok(
            ["transition", "--task-id", task_id, "--root", str(root), "--to", "待验证", "--actor", actor_dev, "--note", "submit"],
            "提交待验证",
        )
    _ok(
        ["run-acceptance", "--task-id", task_id, "--root", str(root), "--bound-commit", sha],
        "run-acceptance",
    )
    _ok(["verify-gate", "--task-id", task_id, "--root", str(root)], "verify-gate")
    _ok(
        ["transition", "--task-id", task_id, "--root", str(root), "--to", "验证通过", "--actor", "verifier", "--note", "gate"],
        "验证通过",
    )
    return sha


def scenario_c1(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del team_id
    tid = _task_id("c1", task_id, root=root, force=force)
    _ok(["create", "--title", "C1 正常闭环", "--task-id", tid, "--root", str(root)], "create")
    _set_acceptance(root, tid, [_fast("A1", 0), _fast("A2", 0)])
    sha = _pass_gate(root, tid)
    task = _load(root, tid)
    checks = (task.get("verification") or {}).get("checks") or []
    if task["status"] != "验证通过":
        raise ScenarioError(f"C1 状态 {task['status']}")
    if task["merge_policy"]["mode"] != "confirm":
        raise ScenarioError("C1 不得放宽合并确认")
    if len({c.get("round_id") for c in checks}) != 1:
        raise ScenarioError("C1 must_run 必须同一轮")
    return {"ok": True, "scenario": "c1", "task_id": tid, "commit": sha, "merged": False}


def scenario_c2(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del team_id
    tid = _task_id("c2", task_id, root=root, force=force)
    _ok(["create", "--title", "C2 失败后修复", "--task-id", tid, "--root", str(root)], "create")
    _set_acceptance(root, tid, [_fast("C2-CHECK", 1)])
    _ok(
        ["transition", "--task-id", tid, "--root", str(root), "--to", "执行中", "--actor", "chief", "--note", "round1"],
        "round1 start",
    )
    _ok(
        ["transition", "--task-id", tid, "--root", str(root), "--to", "待验证", "--actor", "developer", "--note", "submit fail"],
        "round1 submit",
    )
    failed = _fail(["run-acceptance", "--task-id", tid, "--root", str(root)], "round1 acceptance")
    if "ok=False" not in failed and '"ok": false' not in failed.lower():
        raise ScenarioError(f"round1 应汇总为不通过\n{failed}")
    _fail(["verify-gate", "--task-id", tid, "--root", str(root)], "round1 gate")
    _fail(
        ["transition", "--task-id", tid, "--root", str(root), "--to", "验证通过", "--actor", "verifier"],
        "round1 不得验证通过",
    )
    _ok(
        ["transition", "--task-id", tid, "--root", str(root), "--to", "需修改", "--actor", "verifier", "--note", "rework"],
        "需修改",
    )
    _set_acceptance(root, tid, [_fast("C2-CHECK", 0)])
    sha = _pass_gate(root, tid)
    if _load(root, tid)["status"] != "验证通过":
        raise ScenarioError("C2 修复后应为验证通过")
    return {
        "ok": True,
        "scenario": "c2",
        "task_id": tid,
        "commit": sha,
        "historical_placeholder_sha": False,
        "merged": False,
    }


def _repo_layout() -> tuple[Path, Path] | None:
    here = Path(__file__).resolve()
    candidate = here.parents[3] if len(here.parents) > 3 else None
    if candidate is None:
        return None
    demo = candidate / "demo-app"
    rule = candidate / "lauren-team-kit" / "rules" / "filter-empty-query.md"
    if demo.is_dir() and rule.is_file():
        return demo, rule
    return None


def scenario_c3(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del team_id
    found = _repo_layout()
    if found is None:
        return {"ok": False, "scenario": "c3", "status": "cannot_run", "reason": "找不到 demo-app 与规则文件"}
    demo, rule = found
    data = demo / "data" / "tasks.json"
    if not data.is_file():
        sys.path.insert(0, str(demo / "src"))
        from demo_app.seed import seed

        seed(demo / "fixtures" / "basic.json", data)
    from lauren_team_kit.rule_check import run_rule

    buggy = run_rule(rule, demo, "buggy")
    fixed = run_rule(rule, demo, "fixed")
    if buggy.get("ok") or buggy.get("status") == "pass":
        raise ScenarioError(f"buggy 探针不得 pass: {buggy.get('status')}")
    if not fixed.get("ok") or fixed.get("status") != "pass":
        raise ScenarioError(f"fixed 探针应 pass: {fixed.get('status')} {fixed.get('errors')}")
    tid = _task_id("c3", task_id, root=root, force=force)
    _ok(["create", "--title", "C3 规则复用", "--task-id", tid, "--root", str(root)], "create")
    _set_acceptance(root, tid, [_fast("C3-CLEAN-FIXED", 0)])
    sha = _pass_gate(root, tid)
    return {
        "ok": True,
        "scenario": "c3",
        "task_id": tid,
        "commit": sha,
        "buggy_status": buggy.get("status"),
        "fixed_status": fixed.get("status"),
        "merged": False,
    }


def scenario_c6(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del team_id
    tid = _task_id("c6", task_id, root=root, force=force)
    _ok(["create", "--title", "C6 中断恢复", "--task-id", tid, "--root", str(root)], "create")
    _ok(
        ["transition", "--task-id", tid, "--root", str(root), "--to", "执行中", "--actor", "chief", "--note", "start"],
        "start",
    )
    sha = _real_commit(root, tid, f"c6 {tid}")
    _ok(
        ["set-artifact", "--task-id", tid, "--root", str(root), "--commit", sha, "--actor", "developer"],
        "artifact",
    )
    _ok(
        [
            "block",
            "--task-id",
            tid,
            "--root",
            str(root),
            "--code",
            "KILL",
            "--message",
            "模拟进程被杀",
            "--recovery-hint",
            "resume 后勿重复提交",
            "--resume-point",
            "执行中",
            "--actor",
            "chief",
        ],
        "block kill",
    )
    _ok(["resume", "--task-id", tid, "--root", str(root), "--actor", "chief"], "resume running")
    task = _load(root, tid)
    if task["status"] != "执行中" or (task.get("artifact") or {}).get("commit") != sha:
        raise ScenarioError("C6 恢复执行中时不得丢掉已有提交")
    _ok(
        ["transition", "--task-id", tid, "--root", str(root), "--to", "待验证", "--actor", "developer", "--note", "submit"],
        "待验证",
    )
    _ok(
        [
            "block",
            "--task-id",
            tid,
            "--root",
            str(root),
            "--code",
            "MISSING_DEP",
            "--message",
            "缺依赖",
            "--recovery-hint",
            "装好后 resume，未跑检查不得标 pass",
            "--resume-point",
            "待验证",
            "--actor",
            "verifier",
        ],
        "block dep",
    )
    _ok(["resume", "--task-id", tid, "--root", str(root), "--actor", "chief"], "resume verify")
    task = _load(root, tid)
    if task["status"] != "待验证":
        raise ScenarioError(f"C6 应回到待验证，实际 {task['status']}")
    if (task.get("verification") or {}).get("result") == "pass":
        raise ScenarioError("C6 未跑检查不得标 pass")
    if (task.get("artifact") or {}).get("commit") != sha:
        raise ScenarioError("C6 artifact 被改写")
    return {"ok": True, "scenario": "c6", "task_id": tid, "commit": sha}


def scenario_c7(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del team_id
    tid = _task_id("c7", task_id, root=root, force=force)
    tokens = _new_id("c7tok")
    raised = _new_id("c7raise")
    _ok(["create", "--title", "C7 预算", "--task-id", tid, "--root", str(root)], "create A")
    _ok(
        ["set-budget", "--task-id", tid, "--root", str(root), "--max-attempts", "2", "--max-tokens", "100", "--actor", "chief"],
        "budget A",
    )
    _ok(["transition", "--task-id", tid, "--root", str(root), "--to", "执行中", "--actor", "chief", "--note", "a1"], "a1")
    _ok(["transition", "--task-id", tid, "--root", str(root), "--to", "需修改", "--actor", "verifier", "--note", "f1"], "f1")
    _ok(["transition", "--task-id", tid, "--root", str(root), "--to", "执行中", "--actor", "developer", "--note", "a2"], "a2")
    _ok(["transition", "--task-id", tid, "--root", str(root), "--to", "需修改", "--actor", "verifier", "--note", "f2"], "f2")
    denied = _fail(
        ["transition", "--task-id", tid, "--root", str(root), "--to", "执行中", "--actor", "developer", "--note", "a3"],
        "第三次执行",
    )
    if "BUDGET_ATTEMPTS" not in denied:
        raise ScenarioError(f"应出现 BUDGET_ATTEMPTS\n{denied}")
    task = _load(root, tid)
    if task["status"] != "受阻":
        raise ScenarioError("超次后应为受阻")
    _ok(["create", "--title", "C7 tokens", "--task-id", tokens, "--root", str(root)], "create B")
    _ok(
        ["set-budget", "--task-id", tokens, "--root", str(root), "--max-tokens", "50", "--max-attempts", "5", "--actor", "chief"],
        "budget B",
    )
    _ok(["record-tokens", "--task-id", tokens, "--root", str(root), "--tokens", "40", "--actor", "developer"], "tok40")
    _ok(["record-tokens", "--task-id", tokens, "--root", str(root), "--tokens", "20", "--actor", "developer"], "tok20")
    denied_b = _fail(
        ["transition", "--task-id", tokens, "--root", str(root), "--to", "执行中", "--actor", "chief"],
        "token 超额",
    )
    if "BUDGET_TOKENS" not in denied_b:
        raise ScenarioError(f"应出现 BUDGET_TOKENS\n{denied_b}")
    _ok(["create", "--title", "C7 raise", "--task-id", raised, "--root", str(root)], "create C")
    _ok(["set-budget", "--task-id", raised, "--root", str(root), "--max-attempts", "1", "--actor", "chief"], "budget C")
    denied_c = _fail(
        ["set-budget", "--task-id", raised, "--root", str(root), "--max-attempts", "3", "--actor", "chief"],
        "抬预算",
    )
    if "allow-raise" not in denied_c:
        raise ScenarioError(f"抬预算应被拒绝\n{denied_c}")
    _ok(
        ["set-budget", "--task-id", raised, "--root", str(root), "--max-attempts", "3", "--allow-raise", "--actor", "chief"],
        "allow-raise",
    )
    return {"ok": True, "scenario": "c7", "task_id": tid, "tokens_task": tokens, "raise_task": raised}


def scenario_c8(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del team_id
    tid = _task_id("c8", task_id, root=root, force=force)
    lesson = _new_id("c8rule")
    _ok(["create", "--title", "C8 经验发布", "--task-id", tid, "--root", str(root)], "create")
    draft = task_path_for(root, tid).parent / "draft-rule.md"
    draft.write_text("# rule\n\n空 query 必须返回 []。\n", encoding="utf-8")
    _ok(
        [
            "lesson-add",
            "--task-id",
            tid,
            "--root",
            str(root),
            "--id",
            lesson,
            "--summary",
            "空 query 必须返回 []",
            "--rule-file",
            str(draft),
            "--actor",
            "developer",
            "--probe-ref",
            "c8-probe",
            "--probe",
            "empty safe",
        ],
        "lesson-add",
    )
    _fail(
        ["lesson-publish", "--task-id", tid, "--root", str(root), "--id", lesson, "--actor", "chief"],
        "未批准不得发布",
    )
    probe = json.dumps(
        {
            "probe_id": "c8-probe",
            "passed": True,
            "stdout_summary": "[]",
            "evidence": "checks/c8.log",
            "at": "2026-11-05T11:00:00+08:00",
        },
        ensure_ascii=False,
    )
    _ok(
        [
            "lesson-review",
            "--task-id",
            tid,
            "--root",
            str(root),
            "--id",
            lesson,
            "--verdict",
            "approve",
            "--actor",
            "verifier",
            "--notes",
            "ok",
            "--probe-result-json",
            probe,
        ],
        "review",
    )
    _ok(
        ["lesson-publish", "--task-id", tid, "--root", str(root), "--id", lesson, "--actor", "chief"],
        "publish",
    )
    store = root / "lauren-team-kit" / "lessons" / "store" / f"{lesson}.json"
    rule = root / "lauren-team-kit" / "rules" / f"{lesson}.md"
    if not store.is_file() or not rule.is_file():
        raise ScenarioError(f"发布物缺失 {store} {rule}")
    task = _load(root, tid)
    published = (task.get("lessons") or {}).get("published") or []
    if not any(row.get("id") == lesson for row in published if isinstance(row, dict)):
        raise ScenarioError("task.lessons.published 没有这条经验")
    return {"ok": True, "scenario": "c8", "task_id": tid, "lesson_id": lesson}


def scenario_t1(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del task_id
    team = _team_id("t1", team_id, root=root, force=force)
    alpha = _new_id("t1a")
    beta = _new_id("t1b")
    _ok(
        ["team-create", "--root", str(root), "--team-id", team, "--title", "T1 双任务", "--eng-stub", "Eng-A", "--eng-stub", "Eng-B"],
        "team-create",
    )
    for tid, title in ((alpha, "Alpha"), (beta, "Beta")):
        _ok(
            ["team-add-task", "--root", str(root), "--team-id", team, "--task-id", tid, "--title", title, "--actor", "Matcha"],
            f"add {tid}",
        )
    _ok(
        ["team-assign", "--root", str(root), "--team-id", team, "--task-id", alpha, "--assignee", "Eng-A", "--actor", "Matcha", "--note", "alpha"],
        "assign a",
    )
    _ok(
        ["team-assign", "--root", str(root), "--team-id", team, "--task-id", beta, "--assignee", "Eng-B", "--actor", "Matcha", "--note", "beta"],
        "assign b",
    )
    _ok(["transition", "--task-id", alpha, "--root", str(root), "--to", "执行中", "--actor", "Eng-A", "--note", "start"], "alpha run")
    _ok(["transition", "--task-id", beta, "--root", str(root), "--to", "执行中", "--actor", "Eng-B", "--note", "start"], "beta run")
    _ok(
        [
            "block",
            "--task-id",
            beta,
            "--root",
            str(root),
            "--code",
            "WAITING_ENG",
            "--message",
            "等待拆解",
            "--recovery-hint",
            "Eng 不写业务代码",
            "--resume-point",
            "执行中",
            "--actor",
            "Matcha",
        ],
        "block beta",
    )
    _ok(
        ["team-summarize", "--root", str(root), "--team-id", team, "--actor", "Nancy", "--note", "双任务进行中"],
        "summarize",
    )
    doc = load_team(team_path_for(root, team))
    if doc["child_task_ids"] != [alpha, beta]:
        raise ScenarioError(f"子任务顺序不对 {doc['child_task_ids']}")
    if _load(root, alpha)["status"] != "执行中" or _load(root, beta)["status"] != "受阻":
        raise ScenarioError("T1 状态不符合双任务预期")
    if (doc.get("summaries") or [])[-1].get("by") != "Nancy":
        raise ScenarioError("汇总应由 Nancy 写入")
    return {"ok": True, "scenario": "t1", "team_id": team, "alpha": alpha, "beta": beta}


def scenario_t2(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del task_id
    team = _team_id("t2", team_id, root=root, force=force)
    alpha = _new_id("t2a")
    _ok(
        ["team-create", "--root", str(root), "--team-id", team, "--title", "T2 handoff", "--eng-stub", "Eng-A", "--eng-stub", "Eng-B"],
        "team-create",
    )
    _ok(
        ["team-add-task", "--root", str(root), "--team-id", team, "--task-id", alpha, "--title", "Alpha 包", "--actor", "Matcha"],
        "add",
    )
    _ok(
        ["team-assign", "--root", str(root), "--team-id", team, "--task-id", alpha, "--assignee", "Eng-A", "--assignee-role", "eng_coordinator", "--actor", "Matcha", "--note", "pkg"],
        "assign",
    )
    acceptance = json.dumps([_fast("A-alpha", 0)], ensure_ascii=False)
    _ok(
        [
            "team-eng-decompose",
            "--root",
            str(root),
            "--team-id",
            team,
            "--task-id",
            alpha,
            "--actor",
            "Eng-A",
            "--goal",
            "Alpha 包",
            "--in-scope",
            "alpha",
            "--acceptance-json",
            acceptance,
            "--worktree",
            str(root / "workspace" / "wt-alpha"),
        ],
        "decompose",
    )
    text = _ok(
        ["team-handoff", "--root", str(root), "--team-id", team, "--task-id", alpha, "--actor", "Eng-A", "--developer", "developer", "--mode", "local"],
        "handoff",
    )
    match = re.search(r"handoff (\S+) task=", text)
    if not match:
        raise ScenarioError(f"没有 handoff id\n{text}")
    hid = match.group(1)
    _ok(
        ["team-ack-handoff", "--root", str(root), "--team-id", team, "--handoff-id", hid, "--actor", "developer"],
        "ack",
    )
    delegated = omb_delegate(root=root, team_id=team, handoff_id=hid, actor="system")
    if delegated.get("omb_delegation") != "blocked" or delegated.get("mode") != "simulated" or delegated.get("ok"):
        raise ScenarioError(f"不得宣称真实委派: {delegated}")
    return {"ok": True, "scenario": "t2", "team_id": team, "task_id": alpha, "handoff_id": hid, "mode": "local", "omb_delegation": "blocked"}


def scenario_t3(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    del task_id
    team = _team_id("t3", team_id, root=root, force=force)
    alpha = _new_id("t3a")
    _ok(
        ["team-create", "--root", str(root), "--team-id", team, "--title", "T3 nancy", "--eng-stub", "Eng-A", "--eng-stub", "Eng-B"],
        "team-create",
    )
    _ok(
        ["team-add-task", "--root", str(root), "--team-id", team, "--task-id", alpha, "--title", "Alpha", "--actor", "Matcha"],
        "add",
    )
    _ok(
        ["team-assign", "--root", str(root), "--team-id", team, "--task-id", alpha, "--assignee", "Eng-A", "--actor", "Matcha", "--note", "pkg"],
        "assign",
    )
    _ok(
        ["team-todo-add", "--root", str(root), "--team-id", team, "--actor", "Nancy", "--text", "跟进待办", "--source", "user"],
        "todo",
    )
    _ok(["transition", "--task-id", alpha, "--root", str(root), "--to", "执行中", "--actor", "Eng-A", "--note", "start"], "start")
    _ok(
        [
            "block",
            "--task-id",
            alpha,
            "--root",
            str(root),
            "--code",
            "WAITING_DEV",
            "--message",
            "等 developer",
            "--recovery-hint",
            "handoff 后解除",
            "--resume-point",
            "执行中",
            "--actor",
            "Matcha",
        ],
        "block",
    )
    _ok(["team-summarize", "--root", str(root), "--team-id", team, "--actor", "Nancy", "--note", "任务尚未完成"], "sum1")
    _ok(["team-summarize", "--root", str(root), "--team-id", team, "--actor", "Nancy", "--note", "再次汇总"], "sum2")
    _ok(
        ["team-blocker-resolve", "--root", str(root), "--team-id", team, "--task-id", alpha, "--reason-code", "WAITING_DEV", "--actor", "Nancy", "--note", "已安排"],
        "resolve",
    )
    _ok(
        ["resume", "--task-id", alpha, "--root", str(root), "--actor", "Matcha", "--to", "执行中", "--clear-blocker-code", "WAITING_DEV"],
        "resume",
    )
    doc = load_team(team_path_for(root, team))
    todos = doc.get("todos") or []
    if not any(row.get("todo_id") == "todo-001" for row in todos if isinstance(row, dict)):
        raise ScenarioError("Nancy 待办没有落下")
    open_esc = [
        row
        for row in (doc.get("blockers_escalated") or [])
        if isinstance(row, dict) and (row.get("status") or row.get("lifecycle") or "open") == "open"
    ]
    if open_esc:
        raise ScenarioError(f"阻塞未解除 {open_esc}")
    if _load(root, alpha)["status"] != "执行中":
        raise ScenarioError("解除后应回到执行中")
    return {"ok": True, "scenario": "t3", "team_id": team, "task_id": alpha, "mode": "local"}


def scenario_t4(root: Path, *, task_id: str | None, team_id: str | None, force: bool) -> dict[str, Any]:
    team = _team_id("t4", team_id, root=root, force=force)
    tid = _task_id("t4lesson", task_id, root=root, force=force)
    lesson = _new_id("t4rule")
    _ok(
        ["team-create", "--root", str(root), "--team-id", team, "--title", "T4", "--eng-stub", "Eng-A", "--eng-stub", "Eng-B"],
        "team-create",
    )
    _ok(
        ["team-todo-add", "--root", str(root), "--team-id", team, "--actor", "Nancy", "--text", "T4 跟进规则发布", "--source", "user"],
        "todo",
    )
    _ok(["create", "--title", "T4 lesson", "--task-id", tid, "--root", str(root)], "create")
    draft = task_path_for(root, tid).parent / "t4-rule.md"
    draft.write_text("# t4\n空输入必须返回 []。\n", encoding="utf-8")
    _ok(
        [
            "lesson-add",
            "--task-id",
            tid,
            "--root",
            str(root),
            "--id",
            lesson,
            "--summary",
            "空输入必须 []",
            "--rule-file",
            str(draft),
            "--actor",
            "developer",
            "--applies-to",
            "filter",
            "--probe-ref",
            "t4-probe",
            "--probe",
            "empty",
        ],
        "add",
    )
    _fail(
        ["lesson-review", "--task-id", tid, "--root", str(root), "--id", lesson, "--verdict", "approve", "--actor", "verifier", "--notes", "bare"],
        "无探针不得批准",
    )
    probe = json.dumps(
        {"probe_id": "t4-probe", "passed": True, "stdout_summary": "[]", "evidence": "checks/t4.log", "at": "2026-11-05T11:00:00+08:00"},
        ensure_ascii=False,
    )
    _ok(
        ["lesson-review", "--task-id", tid, "--root", str(root), "--id", lesson, "--verdict", "approve", "--actor", "verifier", "--notes", "ok", "--probe-result-json", probe],
        "review",
    )
    _ok(["lesson-publish", "--task-id", tid, "--root", str(root), "--id", lesson, "--actor", "chief"], "publish")
    store = json.loads((root / "lauren-team-kit" / "lessons" / "store" / f"{lesson}.json").read_text(encoding="utf-8"))
    version = store["rules_version"]
    _ok(
        ["lesson-rule-load", "--root", str(root), "--team-id", team, "--id", lesson, "--eng", "Eng-A", "--rules-version", version, "--actor", "Eng-A"],
        "load",
    )
    _ok(
        ["lesson-rule-receive", "--root", str(root), "--team-id", team, "--id", lesson, "--developer", "developer", "--rules-version", version, "--actor", "developer"],
        "receive",
    )
    _ok(
        ["lesson-recurrence", "--root", str(root), "--team-id", team, "--id", lesson, "--probe-result-json", '{"probe_id":"t4-probe","passed":false,"stdout_summary":"TypeError"}', "--actor", "verifier"],
        "recurrence",
    )
    doc = load_team(team_path_for(root, team))
    receipts = doc.get("rule_receipts") or []
    if not any(row.get("kind") == "load" for row in receipts) or not any(row.get("kind") == "receive" for row in receipts):
        raise ScenarioError("规则交接回执不完整")
    events = doc.get("recurrence_events") or []
    if not any(row.get("recurrence_blocked") for row in events if isinstance(row, dict)):
        raise ScenarioError("复发应被拦住")
    delegated = omb_delegate(root=root, team_id=team, handoff_id="none", actor="system")
    if delegated.get("mode") != "simulated" or delegated.get("omb_delegation") != "blocked":
        raise ScenarioError("T4 不得写成真实委派")
    return {"ok": True, "scenario": "t4", "team_id": team, "task_id": tid, "lesson_id": lesson, "omb_delegation": "blocked"}


SCENARIOS: dict[str, Callable[..., dict[str, Any]]] = {
    "c1": scenario_c1,
    "c2": scenario_c2,
    "c3": scenario_c3,
    "c6": scenario_c6,
    "c7": scenario_c7,
    "c8": scenario_c8,
    "t1": scenario_t1,
    "t2": scenario_t2,
    "t3": scenario_t3,
    "t4": scenario_t4,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m lauren_team_kit.scenarios")
    parser.add_argument("name", choices=sorted(SCENARIOS))
    parser.add_argument("--root", required=True)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--team-id", default=None)
    parser.add_argument("--force", action="store_true", help="覆盖已有同名演示；默认拒绝")
    args = parser.parse_args(argv)
    try:
        result = SCENARIOS[args.name](
            Path(args.root).resolve(),
            task_id=args.task_id,
            team_id=args.team_id,
            force=bool(args.force),
        )
    except ScenarioError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
