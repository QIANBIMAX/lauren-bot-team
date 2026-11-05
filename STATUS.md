# lauren-bot-team v0.1 进度（2026-11-05 11:00 Asia/Shanghai）

公开仓：https://github.com/QIANBIMAX/lauren-bot-team.git（主路径 = clone → OMB Import）  

更新：2026-11-05 11:40 Asia/Shanghai — T4：lessons 探针审核/版本一致/加载接收回执 + test_t4_e2e；pytest；t1 标明旧协议。T3/T2/T1 保留。**GUI 真机未完成**。勿 push。勿开 T5。

## 已齐
- **T4**：`lesson-add` 须 scope/probe；`lesson-review` 批准须探针证据；publish 规则文件与 store `rules_version`/`content_hash` 一致；`lesson-rule-load`/`lesson-rule-receive` 回执；`test_t4_e2e.py` + `t4_e2e_smoke.sh`；t1 烟雾仅验旧协议/状态
- **T3**：`team-todo-*` / `team-blocker-resolve`；`summarize_team` 分列 verified/pending_merge/completed；阻塞按 task+reason+open 去重；客观备注「任务待合并，尚未完成」可记；routines:[] 仍须显式创建
- **T2**：`handoff.py` + CLI（decompose/handoff/ack/rework/omb-delegate）；默认 engineering_chain 拒首席绕过；`eng_stubs` 兼容保留；OMB 多助手委派受阻
- **T1**：`authz.Principal` 统一入口；`record-check` 可信/diagnostic 分离 + round_id；`already_merged` 须有效验收；Eng 备注仅 assignee；原子 JSON + 集成分支锁
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
- **Full 产品线**（Eng 在任何产品线都不写业务代码；①②拆解转交；③④未建）
- 真 OS 杀进程级恢复（L3 为协议层模拟）

## 原则
装好 OpenMausBot → **自选 Import Lite 或 Team** → 日常 **私聊幕僚长** 派活（群可选）→ 跑 Demo / t1 smoke。未跑过的检查不得标通过。合并默认 confirm，只针对 Demo 本地分支。Nancy私人助理维护进度整本与待办（减负接单；本包 routines:[] 未预置例程条目，需显式创建后再启用）；工程主管Matcha只调度复杂工程；工程bot①②拆解并转交 developer（不做业务实现）。Team：原图核心链 + 可选捷径；默认 engineering_chain（硬禁默认直派）；可选 fast_path 默认关。Lite 仍三角直派。

## kit 测试备注
- 仓库内 `lauren-team-kit/.venv` 可能因路径改名变成空壳；一键测：`python3 -m venv .venv && pip install -e '.[dev]'`（optional-dependencies.dev 含 pytest/jsonschema）。跨卷 shebang 不强制修。
