# lauren-bot-team v0.1 进度（2026-11-04 19:48 Asia/Shanghai）

权威根：`/workspace/lauren-bot-team-v0.1/` ↔ F：`/Volumes/F/宁银理财/实习/lauren-bot-team-v0.1/`

## 已齐
- 三角色 pack（幕僚长 / 开发助手 / 验证助手）instructions + SOUL
- `lauren-team-kit`：状态机 CLI、must_run 硬门、verify-gate / record-check / merge-precheck（占位不真 merge）、`check-rule` / `preflight`
- Demo C1 筛选
- Demo C2 失败返工（含 kit 接线冒烟 → 验证通过）
- Demo C3 经验复用（demo-app + kit `c3_kit_lesson_smoke`：注入缺陷→需修改，干净版→验证通过）
- 文档：merge-policy 默认 confirm、compatibility（OMB GUI 项延后）
- **零基础安装使用文档已写（2026-11-04 Asia/Shanghai）**：`docs/新手入门.md`、`docs/安装指南.md`、`docs/使用指南.md`；并更新 `docs/tutorial.md`、根 `README.md`、`lauren-omb-pack/README.md`
- 测试（本机复验 2026-11-04 19:33）：kit pytest **16 passed**、demo pytest **9 passed**；C2/C3 kit smoke 均 OK

## 延后
- OMB 真机导入 / 委派 / 重启
- 公开 GitHub 远程仓
- 真实本地 Git 合并自动化深化
- Windows / Linux

## 原则
装好 OpenMausBot → 导入本包 → 跑 Demo；先把项目搭完再回头真机验证。未跑过的检查不得标通过。
