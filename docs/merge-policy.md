# 条件合并策略 v0.1

## 范围
- **仅** Demo 本地集成分支（默认 `demo/integration`）。
- **禁止**自动合并公司主仓 / 生产分支。
- **禁止**默认 push 到任何远程。公开仓 `https://github.com/QIANBIMAX/lauren-bot-team.git` 已存在，但 **kit 的 merge 命令不会 push**；向 GitHub 推送须用户另批，且不由本流程自动执行。

## 开关
| 模式 | 行为 | 一期默认 |
|---|---|---|
| `confirm` | Pass 后落产物+记录，等人确认再合 Demo 分支 | **默认** |
| `auto` | Pass 后自动合入 Demo 本地集成分支（仍不碰主仓、仍不 push） | 可选，需显式配置 |

配置键建议：`MERGE_POLICY=confirm|auto`（任务字段：`merge_policy.mode`）。

## 命令（真实本地合并）

### 1. 初始化集成分支（首次）

基线必须是**明确的干净 commit/分支**，不从脏工作区猜测：

```bash
lauren-team-kit init-integration \
  --worktree workspace/runs/<task>/worktree \
  --baseline <干净基线SHA或main> \
  --branch demo/integration
```

- 分支已存在：报告 tip，**默认不覆盖**。
- `--force`：强制把分支指针移到基线（危险，慎用）。

### 2. 预检（不改 git）

```bash
lauren-team-kit merge-precheck --task-id <id> --root <交付根>
```

### 3. 执行合并

```bash
# 默认 confirm：只打印计划，exit code = 3，不改 git / 不改状态
lauren-team-kit merge --task-id <id> --root <交付根>

# 真正合并
lauren-team-kit merge --task-id <id> --root <交付根> --confirm

# 可选：合并后检查相对 worktree 的文件是否存在
lauren-team-kit merge --task-id <id> --root <交付根> --confirm \
  --post-check-path hello.txt
```

`merge_policy.mode=auto` 时可省略 `--confirm`，但仍会跑全部执行前检查。

#### 退出码

| 码 | 含义 |
|---|---|
| 0 | 合并成功，或已幂等包含（already_merged） |
| 1 | 预检失败 / 冲突 / 合并后检查失败 |
| 2 | 参数用法错误 |
| 3 | 等待确认（未传 `--confirm` 且 mode=confirm） |

#### 行为要点

- 执行前**重新**跑与 `merge-precheck` 同等条件。
- 用 `git rev-parse` 解析短/长 SHA，确认产物与绑定为同一完整提交。
- 入口状态：`待合并`（若为 `验证通过` 会先迁到 `待合并`）。
- 优先快进（`--ff-only`），否则 `--no-ff`；冲突则 `merge --abort`，任务 → `合并失败`，**禁止 force**。
- 成功 → `已完成`，写入 `task.merge` 与 `evidence/merge/report.json`（含前后 SHA、方式）。
- 若 git 已合但后续检查失败 → `合并失败`，并记录真实 git 状态。
- 同一 bound 已在 integration 历史上：不重复合并（幂等）。

## merge-precheck 查什么

`lauren-team-kit merge-precheck` **只做本地预检，不执行 merge**。默认 `confirm` 下，即使预检通过，也仍需 `--confirm` 后再合 Demo 集成分支。

当前 checklist（任一项失败则整体 FAIL）：

| 项 | 含义 |
|---|---|
| `status_in_验证通过_or_待合并` | 任务已过验证门 |
| `merge_policy.mode` | 合并策略字段存在 |
| `commit_present` / `bound_matches_artifact` | 产物 commit 与绑定 commit 一致（允许短/长 SHA） |
| `evidence_dir_exists` | 证据目录在磁盘上 |
| `worktree_is_git_repo` | `worktree.path` 指向可用 git 工作区 |
| `worktree_head_matches_bound` / `verification_not_stale` | `HEAD` 仍等于 bound |
| `worktree_clean` | `git status --porcelain` 为空 |
| `commit_exists` | bound 在该仓库中存在 |
| `integration_branch_exists` | 本地已有 `integration.branch`；预检**不会**自动创建（用 `init-integration`） |
| `ancestor_or_fastforward_possible` | integration 是 bound 祖先，或 `git merge-tree` 干跑无冲突 |

预检通过 ≠ 已合并。真正写入 Demo 集成分支用 `merge --confirm`（且仍不得碰公司主仓、默认不 push）。
