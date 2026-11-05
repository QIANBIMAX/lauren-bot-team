# Lite / Team 部署包装检查

检查日期：2026-11-05。范围：当前仓库的产品入口、导入文件和文档；不代表 OMB 真机验收。

## 独立选择

| 产品线 | BotMRR 文件 | 角色数 | 部署前置 |
|---|---|---|---|
| Lite | `lauren-omb-pack/lauren-lite.botmrr.md` | 3 | OMB、所选引擎及共享 kit / Demo |
| Team | `lauren-omb-pack/team-v0.2/lauren-team.botmrr.md` | 7 | 同上，不需要先导入 Lite |

Team 已包含 chief、developer、verifier 三个基础角色，并增加 Nancy、Matcha 和两个工程 stub。共用内核不等于依赖另一条线的导入配置。Full 尚未交付。

## 已执行检查

- 两个 BotMRR 文件的 YAML 与两个兼容 JSON 文件均可解析。
- Lite 3 个、Team 7 个角色 key 无重复，分别与兼容 JSON 的角色及显示名一致。
- Chief、房间成员、角色引用的 playbook 均在对应包内存在。
- 仓库 Markdown 的相对链接目标存在，Team 文件改名后的引用未发现遗留旧文件名。
- 已移除本次同步重新带入的个人路径与内部同步说明。
- kit CLI 的帮助入口可运行。

## 未验证与限制

- 未在本轮执行 OMB GUI 导入、实际委派、重启或三平台端到端验收。
- Team 工程 bot 仍是 stub，不能据此宣称完整并行开发能力已交付。
- 当前环境缺少 pytest，安装依赖时出现 TLS 连接错误；本轮未重跑完整测试套件。
- 静态文件可解析、引用一致，不代表符合 OMB 当前版本的完整导入 schema；须继续真机验收。
- 规格切换时不应简单叠加导入。自动去重、迁移和升级降级能力尚需专门验证。
