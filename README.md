# lauren-bot-team v0.1

**新人从这里开始 → [docs/新手入门.md](docs/新手入门.md)**  
（再细一点：[安装指南](docs/安装指南.md) · [使用指南](docs/使用指南.md)）

一期交付：在 **OpenMausBot（OMB）** 上用的队工作台配置 + 独立写好的 **pack / kit / Demo**。  
**不 fork** OMB——本仓是配置包与工程闭环，不是上游源码镜像。

## 组成

| 目录 | 作用 |
|---|---|
| `lauren-omb-pack/` | 可导入 OMB 的三角色团队包（幕僚长 / 开发助手 / 验证助手） |
| `lauren-team-kit/` | 任务协议、状态机、验收门、合并预检与确认后本地合并（工程闭环） |
| `demo-app/` | 跨平台小型任务列表（筛选切片作首条闭环靶） |
| `docs/` | 新手入门、安装、使用、合并策略、兼容表 |
| `m0/` | Mac 实测证据与批件指针 |
| `workspace/runs/` | 运行证据根（内容默认不提交） |

## 角色（一期仅此三角）

- 幕僚长（chief）
- 开发助手（developer）
- 验证助手（verifier）

不含 Nancy / Matcha 等扩展角色。

## 快速路径

1. 安装 OMB（Mac 钉死 **0.1.140**，见 `UPSTREAM.md`）。
2. 按 `lauren-omb-pack/README.md` / 新手入门第 6 节粘贴建三角色（**GUI 正式导入 / 委派 / 重启：尚未在本项目验收通过**）。
3. 不靠 OMB 也能先看懂闭环：在 `demo-app` 跑 C1/C2/C3 烟雾；需要时再跑 `lauren-team-kit` 接线烟雾（命令见新手入门）。

默认合并策略：`MERGE_POLICY=confirm`（见 `docs/merge-policy.md`）。**禁止**自动合公司主仓。

## 证据与公开仓

- OMB 委派探针归档：[`docs/runs/demo-c4.md`](docs/runs/demo-c4.md)（委派与验证有证据；**合并未完成**）
- 公开仓已创建：<https://github.com/QIANBIMAX/lauren-bot-team.git>  
  材料仍可以本文件夹为准；**默认不自动 push**，推送须另批。

## 延后项（诚实）

- OMB GUI 正式导入格式 / 重启恢复的系统验收
- Windows / Linux
- demo-c4 在 Demo 集成分支上的真实合并（需先 `init-integration`）

## 材料路径（附录）

- 本机项目文件夹（F 盘常见）：`/Volumes/F/宁银理财/实习/lauren-bot-team-v0.1/`
