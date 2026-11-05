# 原生 kit：公共使用与恢复

Lite 与 Team 共用 `lauren-team-kit`。下面这些现象在 Windows 和 Ubuntu 上含义相同。不要把 Key、账号或个人绝对路径写进仓库。

## 装好之后

```text
python -m lauren_team_kit doctor
python -m lauren_team_kit.scenarios c1 --root <仓库根>
```

`doctor` 只读。它不写 git config、不关 TLS、不提权、不探测 OMB。`omb_delegate` 固定是未接通。

验收优先用 `exec.kind=argv`（参数数组、cwd、env、timeout）。旧的 `command` 字符串类型是 POSIX shell，含 `&&` 时不会拆开猜。Windows 上没有显式 `LAUREN_POSIX_SHELL` 时，shell 验收是启动失败，不会改走 Git Bash。

## 常见恢复

| 现象 | 含义 | 怎么处理 |
|---|---|---|
| doctor 说找不到 git | 本机没有 git | 按平台安装 Git。不要为了过检查去改 `safe.directory=*` |
| `core.autocrlf` 各机不同 | 只记录，不改你的全局配置 | 仓库 `.gitattributes` 约定源文件 LF。内容摘要另有换行归一化算法 |
| 获取文件锁超时 | 另一个进程正拿着同一把锁 | 等它结束。不要删 `.lock` 或 `.git/lauren-merge-*.lock` 去抢正在跑的合并 |
| 替换失败且原文还在 | 目标文件被占用，重试用尽 | 关掉占用该文件的程序后再写。失败不会先把原文件截断 |
| 进程状态未知 | 探活权限不足，或 Windows 取消树还没做 | 保持受阻。未知不是“可以杀”。Windows 取消树仍是 `windows_incomplete` |
| 规则结果 cannot-run | 这条探针需要 Bash，当前环境没有 | 这不是 pass。用结构化探针，或只在 POSIX 上跑 Bash 块 |
| 中文或空格路径 | argv 与 cwd 按字段传递 | 不要把这种路径塞进 `python -c` 的字符串里 |
| 大小写撞目录 | 已有 `Demo` 又要建 `demo` | 报错且不覆盖。换一个任务 id |
| 缺 jsonschema | 旧环境没装运行依赖 | `pip install` 当前 wheel/sdist。正式安装已经带上 jsonschema |
| 场景拒绝覆盖 | 同名演示目录已在 | 换新的 id，或你明确加上 `--force` |

网络盘和 UNC 路径不在本预览的一致性承诺里。

## 发布边界

程序侧做到 W3–W6：锁与路径、验收命令、Python 场景、Lite/Team 回归测试、wheel。W7（OMB 桌面导入、真实委派、重启）仍然未做。Full 与 VibeX 不在这条线里。
