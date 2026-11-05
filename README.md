# lauren-bot-team

**新人从这里开始 → [docs/新手入门.md](docs/新手入门.md)**  
（再细一点：[安装指南](docs/安装指南.md) · [使用指南](docs/使用指南.md)）

一期交付：在 **OpenMausBot（OMB）** 上用的队工作台配置 + 独立写好的 **pack / kit / Demo**。  
**不 fork** OMB——本仓是配置包与工程闭环，不是上游源码镜像。

## 两条产品线（自选其一）

Lite 与 Team 是 **平行、对等的两套 Import 材料**，互不依赖、也不互为「旁路」。挑一条导入即可；**Full（完整工程线）是未来第三条产品线**，本期未交付。

- Lite：独立导入 3 个角色；**三角直派闭环**（幕僚长 → 云端编程助手 → 验证助手）。
- Team：独立导入 7 个角色（三角 + Nancy私人助理 + 工程主管Matcha + 工程bot①②）；**默认 `engineering_chain`**（幕僚长→Matcha→Eng→developer→验证助手）；**可选 `fast_path`**（默认关）。口径：原图核心链 + 可选捷径。无需先导入 Lite。
- 两条线共用 `lauren-team-kit` 与 Demo。这是共享运行依赖，不是部署先后依赖。更换产品线请勿直接叠加导入，以免重复创建基础角色；已有任务和证据应先保留。
- 工程bot①②做**子任务拆解并转交 developer**（Team/Full 均**永不写业务代码**；③④未建）；GUI 导入和三平台尚未完成验收；真 OMB 多助手委派属 T2 预留（勿冒充已通）。

| 产品线 | 适合谁 | BotMRR（优先） | 兼容旧格式 |
|---|---|---|---|
| **Lite** | 三角闭环：派活 → 写码 → 验收 | [`lauren-omb-pack/lauren-lite.botmrr.md`](lauren-omb-pack/lauren-lite.botmrr.md) | [`lauren-omb-pack/team.mausteam.json`](lauren-omb-pack/team.mausteam.json) |
| **Team** | 三角 + 进度协调 + 复杂工程强制中间层（Eng 拆解转交） | [`lauren-omb-pack/team/lauren-team.botmrr.md`](lauren-omb-pack/team/lauren-team.botmrr.md) | [`lauren-omb-pack/team/team.mausteam.json`](lauren-omb-pack/team/team.mausteam.json) |

> Lite 与 Team 的导入文件与目录均使用无版本号命名。Full 尚未交付。

### 怎么用（省 token）

- **优先：私聊幕僚长派活。** 日常开需求、拆任务、盯进度，找 **幕僚长** 单聊即可。
- **群房间可选。** 包里仍带 Lite Room / Team Room，Import 后可以建群，但多人同房会互相读上下文，**更耗 token**。需要齐人讨论时再开群；平时不必默认群聊。

## 组成

| 目录 | 作用 |
|---|---|
| `lauren-omb-pack/` | 可导入 OMB 的团队包（Lite 与 Team 两条平行线） |
| `lauren-team-kit/` | 任务协议、状态机、验收门、合并预检与确认后本地合并（工程闭环） |
| `demo-app/` | 跨平台小型任务列表（筛选切片作首条闭环靶） |
| `docs/` | 新手入门、安装、使用、合并策略、兼容表 |
| `m0/` | Mac 实测证据与批件指针 |
| `workspace/runs/` | 运行证据根（内容默认不提交） |

## 角色（对照 Lauren 组织图）

导入后侧栏显示名尽量与图一致。技术 key / CLI actor 仍可用英文（`nancy` / `Nancy`、`matcha` / `Matcha`、`Eng-A` 等），不影响烟雾脚本。

### Lite（三角）

| 显示名 | key | 干什么 |
|---|---|---|
| **幕僚长** | `chief` | 统一入口：只派活、给背景、盯质量，不亲自干重活；拆任务、推进状态；确认后才请求本地合并 |
| **云端编程助手** | `developer` | 真正写代码：在指定工作区实现与自检，提交待验 |
| **验证助手** | `verifier` | 独立跑 must_run 验收；未跑不得标通过 |

### Team（三角 + 协调 / 调度）

