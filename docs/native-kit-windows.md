# Windows 原生 kit 预览

这是 Windows 11 x64 上的 **kit / CLI** 安装说明，不是 OMB 桌面验收，也不是 VibeX。`windows-latest` 上的 GitHub Actions 只说明托管 runner 跑过测试，**不能**写成 Windows 11 桌面已验收。

## 安装

在仓库根目录：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .\lauren-team-kit
.\.venv\Scripts\python.exe -m lauren_team_kit doctor
```

已有 `.venv` 时不要删掉重来。`bootstrap.ps1` 只是上面几条命令的薄入口。若执行策略拦住脚本，直接跑这些 Python 命令。不要把本机执行策略改成不受限制。

解释器是 `.venv\Scripts\python.exe` 或 `py -3`。验收命令走 argv，不会偷偷改用 Git Bash。

## 第一个场景

```powershell
.\.venv\Scripts\python.exe -m lauren_team_kit.scenarios c1 --root .
```

或 `lauren-team-kit\scripts\run-scenario.ps1 c1`。默认不会 `--force` 覆盖已有演示目录。

## 还没做

- OMB GUI 导入、真实多助手委派、应用重启（W7，人工在桌面做）
- `omb_delegate` 真实桥。doctor 里它是 `not_connected`
- Windows 受控进程树（Job Object）取消。探活不再调用 `os.kill(pid, 0)`；取消仍标 `windows_incomplete`
- 网络盘 / UNC 的一致性

模型 Key 只在你自己的引擎配置里填一次，不要写进仓库或对话。
