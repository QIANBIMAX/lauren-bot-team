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

## 角色

**Lite 默认（一期三角）**

- 幕僚长（chief）
- 开发助手（developer）
- 验证助手（verifier）

**Team v0.2 扩展（可选，旁路）**：Nancy（进度）/ Matcha（工程调度）/ Eng stub — 见 [`lauren-omb-pack/team-v0.2/`](lauren-omb-pack/team-v0.2/) 与 [`docs/team-v0.2.md`](docs/team-v0.2.md)。**不是**一期 M0 三角包的一部分。

## 快速路径（主路径 = GitHub clone → OMB Import）

1. Clone 公开仓：
   ```bash
   git clone https://github.com/QIANBIMAX/lauren-bot-team.git
   cd lauren-bot-team
   ```
2. 安装 OMB（Mac 钉死 **0.1.140**，见 `UPSTREAM.md`）。
3. 在 OMB 里 **Import 团队**：
   - **Team 版（推荐给要 Nancy/Matcha 的人）**：`lauren-omb-pack/team-v0.2/lauren-team-v0.2.botmrr.md`（兼容旧格式：同目录 `team.mausteam.json`）
   - **Lite 三角**：`lauren-omb-pack/lauren-lite.botmrr.md`（兼容：`lauren-omb-pack/team.mausteam.json`）
   - 菜单大致是 Templates → Import；名字以界面为准。详见 [`lauren-omb-pack/README.md`](lauren-omb-pack/README.md)。
4. 导入后：skills 默认关、routines 暂停；须手动启用；**包内无密钥**。
5. 不靠 OMB GUI 也能先看懂闭环：在 `demo-app` 跑 C1/C2/C3；Team 可再跑 `bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`（先按安装指南备 venv）。

> **诚实：Mac 0.1.140 真机 GUI 导入验收尚未完成**，不要宣称「已实测导入成功」。手工粘贴 instructions 仅作兜底（见新手入门第 6 节）。

默认合并策略：`MERGE_POLICY=confirm`（见 `docs/merge-policy.md`）。**禁止**自动合公司主仓。

## 证据与公开仓

- OMB 委派探针归档：[`docs/runs/demo-c4.md`](docs/runs/demo-c4.md)（委派与验证有证据；**合并未完成**）
- 公开仓：<https://github.com/QIANBIMAX/lauren-bot-team.git>  
  **权威获取方式 = clone 本仓**；统一 sync / push 由执行线处理，本棒只写文件、不中途 sync F、不擅自 push。

## 延后项（诚实）

- OMB GUI 正式导入 / 委派 / 重启恢复的真机验收
- Windows / Linux
- 四个完整 Eng / Full OMB GUI（Team 切片仅 stub）
- demo-c4 在 Demo 集成分支上的真实合并（需先 `init-integration`）

## 材料路径（附录）

- F 盘本地拷贝（可选，非主路径）：`/Volumes/F/宁银理财/实习/lauren-bot-team-v0.1/`
