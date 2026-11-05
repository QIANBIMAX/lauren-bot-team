# Ubuntu 原生 kit 预览

目标是 Ubuntu 24.04 x64 上的 **kit / CLI**。这不是桌面 OMB 验收。GitHub `ubuntu-24.04` runner 上的 pytest 只覆盖跑到的用例。

## 安装

需要本机已有 `python3`（3.11 或 3.12）和 `git`。不改系统 Python，也不用 root 跑项目。

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git
```

在仓库根目录：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install ./lauren-team-kit
.venv/bin/python -m lauren_team_kit doctor
```

`bootstrap.sh` 是同一组命令。已有 `.venv` 会沿用，不会删掉。

## 第一个场景

```bash
.venv/bin/python -m lauren_team_kit.scenarios c1 --root .
```

Bash 脚本 `lauren-team-kit/scripts/*.sh` 只负责启动这个 Python 运行器。没有 bash 时，带 `requires_bash: true` 的规则探针结果是 cannot-run，不是 pass。

## 还没做

- OMB 桌面导入、真实委派、重启恢复
- `omb_delegate` 真实桥（仍是 blocked / simulated）
- 把某次 CLI 通过写成 Ubuntu 桌面工作台已验收
