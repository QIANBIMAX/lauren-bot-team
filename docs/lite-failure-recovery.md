# Lite 故障恢复（常见情况）

> 日期：2026-11-05（Asia/Shanghai）  
> 面向：跑 Lite 三角 / kit CLI 时卡住、报错、被取消或预算打满。  
> 路径约定：先 `cd` 到 clone 根目录，再 `export PROJECT_ROOT="$(pwd)"`。

跨平台入口优先：

```bash
cd "${PROJECT_ROOT}/lauren-team-kit"
python3 -m venv .venv          # 若还没有
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m lauren_team_kit --help
```

Windows PowerShell 把 `.venv/bin/` 换成 `.venv\Scripts\`；**一期 Win/Linux 未验收**，下列命令以 Mac/Linux Bash 为例。

---

## 1. 缺依赖：`jsonschema` / 模块找不到

**症状：** `ModuleNotFoundError: jsonschema`，或 `validate` / Schema 相关命令退出码 2。

**处理：**

```bash
cd "${PROJECT_ROOT}/lauren-team-kit"
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'   # 含 jsonschema + pytest
# 或仅 Schema：.venv/bin/pip install -e '.[schema]'
.venv/bin/python -c "import jsonschema; print(jsonschema.__version__)"
```

仍失败：确认用的是 **项目 `.venv` 里的 python**，不是系统裸 `python3` 忘装 optional。

---

## 2. 预算受阻（tokens / attempts / duration）

**症状：** 任务状态变成 **受阻**；CLI 出现 `BUDGET_TOKENS` / `BUDGET_ATTEMPTS` / `BUDGET_DURATION`；或 `resume` / 进入执行中被拒。

**不要做：** 反复 `resume --to 执行中` 硬闯（Lite-B L4 会挡）。

**处理顺序：**

1. 看清原因：
   ```bash
   .venv/bin/python -m lauren_team_kit check-budget --task <task.json或task_id>
   ```
2. **幕僚长确认**后抬限（须显式允许）：
   ```bash
   .venv/bin/python -m lauren_team_kit set-budget --task <id> \
     --max-tokens <更大值> --allow-raise
   ```
   （attempts / duration 同理换对应参数。）
3. 再恢复。默认回到存储的 `resume_point`；若目标是执行中，会再跑预算硬门：
   ```bash
   .venv/bin/python -m lauren_team_kit resume --task <id>
   ```
4. 若业务上不该继续：保持受阻，或走取消（下一节）。

---

## 3. 取消任务

**症状：** 人不想继续；或执行器还在跑。

```bash
.venv/bin/python -m lauren_team_kit cancel --task <id> --actor chief --reason "用户取消"
```

效果（Lite-C）：
- 状态 → **已取消**
- 写下 `cancel.cancel_requested`（租约）
- **尽力**对登记 PID 发 SIGTERM（不宣称 OS 级必杀已验收）

只要标记、不发信号：加 `--no-signal`。

取消后不要再当「执行中」去合并；新需求请开新 task。

---

## 4. 中断 / 重启后对账（resume）

**症状：** 终端关了、机器睡了、或不确定上次执行有没有写完；任务停在受阻 / 执行中附近。

```bash
.venv/bin/python -m lauren_team_kit resume --task <id>
```

Lite-C 会先对账（租约、Git HEAD、脏文件等）。**结果未知 → 保持受阻**，不会盲目重复执行或重复提交。

若对账报告写明 blocker：按消息修环境（清脏文件、确认 worktree、确认没有另一进程占着）后再 `resume`。

**预览限制：** 「应用崩溃 / 断网 / 真杀进程」级恢复 **尚未在本项目真机验收**；上表是程序协议层行为。

---

## 5. 验证不过 / 需修改

1. 看 `evidence_dir` 与验收记录，不要改 verifier 证据来「假绿」。
2. Developer：状态机要求 **需修改 → 先回执行中 → 再待验证**（Lite-C L6）。
3. 修完后提交新 `artifact.commit` / 新 attempt，让验证助手重跑 must_run。

---

## 6. 合并被拒 / 后置失败

- 默认 **confirm**：没人确认不会合。
- 冲突、目标基线前进、后置检查失败、重复请求：按 CLI / 报告修，**不要**改成自动推远程。
- `already_merged` 但验收失败或后置缺失：**不能**标已完成（L3 底座）。

详见 `docs/merge-policy.md`。

---

## 7. 静态包自检（发布前）

```bash
cd "${PROJECT_ROOT}/lauren-team-kit"
.venv/bin/python scripts/validate_lite_pack.py
```

期望：`LITE PACK OK`。失败时按打印的缺文件 / 缺角色修，再发版。

完整勾选：[`lite-release-checklist.md`](lite-release-checklist.md)。
