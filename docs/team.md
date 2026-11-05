# Team 产品线（原图核心链 + 可选捷径）

日期：2026-11-05（Asia/Shanghai）

## 与 Lite / Full 的关系

| | Lite | Team（本切片） | Full（未来） |
|---|---|---|---|
| 定位 | 平行产品线之一 | 平行产品线之一 | 第三条产品线（未交付） |
| 路径 | `lauren-omb-pack/` 三角色 | `lauren-omb-pack/team/` | 待定 |
| 导入文件 | `lauren-lite.botmrr.md` | `lauren-team.botmrr.md` | 待定 |
| 角色 | 幕僚长 / 云端编程助手 / 验证助手 | 上表三角 + Nancy私人助理 + 工程主管Matcha + 工程bot①② | Eng③④+外围等；**Eng 永不写业务代码** |
| 默认工程路由 | 幕僚长 → developer → 验证助手（Lite 直派） | **`engineering_chain`（默认）**：幕僚长 → Matcha → Eng → developer → 验证助手 | — |
| 可选捷径 | — | **`fast_path`（默认关）**：幕僚长 → developer → 验证助手，须记因 | — |

Lite 与 Team **对等、自选**，不是「Lite 默认 + Team 旁路塞进一期三角包」。一期 ROLE-RULING 仍要求：**不要把 Nancy / Matcha 写进 Lite 根包**；Team 有自己的目录与导入文件。

显示名对照 Lauren 组织图；CLI / 协议技术名仍为 `Nancy` / `Matcha` / `Eng-A` / `Eng-B`（烟雾脚本勿改）。

## 路由策略（engineering_chain + 可选 fast_path）

口径：**原图核心链 + 可选捷径**。开发/修复默认走 `engineering_chain`；`fast_path` 默认关。普通问答/纯状态查询不进工程链。

| 策略 | 默认 | 路径 |
|---|---|---|
| `engineering_chain` | **开** | 幕僚长 → Matcha → Eng → developer → 验证助手 |
| `fast_path` | **关** | 幕僚长 → developer → 验证助手（仅严格小任务且须记因） |

`fast_path` 启用须全部满足：单文件或一行级/函数级；不拆子任务；验收 ≤1 条 must_run（或纯文档一句修订）；并在 history/备注写明原因。不得为迁就捷径删减必做检查。

细则：**Team** 幕僚长指令 `lauren-omb-pack/team/bots/chief/instructions.md`（勿用 Lite 根包指令代替）。

## 怎么用（省 token）

- **优先私聊幕僚长**派活（由幕僚长判分流）。
- Team Room 可 Import，但多人同房更耗 token；**需要齐人再开群**。

## 角色边界

API 按 `team.roles` 解析 actor→role，再走操作白名单硬拦（unknown/越权 → TeamError）；关键词仅作额外防线。

### 幕僚长
- **可**：默认 engineering_chain 交 Matcha；例外启用 fast_path（记因）；减负协议下把进度闲杂转 Nancy；范围裁定、协议、合并请求（确认后）
- **不可**：默认直派 developer；未记因启用 fast_path；亲自干重活代替工程线；未跑检查写通过；擅自抬预算；长篇自述进度代替转 Nancy

### Nancy私人助理（图：Nancy 私人助理 · Coordinator）
- **可**：维护进度整本（任务 id / 状态 / 负责人 / 阻塞 / 更新时间）；承接口头待办并勾销/升级；`team-status` / `team-summarize`；接幕僚长减负转交（催进度/列阻塞/复述状态）；说明本包 `routines: []` 未预置例程及如何在陛下显式要求后新建启用（不擅自开）
- **不可**：写码、写 `artifact`、标验证通过、merge、抬预算、擅自启用 routines、代替 Matcha 工程派活
- 复杂 Team 跑起来后，陛下问进度先找她

### 工程主管Matcha（图：工程主管 Matcha · Eng Lead）
- **可**：调度 engineering_chain；`team-add-task` / `team-assign`；跟踪 Eng「拆解→转交 developer」；fast_path 条件不满足则退回默认链
- **不可**：输出代码字段（含 `artifact.commit`）、标验证通过、merge；代替 Eng 写业务代码

### 工程bot① / 工程bot②
- **必须**：子任务拆解（目标/范围/验收要点/worktree 注意）→ 转交云端编程助手（开工包：**顶层** `parent_task_id` + `team.team_id`；先替换占位验收）
- **永不写业务代码**（Team/Full 皆然）；可用 `team-eng-note`；③④先不建；不是「四个写码 Eng」

### 云端编程助手 / 验证助手
- 实现与独立验收；Team 阻塞升级给幕僚长。

## 减负协议（与分流并行）

闲杂催进度 / 列阻塞 / 复述状态 → 幕僚长转 **Nancy**；工程派活仍 **Matcha**。不削弱默认 engineering_chain。本包 routines:[] 未预置例程。

## 协议

- Team 文档：`workspace/runs/<team_id>/team.json`（`lauren-team-run/0.2`）
- 子任务仍用 `task.json`；可选字段：
  - `team.team_id` / `team.role` / `team.assignee`（**勿**把 `parent_task_id` 放进 `team`）
  - **顶层** `parent_task_id`（Eng 转交 developer 时应注明）
  - 子任务创建时验收为中性占位（`must_run=false`）；Eng 转交前须填写真实验收

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
3. 导入后 skills 默认关；本包 routines:[] 未预置例程（须陛下显式创建后再启用）；包内无密钥。侧栏应见：幕僚长、云端编程助手、验证助手、Nancy私人助理、工程主管Matcha、工程bot①、工程bot②。日常优先 **私聊幕僚长**。Team 三角请用 `team/bots/chief|developer|verifier/` 指令。
4. 终端自检：`bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`（先备 venv）。

**诚实：Mac 0.1.140 真机 GUI 导入验收尚未完成。** 细节见 `lauren-omb-pack/team/README.md`。请从公开仓库获取团队包。

## 明确未做

- **Full** 产品线（Eng 永不写业务代码；③④未建；①②已是拆解转交中间层）
- OMB GUI 正式导入 / 委派验收
- 自动 git push
- 把 Team 角色塞进 Lite 根包（保持两条平行线）
