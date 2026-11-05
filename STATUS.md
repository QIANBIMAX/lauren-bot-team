# lauren-bot-team v0.1 进度（2026-11-05 08:10 Asia/Shanghai）

权威根：`/workspace/lauren-bot-team-v0.1/`  
公开仓：https://github.com/QIANBIMAX/lauren-bot-team.git（主路径 = clone → OMB Import）  
F 盘：`/Volumes/F/宁银理财/实习/lauren-bot-team-v0.1/`（附录；**统一 sync/push 由执行线**，本棒只写文件、中途不 sync F）

更新：2026-11-05 08:10 Asia/Shanghai — **正在补 OMB 可导入物**（Team + Lite 的 BotMRR / mausteam）；**GUI 真机验收未完成**。Lite L3–L5 与 Team v0.2 kit 侧此前已锁刀。

## 已齐
- 三角色 pack（幕僚长 / 开发助手 / 验证助手）instructions + SOUL
- `lauren-team-kit`：状态机 CLI、must_run 硬门、verify-gate / record-check / merge-precheck、`check-rule` / `preflight`
- **验证门加固** + **merge-precheck 真实本地 Git** + **真实本地 merge**（confirm；永不默认 push）
- Demo C1–C5；**Lite L3 demo-c6**；**L4 demo-c7**；**L5 demo-c8**
- **Team v0.2 demo-t1**：Team API + 角色硬拦；pack 旁路目录 `lauren-omb-pack/team-v0.2/`
- **OMB 可导入物（文件已补，≠ GUI 已验收）**：
  - Team：`lauren-omb-pack/team-v0.2/lauren-team-v0.2.botmrr.md` + `team.mausteam.json`
  - Lite：`lauren-omb-pack/lauren-lite.botmrr.md` + `lauren-omb-pack/team.mausteam.json`

## 公开仓
- `https://github.com/QIANBIMAX/lauren-bot-team.git`
- 统一 sync F / push：执行线；本棒只写权威树文件

## 延后 / 未验收
- **OMB GUI 真机导入验收**（BotMRR / mausteam 文件已备，验收未跑）
- Windows / Linux 三平台新人验收
- **四个完整 Eng**、Full Team 管理面（本期 Eng 仅为 stub）
- 真 OS 杀进程级恢复（L3 为协议层模拟）

## 原则
装好 OpenMausBot → **Import** Team 或 Lite 可导入物 → 跑 Demo / t1 smoke。未跑过的检查不得标通过。合并默认 confirm，只针对 Demo 本地分支。Nancy 只汇总、Matcha 不输出代码字段。
