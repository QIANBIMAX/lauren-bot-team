# 一期角色口径裁定（指挥官，2026-11-04）

**权威**：项目维护者已批 `m0/phase1-plan-v0.1.md`

| 一期角色 | 英文可对照 | 备注 |
|---|---|---|
| 幕僚长 | Chief | 统一入口与调度 |
| 开发助手 | Developer | 实现与修复 |
| 验证助手 | Verifier | 独立验收 |

**禁止写入一期团队包（三角根包）**：Nancy、Matcha、四个 Eng、专项 bot。

Codex 主稿 `一期技术方案.md` §2 旧「Worker/Nancy」已作废并改正。

---

## Team v0.2 旁路（2026-11-04 续）

用户批准 Lite 收尾后开 **Team 切片**。Nancy / Matcha / Eng stub **仅**落在：

- `lauren-omb-pack/team-v0.2/`
- kit：`team-*` CLI / `lauren_team_kit.team`
- 文档：`docs/team-v0.2.md`、`docs/runs/demo-t1.md`

**不得**把他们写进一期三角包根 manifest，也不得改口称「M0 一开始就含 Nancy/Matcha」。Lite 默认路径仍是三角色。
