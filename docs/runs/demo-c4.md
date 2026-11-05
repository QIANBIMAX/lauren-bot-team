# demo-c4 运行归档

公开归档中的个人路径已替换为 PROJECT_ROOT，不改变检查结论。

归档时间：2026-11-04（Asia/Shanghai）  
证据根：`workspace/runs/demo-c4/`（自 原始 macOS 运行环境拷贝；本报告不补写未观察事实）

## 一句话结论

| 能力 | 状态 |
|---|---|
| 委派跑通（幕僚长 → 开发助手 → 验证助手） | ✅ 有证据 |
| 验证通过（独立 must_run × 3，exit 0） | ✅ 有记录 |
| 合并完成（合入 `demo/integration`） | ✅ 2026-11-04 22:33 Asia/Shanghai（ff → 6f21756） |

## 环境

| 项 | 值 | 依据 |
|---|---|---|
| 系统 | macOS 15.7.7 (24G720) arm64 | `uploads/demo-c4-env.txt` / 实测 |
| OpenMausBot | 0.1.140 | 同上 |
| Codex CLI | 0.151.0 | 同上 |
| 引擎/模型具体名 | **缺失**（证据未写清） | — |
| 项目根（运行时） | `${PROJECT_ROOT}` | verifier checks 的 `cwd` |

## 用户输入 / 目标

- 任务编号：`demo-c4`
- 标题：委派连通性探针：`hello.txt=ping`
- 目标：开发助手在任务工作区写出 `hello.txt`，内容为 `ping`；验证助手独立确认。
- 明确不在范围内：业务代码、demo-app 筛选、合入 `demo/integration`、远程 PR。

## 角色与委派

| 协议角色 | OMB 显示名（运行侧） |
|---|---|
| 幕僚长（chief） | Lauren幕僚长 |
| 开发助手（developer） | Lauren开发助手 |
| 验证助手（verifier） | Lauren验证助手 |

`task.json` 的 `roles` 字段写的是协议短名（幕僚长 / 开发助手 / 验证助手）。

## 工作区与版本

| 项 | 值 |
|---|---|
| 工作目录 | `workspace/runs/demo-c4/worktree` |
| 任务分支 | `task/demo-c4` |
| 起始 / 父提交 | `96e054c2ad88faa712353902eb895420b5ff0b23`（main） |
| 产物 / 绑定提交 | `6f2175675755dc6af714ebc585e5e1dfab2998e9`（短：`6f21756`） |
| 集成分支配置 | `integration.branch = demo/integration` |
| 合并策略 | `merge_policy.mode = confirm` |

归档包内 `worktree/` 仅含 `hello.txt`（内容 `ping`），**不含完整 `.git`**。完整 git 历史在 原始运行工作区；本归档以 JSON/日志为准。

commit 说明（`demo-c4-commit-stat.txt`）：

```text
6f21756 feat: add hello.txt probe (demo-c4)
 hello.txt | 1 +
 1 file changed, 1 insertion(+)
```

## 实际检查与证据路径

### 开发自检（不采信为独立验收）

- `developer/self_check.json`（3/3 executed，commit 短 SHA `6f21756`）
- 日志：`developer/C4-FILE-EXISTS.log`、`C4-CONTENT-PING.log`、`C4-SINGLE-FILE.log`
- 另有：`developer/diff.patch`、`developer/notes.md`

验证报告写明：自检「仅作为待核对材料，未采信」。

### 验证助手独立验收

- 主报告：`verifier/verification.json`
  - `result=pass`
  - `ran_at=2026-11-04T21:53:17+08:00`
  - `bound_commit` = `artifact_commit` = `6f2175675755dc6af714ebc585e5e1dfab2998e9`
- 三条 must_run 均 `executed=true` 且 `exit_code=0`：
  - `C4-FILE-EXISTS`
  - `C4-CONTENT-PING`
  - `C4-SINGLE-FILE`
- 命令产出：`verifier/commands/*.out.txt|*.err.txt|*.meta.json`
- 日志：`verifier/*.log`、`verifier/logs/git-corroboration.log`
- 截图：`verifier/screenshots/`（本用例非视觉检查；报告写 none required）

### 顶层空壳说明（如实）

- 顶层 `checks/`、`artifacts/`：**缺失或几乎只有占位**（若目录不存在则标缺失）。真正证据在 `developer/`、`verifier/`。

## 状态机与 history 注意

最终 `task.json.status`：**待合并**（`updated_at=2026-11-04T21:54:16+08:00`）。

history 中「待验证 → 验证通过」与「验证通过 → 待合并」的 `actor` 记为 **`chief`（幕僚长代推进）**，不是验证助手本人点的状态迁移。这是已观察记录，**不改写成未观察事实**。验证助手的独立执行证据以 `verifier/verification.json` 为准。

## 未完成项

1. **真实 merge**：尚未执行合入 `demo/integration`。
2. **`demo/integration` 基线**：原始运行仓库当时 worktree 仅有 `main` @ `96e054c` 与 `task/demo-c4` @ `6f21756`，**尚无** `demo/integration` 分支（需 `lauren-team-kit init-integration` 从明确基线创建后再 `merge --confirm`）。
3. 本归档**不**声称合并完成；也不伪造成功合并证据。

## 可追溯索引

| 产物 | 路径 |
|---|---|
| 任务 | `workspace/runs/demo-c4/task.json` |
| 本报告 | `docs/runs/demo-c4.md` |
| 环境摘录 | 同步时的 `demo-c4-env.txt` / `demo-c4-commit-stat.txt`（uploads） |


## 真实合并（补记）

- 时间：2026-11-04 22:33:37 Asia/Shanghai
- 命令：`init-integration --baseline 96e054c…` → `merge --task-id demo-c4 --confirm --post-check-path hello.txt`
- 方式：快进（ff）
- `demo/integration`：`96e054c` → `6f2175675755dc6af714ebc585e5e1dfab2998e9`
- 任务状态：`待合并` → `已完成`
- 证据：`workspace/runs/demo-c4/merge/report.json`
- 未做：push 远程；未碰公司主仓
- 重复 `merge --confirm`：应幂等成功（`already_merged`）；若 kit 早于幂等修补，可能因 status=已完成 被预检拒绝（已修）
