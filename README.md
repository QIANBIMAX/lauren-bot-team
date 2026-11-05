# lauren-bot-team v0.1

**新人从这里开始 → [docs/新手入门.md](docs/新手入门.md)**  
（再细一点：[安装指南](docs/安装指南.md) · [使用指南](docs/使用指南.md)）

一期交付：在 **OpenMausBot（OMB）** 上用的队工作台配置 + 独立写好的 **pack / kit / Demo**。  
**不 fork** OMB——本仓是配置包与工程闭环，不是上游源码镜像。

## 组成

| 目录 | 作用 |
|---|---|
| `lauren-omb-pack/` | 可导入 OMB 的团队包（Lite 三角 + 可选 Team 扩展） |
| `lauren-team-kit/` | 任务协议、状态机、验收门、合并预检与确认后本地合并（工程闭环） |
| `demo-app/` | 跨平台小型任务列表（筛选切片作首条闭环靶） |
| `docs/` | 新手入门、安装、使用、合并策略、兼容表 |
| `m0/` | Mac 实测证据与批件指针 |
| `workspace/runs/` | 运行证据根（内容默认不提交） |

## 角色（对照 Lauren 组织图）

导入后侧栏显示名尽量与图一致。技术 key / CLI actor 仍可用英文（`nancy` / `Nancy`、`matcha` / `Matcha`、`Eng-A` 等），不影响烟雾脚本。

### Lite 默认（一期三角 · 一个小房间）

| 显示名 | key | 干什么 |
|---|---|---|
| **幕僚长** | `chief` | 统一入口：只派活、给背景、盯质量，不亲自干重活；拆任务、推进状态；确认后才请求本地合并 |
| **云端编程助手** | `developer` | 真正写代码：在指定工作区实现与自检，提交待验（对应组织图「云端编程助手」） |
| **验证助手** | `verifier` | 独立跑 must_run 验收；未跑不得标通过 |

### Team v0.2 扩展（可选大房间 · 旁路，不是改写一期三角包）

在 Lite 三角之上再加：

| 显示名 | key | 干什么 |
|---|---|---|
| **Nancy私人助理** | `nancy` | 图：Nancy 私人助理 · Coordinator。日常协调、待办/日程/进度，减轻主人负担。本期切片：进度汇总与阻塞升级；**不写验证、不写代码** |
| **工程主管Matcha** | `matcha` | 图：工程主管 Matcha · Eng Lead。管工程线、排任务指派工程bot，不亲自干重活；**不写验证、不写业务代码** |
| **工程bot①** / **工程bot②** | `eng-a` / `eng-b` | 图：工程 bot ①②。本期占位 stub，只回状态；**不是** Full Eng ①–④（③④先不建） |

材料：[`lauren-omb-pack/team-v0.2/`](lauren-omb-pack/team-v0.2/) · 说明：[`docs/team-v0.2.md`](docs/team-v0.2.md)。

**怎么选：** 只要三角闭环 → 导入 **Lite**；要进度协调 + 工程调度房间 → 导入 **Team**（含三角 + 上表扩展）。

## 快速路径（主路径 = GitHub clone → OMB Import）

1. Clone 公开仓：
   ```bash
   git clone https://github.com/QIANBIMAX/lauren-bot-team.git
   cd lauren-bot-team
   ```
2. 安装 OMB（Mac 钉死 **0.1.140**，见 `UPSTREAM.md`）。
3. 在 OMB 里 **Import 团队**：
   - **Team 版（推荐给要 Nancy私人助理 / 工程主管Matcha 的人）**：`lauren-omb-pack/team-v0.2/lauren-team-v0.2.botmrr.md`（兼容旧格式：同目录 `team.mausteam.json`）
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
- 四个完整 Eng / Full OMB GUI（Team 切片仅 stub ①②）
- demo-c4 在 Demo 集成分支上的真实合并（需先 `init-integration`）

## 材料路径（附录）

- F 盘本地拷贝（可选，非主路径）：`/Volumes/F/宁银理财/实习/lauren-bot-team-v0.1/`
