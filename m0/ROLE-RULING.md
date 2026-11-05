# 一期角色口径裁定（指挥官，2026-11-04）

**权威**：陛下已批 `m0/phase1-plan-v0.1.md`

| 一期角色 | 英文可对照 | 备注 |
|---|---|---|
| 幕僚长 | Chief | 统一入口与调度 |
| 云端编程助手 | Developer | 实现与修复（侧栏显示名） |
| 验证助手 | Verifier | 独立验收 |

**禁止写入一期团队包（三角根包）**：Nancy、Matcha、四个 Eng、专项 bot。

Codex 主稿 `一期技术方案.md` §2 旧「Worker/Nancy」已作废并改正。

---

## Team 产品线（平行线）

Lite 与 Team 是 **两条平行产品线**（Full 为未来第三条）。Nancy / Matcha / Eng stub **仅**落在 Team 材料目录，不写进 Lite 根包：

- `lauren-omb-pack/team/`（导入文件：`lauren-team.botmrr.md`）
- kit：`team-*` CLI / `lauren_team_kit.team`
- 文档：`docs/team.md`、`docs/runs/demo-t1.md`

**不得**把他们写进 Lite 三角根 manifest，也不得改口称「M0 一开始就含 Nancy/Matcha」。用户 Import 时自选 Lite 或 Team。
