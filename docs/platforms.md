# 平台基线与支持矩阵

> 日期：2026-11-05（Asia/Shanghai）  
> **只标实做过的。** `platforms: any`（BotMRR 字段）≠ 三平台实测。

## 证据怎么读

原生 kit 程序侧（W0 doctor / 探活，以及 W3–W6 锁、验收命令、Python 场景、打包）在仓库里，并由 `.github/workflows/cross-platform.yml` 在 `windows-latest`、`ubuntu-24.04`、`macos-latest` × Python 3.11/3.12 上跑 pytest 和源码树外的 wheel 导入。

- **CI**：该工作流跑过的用例。`windows-latest` ≠ Windows 11 桌面。`ubuntu-24.04` runner ≠ Ubuntu 桌面会话。
- **未测**：还没有对应桌面或真机记录。
- **已测**：开发机或已归档的实跑，表里会写明是哪一种。

计划：[`win-linux-development-plan.md`](win-linux-development-plan.md)。安装：[`native-kit-windows.md`](native-kit-windows.md)、[`native-kit-ubuntu.md`](native-kit-ubuntu.md)、[`native-kit-common.md`](native-kit-common.md)。

## 矩阵

| 项 | macOS（Apple 芯片） | Windows 11 | Ubuntu 24.04 |
|---|---|---|---|
| OMB 版本钉死 | **0.1.140 已实测** | **未测** | **未测** |
| 引擎 Codex | **0.151.0 已实测锁定** | **未测** | **未测** |
| kit pytest / CLI（Python） | 开发机历史已测；CI 作业含 macos-latest | CI 作业含 windows-latest；Windows 11 桌面 **未测** | 本环境 pytest 已跑过 Linux；CI 作业含 ubuntu-24.04；桌面 **未测** |
| Python 场景（C/T 运行器） | CI 作业覆盖；本切片未在 Mac 上重跑 | CI 作业覆盖（不依赖 Git Bash）；桌面 **未测** | 本环境 pytest 已跑过；桌面 **未测** |
| demo-app 历史 Bash 烟雾 | **已测**（旧脚本） | 薄包装不能冒充 Win 完成；无 Bash 时规则是 cannot-run | 结构化探针随 kit pytest；桌面 **未测** |
| OMB GUI Import Lite | **未验收**（文件已备） | **未测** | **未测** |
| 多助手真委派 | **未验收** | **未测** | **未测** |
| 应用重启后记录 | **未验收** | **未测** | **未测** |
| 真 OS 杀进程 / 断网恢复 | **未验收** | **未测** | **未测** |

## 跨平台入口（诚实）

- **优先**：安装后的 `python -m lauren_team_kit`。Windows 用 `py -3` 与 `.venv\Scripts\python.exe`。Ubuntu 用 `python3 -m venv`。
- 场景：`python -m lauren_team_kit.scenarios <c1|c2|c3|c6|c7|c8|t1|t2|t3|t4> --root <仓库根>`。默认不覆盖已有演示。
- Bash 文件只是 POSIX 薄入口。Windows 入口是 `run-scenario.ps1` 或同一条 Python 命令。
- 桌面 OMB 仍 **未测**。`omb_delegate` 仍是 blocked / simulated。

详见 [`compatibility.md`](compatibility.md)、[`lite-release-checklist.md`](lite-release-checklist.md)。
