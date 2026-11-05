# Team v0.2（Nancy私人助理 / 工程主管Matcha 双任务切片）

日期：2026-11-05（Asia/Shanghai）

## 与一期的关系

| | Lite（默认） | Team v0.2（本切片） |
|---|---|---|
| 路径 | `lauren-omb-pack/` 三角色 | `lauren-omb-pack/team-v0.2/` |
| 角色 | 幕僚长 / 云端编程助手 / 验证助手 | 上表三角 + Nancy私人助理 + 工程主管Matcha + 工程bot①② stub |
| 计划出处 | phase1 M0–M5 / ROLE-RULING | 用户批准的 Lite→Team 计划；**不是**改写一期 M0 已含他们 |

一期 ROLE-RULING 仍禁止把 Nancy私人助理 / 工程主管Matcha **塞进一期三角包**。本切片是**旁路扩展**，文档与目录均标 `team-v0.2`。

显示名对照 Lauren 组织图；CLI / 协议技术名仍为 `Nancy` / `Matcha` / `Eng-A` / `Eng-B`（烟雾脚本勿改）。

## 角色边界

API 按 `team.roles` 解析 actor→role，再走操作白名单硬拦（unknown/越权 → TeamError）；关键词仅作额外防线。

### 幕僚长
- **可**：只派活、给背景、盯质量；范围裁定、协议、状态、合并请求（确认后）
- **不可**：亲自干重活代替工程线；未跑检查写通过；擅自抬预算

### Nancy私人助理（图：Nancy 私人助理 · Coordinator）
- **可**：日常协调；`team-status` / `team-summarize`；列 blockers 并升级幕僚长
- **不可**：写码、写 `artifact`、标验证通过、merge、抬预算

### 工程主管Matcha（图：工程主管 Matcha · Eng Lead）
- **可**：管工程线；`team-add-task` / `team-assign`；跟踪工程bot stub
- **不可**：亲自干重活；输出代码字段（含 `artifact.commit`）、标验证通过、merge

### 工程bot① / 工程bot②
- **本期 stub**：确认指派、占位状态；对应图中工程 bot ①②；**③④先不建**；**不是**四个完整 Eng

### 开发助手 / 验证助手
- 实现与独立验收（Lite 三角一环）；Team 阻塞升级给幕僚长。图中「云端编程助手」是 Cursor 云端代理，**不是**本仓 `developer` 显示名。

## 协议

- Team 文档：`workspace/runs/<team_id>/team.json`（`lauren-team-run/0.2`）
- 子任务仍用 Lite `task.json`；可选字段：
  - `team.team_id` / `team.role` / `team.assignee`
  - `parent_task_id`（可选；本切片双任务通常只用 `team.team_id`）

## CLI

技术名保持英文（与 kit / smoke 一致）：

```bash
cd lauren-bot-team-v0.1
python -m lauren_team_kit team-create --root . --team-id demo-t1 --title "..."
python -m lauren_team_kit team-add-task --root . --team-id demo-t1 --task-id t-a --title "..."
python -m lauren_team_kit team-assign --root . --team-id demo-t1 --task-id t-a --assignee Eng-A
python -m lauren_team_kit team-summarize --root . --team-id demo-t1 --actor Nancy
python -m lauren_team_kit team-status --root . --team-id demo-t1
```

烟雾：`bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`


## OMB 部署

主路径：**GitHub clone → OMB Import Team 版**。

1. `git clone https://github.com/QIANBIMAX/lauren-bot-team.git`
2. OMB（建议 0.1.140）→ Templates → Import：
   - 优先：`lauren-omb-pack/team-v0.2/lauren-team-v0.2.botmrr.md`
   - 兼容：`lauren-omb-pack/team-v0.2/team.mausteam.json`
3. 导入后 skills 默认关、routines 暂停；手动启用；包内无密钥。侧栏应见：幕僚长、开发助手、验证助手、Nancy私人助理、工程主管Matcha、工程bot①、工程bot②。
4. 终端自检：`bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`（先备 venv）。

**诚实：Mac 0.1.140 真机 GUI 导入验收尚未完成。** 细节见 `lauren-omb-pack/team-v0.2/README.md`。请从公开仓库获取团队包。

## 明确未做

- 四个完整 Eng 实现（③④亦未建）
- OMB GUI 正式导入 / 委派验收
- 自动 git push
- 用 Team 替代 Lite 默认路径
