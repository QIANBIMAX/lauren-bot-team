# lauren-bot-team v0.1 进度（2026-11-05 09:02 Asia/Shanghai）

公开仓：https://github.com/QIANBIMAX/lauren-bot-team.git（主路径 = clone → OMB Import）  

更新：2026-11-05 09:02 Asia/Shanghai — **Lite / Team 包装为两条平行产品线**；Team 导入文件改名为 `lauren-team.botmrr.md`（去掉文件名版本号）；文档强调 **优先幕僚长单聊**（群可选、更耗 token）。**GUI 真机验收未完成**。Full 为未来第三条线。

## 已齐
- 三角色 pack（幕僚长 / 云端编程助手 / 验证助手）instructions + SOUL
- `lauren-team-kit`：状态机 CLI、must_run 硬门、verify-gate / record-check / merge-precheck、`check-rule` / `preflight`
- **验证门加固** + **merge-precheck 真实本地 Git** + **真实本地 merge**（confirm；永不默认 push）
- Demo C1–C5；**Lite L3 demo-c6**；**L4 demo-c7**；**L5 demo-c8**
- **Team demo-t1**：Team API + 角色硬拦；材料目录 `lauren-omb-pack/team/`（与 Lite 平行）
- **OMB 可导入物（文件已补，≠ GUI 已验收）**：
  - Lite：`lauren-omb-pack/lauren-lite.botmrr.md` + `lauren-omb-pack/team.mausteam.json`
  - Team：`lauren-omb-pack/team/lauren-team.botmrr.md` + `team.mausteam.json`

## 公开仓
- `https://github.com/QIANBIMAX/lauren-bot-team.git`

## 延后 / 未验收
- **OMB GUI 真机导入验收**（BotMRR / mausteam 文件已备，验收未跑）
- Windows / Linux 三平台新人验收
- **Full 产品线**、四个完整 Eng（本期 Eng 仅为 stub）
- 真 OS 杀进程级恢复（L3 为协议层模拟）

## 原则
装好 OpenMausBot → **自选 Import Lite 或 Team** → 日常 **私聊幕僚长** 派活（群可选）→ 跑 Demo / t1 smoke。未跑过的检查不得标通过。合并默认 confirm，只针对 Demo 本地分支。Nancy私人助理只做日常协调/进度汇总；工程主管Matcha不输出代码字段；工程bot①②本期 stub。
