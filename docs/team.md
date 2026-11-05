# Team 产品线（按复杂度分流）

日期：2026-11-05（Asia/Shanghai）

## 与 Lite / Full 的关系

| | Lite | Team（本切片） | Full（未来） |
|---|---|---|---|
| 定位 | 平行产品线之一 | 平行产品线之一 | 第三条产品线（未交付） |
| 路径 | `lauren-omb-pack/` 三角色 | `lauren-omb-pack/team/` | 待定 |
| 导入文件 | `lauren-lite.botmrr.md` | `lauren-team.botmrr.md` | 待定 |
| 角色 | 幕僚长 / 云端编程助手 / 验证助手 | 上表三角 + Nancy私人助理 + 工程主管Matcha + 工程bot①② | 含完整 Eng 等（本期不做业务实现于 Eng） |
| 简单工程 | 幕僚长 → developer → 验证助手 | **同左** | — |
| 复杂工程 | （无强制中间层） | **强制** 幕僚长 → Matcha → 工程bot → developer → 验证助手 | — |

Lite 与 Team **对等、自选**，不是「Lite 默认 + Team 旁路塞进一期三角包」。一期 ROLE-RULING 仍要求：**不要把 Nancy / Matcha 写进 Lite 根包**；Team 有自己的目录与导入文件。

显示名对照 Lauren 组织图；CLI / 协议技术名仍为 `Nancy` / `Matcha` / `Eng-A` / `Eng-B`（烟雾脚本勿改）。

## 复杂度分流

### 复杂（满足任一）
- 预估改动 ≥2 个文件，或跨 ≥2 模块/包
- 需要拆成 ≥2 个子任务才能验收
- 有验收矩阵（≥2 条 must_run / 多场景）
- 涉及协议 / 状态机 / 多角色协作 / 合并策略变更

### 简单（须全部满足）
- 单文件或极局部一行级 / 函数级改动
- 不需拆子任务
- 验收 ≤1 条清晰 must_run（或纯文档一句修订）

复杂时幕僚长 **硬禁** 直派云端编程助手；须 `team-create`（若尚无）→ 交 Matcha。简单仍须验证助手真跑 must_run。细则：`lauren-omb-pack/bots/chief/instructions.md`「复杂度分流」。

## 怎么用（省 token）

- **优先私聊幕僚长**派活（由幕僚长判分流）。
- Team Room 可 Import，但多人同房更耗 token；**需要齐人再开群**。

## 角色边界

API 按 `team.roles` 解析 actor→role，再走操作白名单硬拦（unknown/越权 → TeamError）；关键词仅作额外防线。

### 幕僚长
- **可**：判简单/复杂；简单直派 developer；复杂交 Matcha；减负协议下把进度闲杂转 Nancy；范围裁定、协议、合并请求（确认后）
- **不可**：复杂时直派 developer；亲自干重活代替工程线；未跑检查写通过；擅自抬预算；长篇自述进度代替转 Nancy

### Nancy私人助理（图：Nancy 私人助理 · Coordinator）
- **可**：维护进度整本（任务 id / 状态 / 负责人 / 阻塞 / 更新时间）；承接口头待办并勾销/升级；`team-status` / `team-summarize`；接幕僚长减负转交（催进度/列阻塞/复述状态）；说明 OMB routines 默认暂停及如何手动启用（不擅自开定时）
- **不可**：写码、写 `artifact`、标验证通过、merge、抬预算、擅自启用 routines、代替 Matcha 工程派活
- 复杂 Team 跑起来后，陛下问进度先找她

### 工程主管Matcha（图：工程主管 Matcha · Eng Lead）
- **可**：接复杂工程；`team-add-task` / `team-assign`；跟踪 Eng「拆解→转交 developer」；误派简单则退回幕僚长
- **不可**：输出代码字段（含 `artifact.commit`）、标验证通过、merge；把简单工程硬拆复杂

### 工程bot① / 工程bot②
- **必须**：子任务拆解（目标/范围/验收要点/worktree 注意）→ 转交云端编程助手（开工包带 parent team/task）
- **本期不做业务实现**；可用 `team-eng-note`；③④先不建；**不是**四个完整 Full Eng

### 云端编程助手 / 验证助手
- 实现与独立验收；Team 阻塞升级给幕僚长。

## 减负协议（与分流并行）

闲杂催进度 / 列阻塞 / 复述状态 → 幕僚长转 **Nancy**；工程派活仍 **Matcha**。不削弱复杂度分流。routines 默认暂停。

## 协议

- Team 文档：`workspace/runs/<team_id>/team.json`（`lauren-team-run/0.2`）
- 子任务仍用 Lite `task.json`；可选字段：
  - `team.team_id` / `team.role` / `team.assignee`
  - `parent_task_id`（Eng 转交 developer 时应注明）

## CLI

技术名保持英文（与 kit / smoke 一致）：

```bash
cd lauren-bot-team
python -m lauren_team_kit team-create --root . --team-id demo-t1 --title "..."
python -m lauren_team_kit team-add-task --root . --team-id demo-t1 --task-id t-a --title "..."
python -m lauren_team_kit team-assign --root . --team-id demo-t1 --task-id t-a --assignee Eng-A
python -m lauren_team_kit team-summarize --root . --team-id demo-t1 --actor Nancy
python -m lauren_team_kit team-status --root . --team-id demo-t1
```

烟雾：`bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`

## OMB 部署

主路径：**GitHub clone → OMB Import Team 产品线**。

1. `git clone https://github.com/QIANBIMAX/lauren-bot-team.git`
2. OMB（建议 0.1.140）→ Templates → Import：
   - 优先：`lauren-omb-pack/team/lauren-team.botmrr.md`
   - 兼容：`lauren-omb-pack/team/team.mausteam.json`
3. 导入后 skills 默认关、routines 暂停；手动启用；包内无密钥。侧栏应见：幕僚长、云端编程助手、验证助手、Nancy私人助理、工程主管Matcha、工程bot①、工程bot②。日常优先 **私聊幕僚长**。
4. 终端自检：`bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`（先备 venv）。

**诚实：Mac 0.1.140 真机 GUI 导入验收尚未完成。** 细节见 `lauren-omb-pack/team/README.md`。请从公开仓库获取团队包。

## 明确未做

- **Full** 产品线与四个完整写码 Eng（③④亦未建；①②本期拆解转交、不做业务实现）
- OMB GUI 正式导入 / 委派验收
- 自动 git push
- 把 Team 角色塞进 Lite 根包（保持两条平行线）
