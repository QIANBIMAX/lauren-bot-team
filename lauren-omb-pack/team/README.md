# Team 产品线包（可导入）

与根目录 **Lite** 包平行、对等：要协调 / 调度角色时 **直接 Import 本目录**，不必先装 Lite 再「旁路扩展」。  
**Full** 是未来第三条产品线；本目录为独立 Team 部署包。

本目录一次导入：三角色 + Nancy私人助理 / 工程主管Matcha / 工程bot①②，配合 `lauren-team-kit` 的 Team API。显示名对照 Lauren 组织图。

## 与 Lite 的差异（分流）

| | Lite | Team |
|---|---|---|
| 角色 | 幕僚长 / 云端编程助手 / 验证助手 | 上表三角 + Nancy私人助理 + 工程主管Matcha + 工程bot①② |
| 简单工程 | 幕僚长直派云端编程助手 → 验证助手 | **同左**（可不经 Matcha / Eng） |
| 复杂工程 | （无中间层）直派 developer | **强制** 幕僚长 → Matcha → 工程bot → 云端编程助手 → 验证助手 |
| 中间层价值 | — | Matcha 拆派；Eng **拆解并转交** developer（本期不做业务实现） |
| Nancy | 无 | 进度整本 / 待办 / 阻塞汇总；routines 默认暂停；硬禁验证与代码 |

**复杂判据（任一）**：≥2 文件或跨 ≥2 模块；需 ≥2 子任务；验收矩阵（≥2 条 must_run / 多场景）；协议 / 状态机 / 多角色协作 / 合并策略变更。  
**简单判据（全部）**：单文件或一行级/函数级；不拆子任务；验收 ≤1 条 must_run（或纯文档一句修订）。  
复杂时幕僚长 **硬禁** 直派 developer。细则见 `bots/../bots/chief/instructions.md`（仓内 `lauren-omb-pack/bots/chief/instructions.md`）「复杂度分流」专节。

## 陌生人怎么用（主路径）

```bash
git clone https://github.com/QIANBIMAX/lauren-bot-team.git
cd lauren-bot-team
```

### 优先：BotMRR Markdown（OMB Templates → Import）

1. 打开本机 OpenMausBot（Mac 建议 **0.1.140**）。
2. 走 **Templates → Import**（菜单名以界面为准）。
3. 选择本地文件：
   - `lauren-omb-pack/team/lauren-team.botmrr.md`
4. 或（仓库已公开且该文件已 push 后）粘贴 raw GitHub URL，例如：
   - `https://raw.githubusercontent.com/QIANBIMAX/lauren-bot-team/main/lauren-omb-pack/team/lauren-team.botmrr.md`
   - 分支名以实际默认分支为准。

### 兼容 0.1.140：旧格式 `team.mausteam.json`

若界面更认旧团队模板：

- 文件：`lauren-omb-pack/team/team.mausteam.json`
- 走 Import / 团队模板导入（菜单名以界面为准）。

## 导入后请注意

- **优先私聊幕僚长派活。** Team Room 可导入，但多人同房更耗 token；需要齐人再开群。
- **Skills 默认关**；**routines 保持暂停**——须你手动启用。
- **包内不含任何密钥 / API Key**。
- **幕僚长**先判简单/复杂再分流；闲杂催进度/列阻塞/复述状态按**减负协议**转 **Nancy私人助理**（进度整本 + 待办；陛下问进度先找她）；**工程主管Matcha**只调度复杂工程；**工程bot①/②** 拆解并转交云端编程助手（不做业务实现；③④未建）；验证 / 合并仍走 **验证助手 + 幕僚长**。routines 默认暂停，须手动启用。
- **诚实声明：Mac 0.1.140 真机 GUI 导入验收尚未跑通**，不要对外宣称「已实测导入成功」。

## 终端验收（不依赖 OMB GUI）

先按 [`docs/安装指南.md`](../../docs/安装指南.md) 备好 venv，再：

```bash
# 在仓库根目录
bash lauren-team-kit/scripts/t1_dual_task_smoke.sh
```

期望退出码 0，并看到双任务烟雾成功字样（见 [`docs/runs/demo-t1.md`](../../docs/runs/demo-t1.md)）。CLI 仍用技术名 `Nancy` / `Matcha` / `Eng-A` / `Eng-B`。

## 角色边界（摘要）

| 显示名 | 可做 | 不可做 |
|---|---|---|
| 幕僚长 | 判简单/复杂；简单直派 developer；复杂交 Matcha；减负：进度闲杂转 Nancy；范围、协议、合并请求 | 复杂时直派 developer；亲自干重活；未跑检查写通过；擅自抬预算；用长篇自述进度代替转 Nancy |
| 云端编程助手 | 指定工作区改码与自检 | 直接合并；改 must_run；改验证证据 |
| 验证助手 | 真跑 must_run、留证 | 未跑写 pass |
| Nancy私人助理 | 进度整本、待办勾销/升级、阻塞汇总；接减负转交；说明 routines 启用方式 | 写码、标验证通过、merge、抬预算、擅自开定时、代替 Matcha 派活 |
| 工程主管Matcha | 接复杂工程；排任务、指派/跟踪 Eng | 简单工程硬拆；输出代码字段、标验证通过 |
| 工程bot①/② | 子任务拆解 → 转交云端编程助手；`team-eng-note` | 写业务代码；提交 artifact；标验证；宣称 Full Eng |

## 相关

- 说明：[`docs/team.md`](../../docs/team.md)
- Lite 平行线：[`../lauren-lite.botmrr.md`](../lauren-lite.botmrr.md)、[`../team.mausteam.json`](../team.mausteam.json)
- 清单：`team.manifest.md`
