# lauren-bot-team v0.1 进度（2026-11-04 23:50 Asia/Shanghai）

权威根：`/workspace/lauren-bot-team-v0.1/` ↔ F：`/Volumes/F/宁银理财/实习/lauren-bot-team-v0.1/`

更新：2026-11-04 23:50 Asia/Shanghai — **Lite L3–L5 已收齐并锁刀**；**Team v0.2（Matcha/Nancy 双任务 + 角色硬拦）已锁刀**。本回合用户已批准同步 F 并 push。

## 已齐
- 三角色 pack（幕僚长 / 开发助手 / 验证助手）instructions + SOUL
- `lauren-team-kit`：状态机 CLI、must_run 硬门、verify-gate / record-check / merge-precheck、`check-rule` / `preflight`
- **验证门加固** + **merge-precheck 真实本地 Git** + **真实本地 merge**（confirm；永不默认 push）
- Demo C1–C5；**Lite L3 demo-c6**（中断恢复）；**L4 demo-c7**（预算硬门）；**L5 demo-c8**（经验审发）
- **Team v0.2 demo-t1**：`team-create` / `team-add-task` / `team-assign` / `team-summarize` / `team-status` / `team-eng-note`；按 `team.roles` 硬拦（Nancy 仅汇总、Matcha 仅加任务/指派、Eng 仅笔记）；pack 在 `lauren-omb-pack/team-v0.2/`（旁路，非一期三角根包）。见 [`docs/team-v0.2.md`](docs/team-v0.2.md)、[`docs/runs/demo-t1.md`](docs/runs/demo-t1.md)
- 核验：kit pytest 72 passed；`c6_resume_smoke` / `c7_budget_smoke` / `c8_lesson_publish_smoke` / `t1_dual_task_smoke` 全绿

## 公开仓
- `https://github.com/QIANBIMAX/lauren-bot-team.git`
- **最新修补以本地/F 盘文件夹为准**；本回合已批准 push

## 延后 / 未验收
- OMB GUI「正式导入格式」与 Windows / Linux 三平台新人验收
- **四个完整 Eng**、Full Team 管理面（本期 Eng 仅为 stub）
- 真 OS 杀进程级恢复（L3 为协议层模拟）
- Lite `transition`/`block` 尚未并入 Team 角色硬拦（不挡本期）

## 原则
装好 OpenMausBot → 导入三角包（Lite 默认）→ 跑 Demo。Team 扩展单独导入 `team-v0.2`。未跑过的检查不得标通过。合并默认 confirm，只针对 Demo 本地分支，不碰公司主仓。Nancy 只汇总、Matcha 不输出代码字段。
