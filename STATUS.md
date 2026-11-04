# lauren-bot-team v0.1 进度（2026-11-04 22:40 Asia/Shanghai）

权威根：`/workspace/lauren-bot-team-v0.1/` ↔ F：`/Volumes/F/宁银理财/实习/lauren-bot-team-v0.1/`

更新：2026-11-04 22:45+ Asia/Shanghai — Lite L2 demo-c5：权威根已备 limit 实现/测试/两轮补丁；F worktree 待真实 commit+验+merge。

## 已齐
- 三角色 pack（幕僚长 / 开发助手 / 验证助手）instructions + SOUL
- `lauren-team-kit`：状态机 CLI、must_run 硬门、verify-gate / record-check / merge-precheck、`check-rule` / `preflight`
- **验证门加固（2026-11-04）**：`artifact.commit` 与 `bound_commit` 必须一致；must_run 的 `exit_code` 必须为 0；check 若带 `result` 则须为 `pass`
- **merge-precheck 真实本地 Git 预检（2026-11-04）**：对照 HEAD/干净工作区/commit 存在/integration 分支/`merge-tree`
- **真实本地 merge（2026-11-04）**：`init-integration` + `merge [--confirm]`；默认 confirm；幂等；冲突 abort；**永不 push**；只碰 Demo 集成分支
- Demo C1 筛选 / C2 失败返工 / C3 经验复用
- **demo-c4 OMB 委派归档**：见 [`docs/runs/demo-c4.md`](docs/runs/demo-c4.md)（委派✅ 验证✅ 合并✅ ff/`6f21756`）
- 文档：merge-policy、compatibility、新手入门 / 安装 / 使用指南

## 公开仓
- 已创建：`https://github.com/QIANBIMAX/lauren-bot-team.git`
- **最新修补以本地/F 盘文件夹为准**；默认**禁止自动 push**；推送须用户明确批准
- 新人仍可只按文件夹部署，不强制从 GitHub 拉

## 延后 / 未验收
- 公开仓 push 待用户明确批准（本地已 commit）
- OMB GUI「正式导入格式」与 Windows / Linux 三平台新人验收
- Lite L2 在 F 盘完成两轮真实 commit/验证/merge 后归档 SHA
- 恢复、预算、经验回写完整闭环（Lite L3–L5）

## 原则
装好 OpenMausBot → 导入本包 → 跑 Demo。未跑过的检查不得标通过。合并默认 confirm，只针对 Demo 本地分支，不碰公司主仓，默认不 push。


## demo-c5 (F 对齐, Asia/Shanghai)
- task/demo-c5 round1 `5e96bd9` → round2 `4bb05f7`
- demo/integration ff → `4bb05f7`
- 证据目录 `workspace/runs/demo-c5/`；推送由人工确认
