# 兼容表 · Mac 行（M0）· 2026-11-04 19:05 +0800

主机：MacBook-Air-5.local · Apple 芯片 · OpenMausBot 正在运行（pid 监听 127.0.0.1:8799）

| 项 | 状态 | 证据/路径 | 备注 |
|---|---|---|---|
| OMB 安装与版本 | **已实测** | `/Applications/OpenMausBot.app` = **0.1.140**；DMG `~/Downloads/OpenMausBot-0.1.140-arm64.dmg`；`last-run-version.json` | Bundle ID com.openmausbot.app |
| 数据目录 | **已实测** | `~/.openmausbot`（主数据）；`~/Library/Application Support/openmausbot`（Electron） | |
| 引擎 Codex 安装+认证 | **已实测** | 见 `engine-mac-codex.md` | **锁定此引擎**；Win/Linux=待测 |
| 引擎 Hermes/DeepSeek | **已实测** | engine-status hermes available；已有 bot「DeepSeek助手」 | 非本阶段唯一锁定 |
| 团队创建 bot（propose_team_setup） | **已实测** | MausBot(chief) 曾 `propose_team_setup` 创建 DeepSeek助手；`bots.json` + 消息 digest | 历史会话证据 |
| Lauren 三角色正式导入（幕僚长/开发/验证） | **延后：项目骨架完成后再测** | 本地 HTTP API POST → 403「must come from the desktop app or a paired device」 | 需桌面端操作或配对设备；pack 已备 SOUL 草案 |
| 幕僚长委派（delegate_bot/ask_bot） | **延后：项目骨架完成后再测** | 文档/上游有 agents proxy；本机尚未抓到 Lauren 三角色委派回合 | 待 GUI 一步 |
| 结果/结束/失败读取 | **已实测** | GET `/api/bots` 含 messages；`~/.openmausbot/messages.db` 可读；turnSucceeded / digest 可见 | 失败态样本尚未专门制造 |
| 工作目录访问 | **已实测** | task `cwd` 指向 `~/.openmausbot/task-workspaces/...`；已写入 `m0-cwd-probe.txt` | 主机侧可写；bot 进程内读写待委派任务验证 |
| 重启后任务记录 | **延后：项目骨架完成后再测** | 消息落盘 DB，具备持久化条件 | 未执行退出/重启实验（避免打断陛下当前会话） |
| 条件合并策略文档 | **已写** | `docs/merge-policy.md` | 默认 confirm；禁主仓 |
| Eng 契约硬门 / kit 写验回流 | **需开发** | — | M1+ |
| Windows / Linux OMB | **待测** | — | 无机器则标发布阻塞（计划原文） |

## 接口选择说明（Mac）

| 能力 | 拟用 | 说明 |
|---|---|---|
| 队工作台 | OMB 0.1.140 原生 | 零改上游 |
| 建 bot / 团队 | 桌面端 + Chief `propose_team_setup` | curl API 写入被禁 |
| 读状态/消息 | GET `http://127.0.0.1:8799/api/bots` + messages.db | 只读可用 |
| 委派 | OMB `delegate_bot` / `ask_bot`（待 GUI 实测） | |
| 写码闭环 | lauren-team-kit（后做） | OMB 不管闭环细节 |


## 2026-11-04 19:11 +0800 陛下改口
停 OMB 桌面粘贴建 bot / 委派 / 重启；改仓库骨架落地。上列未完成项标延后。