在 Lite 三角之上再含：

| 显示名 | key | 干什么 |
|---|---|---|
| **幕僚长**（Team 下） | `chief` | **默认 engineering_chain** + **减负协议**：硬禁默认直派；可选 fast_path（默认关须记因）；闲杂进度/阻塞转 Nancy |
| **Nancy私人助理** | `nancy` | 图：Nancy 私人助理 · Coordinator。进度整本 / 待办 / 阻塞汇总；减负接单；本包 routines:[] 未预置例程；**硬禁验证、硬禁代码、不擅自开定时** |
| **工程主管Matcha** | `matcha` | 图：工程主管 Matcha · Eng Lead。只接复杂工程；排任务指派 Eng；**不写验证、不写业务代码** |
| **工程bot①** / **工程bot②** | `eng-a` / `eng-b` | 图：工程 bot ①②。**拆解子任务 → 转交云端编程助手**（永不写业务代码）；③④先不建；不是「四个写码 Eng」 |

材料：[`lauren-omb-pack/team/`](lauren-omb-pack/team/) · 说明：[`docs/team.md`](docs/team.md)。

## 快速路径（主路径 = GitHub clone → OMB Import）

1. Clone 公开仓：
   ```bash
   git clone https://github.com/QIANBIMAX/lauren-bot-team.git
   cd lauren-bot-team
   ```
2. 安装 OMB（Mac 钉死 **0.1.140**，见 `UPSTREAM.md`）。
3. 在 OMB 里 **Import 团队**（二选一，平行产品线）：
   - **Lite**：`lauren-omb-pack/lauren-lite.botmrr.md`（兼容：`lauren-omb-pack/team.mausteam.json`）
   - **Team**：`lauren-omb-pack/team/lauren-team.botmrr.md`（兼容：同目录 `team.mausteam.json`）
   - 菜单大致是 Templates → Import；名字以界面为准。详见 [`lauren-omb-pack/README.md`](lauren-omb-pack/README.md)。
4. 导入后：skills 默认关、routines 暂停；须手动启用；**包内无密钥**。日常优先 **私聊幕僚长**；群房间按需再开。
5. 不靠 OMB GUI 也能先看懂闭环：在 `demo-app` 跑 C1/C2/C3；Team 可再跑 `bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`（先按安装指南备 venv）。

> **诚实：Mac 0.1.140 真机 GUI 导入验收尚未完成**，不要宣称「已实测导入成功」。手工粘贴 instructions 仅作兜底（见新手入门第 6 节）。

默认合并策略：`MERGE_POLICY=confirm`（见 `docs/merge-policy.md`）。**禁止**自动合公司主仓。

## 证据与公开仓

- OMB 委派探针归档：[`docs/runs/demo-c4.md`](docs/runs/demo-c4.md)（委派与验证有证据；**合并未完成**）
- 公开仓：<https://github.com/QIANBIMAX/lauren-bot-team.git>  
  获取方式：clone 本仓库。


## Lite 发布与恢复（Lite-E）

- 可勾选清单：[`docs/lite-release-checklist.md`](docs/lite-release-checklist.md)（对照审计 §六；未测项标预览限制）
- 故障恢复：[`docs/lite-failure-recovery.md`](docs/lite-failure-recovery.md)（取消 / 预算受阻 / 缺 jsonschema / resume 对账）
- 平台矩阵：[`docs/platforms.md`](docs/platforms.md)
- 静态包自检：`cd lauren-team-kit && python scripts/validate_lite_pack.py` → `LITE PACK OK`

新人 **只 Import Lite**：[`lauren-omb-pack/lauren-lite.botmrr.md`](lauren-omb-pack/lauren-lite.botmrr.md)（兼容 `team.mausteam.json`）。**OMB GUI 真机导入仍未验收。**

## 延后项（诚实）

- OMB GUI 正式导入 / 委派 / 重启恢复的真机验收
- Windows / Linux
- **Full** 产品线（完整管理面 + Eng③④ 等；Eng 在 Team/Full **均永不写业务代码**，只协调/拆解转交）；Team ①②已是拆解转交中间层；③④未建
- demo-c4 在 Demo 集成分支上的真实合并（需先 `init-integration`）
