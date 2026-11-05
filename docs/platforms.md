# 平台基线与支持矩阵

> 日期：2026-11-05（Asia/Shanghai） · Lite-E  
> **只标实做过的。** `platforms: any`（BotMRR 字段）≠ 三平台实测。

## 进行中（仍未测）

Windows 11 x64 与 Ubuntu 24.04 x64 的**原生 kit**已开工（不是 VibeX，也不是 Full）。计划见 [`win-linux-development-plan.md`](win-linux-development-plan.md)。当前仓库里只有 doctor 与 Windows 探活隔离的代码，外加 CI 骨架。

下表在对应证据出现之前保持 **未测**。不得把 `platforms: any`、windows-latest 或某次本机命令写成 Windows 11 / Ubuntu 桌面或 OMB 已验收。

## 矩阵

| 项 | macOS（Apple 芯片） | Windows 11 | Ubuntu 24.04 |
|---|---|---|---|
| OMB 版本钉死 | **0.1.140 已实测** | **未测** | **未测** |
| 引擎 Codex | **0.151.0 已实测锁定** | **未测** | **未测** |
| kit pytest / CLI（Python） | **已测**（开发机） | **未测** | **未测** |
| demo-app 烟雾（Bash） | **已测** | Bash 脚本**不能**冒充 Win 完成 | **未测** |
| OMB GUI Import Lite | **未验收**（文件已备） | **未测** | **未测** |
| 多助手真委派 | **未验收** | **未测** | **未测** |
| 应用重启后记录 | **未验收** | **未测** | **未测** |
| 真 OS 杀进程 / 断网恢复 | **未验收** | **未测** | **未测** |

## 跨平台入口（诚实）

- **优先**：`python3 -m lauren_team_kit …` 或安装后的 `lauren-team-kit` 控制台脚本（venv 内）。
- Windows：用 `py -3` / `python` + `.venv\Scripts\python.exe -m lauren_team_kit`；**尚未在本项目验收**。
- Bash 烟雾（含历史 C2/C3 kit 脚本）仅作 Mac/Linux 辅助；**不得**当作 Windows 支持完成证据。

详见 [`compatibility.md`](compatibility.md)、[`lite-release-checklist.md`](lite-release-checklist.md)。
