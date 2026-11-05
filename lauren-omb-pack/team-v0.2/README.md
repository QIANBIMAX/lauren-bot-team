# Team v0.2 扩展包（可导入）

**不是**一期 M0 三角包的一部分。Lite 默认仍是根目录 `lauren-omb-pack/` 的幕僚长 / 开发助手 / 验证助手。

本目录提供 **Team 版一次导入** 材料（三角色 + Nancy / Matcha / Eng stub），配合 `lauren-team-kit` 的 Team API。

## 陌生人怎么用（主路径）

```bash
git clone https://github.com/QIANBIMAX/lauren-bot-team.git
cd lauren-bot-team
```

### 优先：BotMRR Markdown（OMB Templates → Import）

1. 打开本机 OpenMausBot（Mac 建议 **0.1.140**）。
2. 走 **Templates → Import**（菜单名以界面为准）。
3. 选择本地文件：
   - `lauren-omb-pack/team-v0.2/lauren-team-v0.2.botmrr.md`
4. 或（仓库已公开且该文件已 push 后）粘贴 raw GitHub URL，例如：
   - `https://raw.githubusercontent.com/QIANBIMAX/lauren-bot-team/main/lauren-omb-pack/team-v0.2/lauren-team-v0.2.botmrr.md`
   - 分支名以实际默认分支为准。

### 兼容 0.1.140：旧格式 `team.mausteam.json`

若界面更认旧团队模板：

- 文件：`lauren-omb-pack/team-v0.2/team.mausteam.json`
- 走 Import / 团队模板导入（菜单名以界面为准）。

## 导入后请注意

- **Skills 默认关**；**routines 保持暂停**——须你手动启用。
- **包内不含任何密钥 / API Key**。
- Nancy **只汇总**；Matcha **只调度**；验证 / 合并仍走 **验证助手 + 幕僚长**；Eng-A/B 本期 **stub**。
- **诚实声明：Mac 0.1.140 真机 GUI 导入验收尚未跑通**，不要对外宣称「已实测导入成功」。

## 终端验收（不依赖 OMB GUI）

先按 [`docs/安装指南.md`](../../docs/安装指南.md) 备好 venv，再：

```bash
# 在仓库根目录
bash lauren-team-kit/scripts/t1_dual_task_smoke.sh
```

期望退出码 0，并看到双任务烟雾成功字样（见 [`docs/runs/demo-t1.md`](../../docs/runs/demo-t1.md)）。

## 角色边界（摘要）

| 角色 | 可做 | 不可做 |
|---|---|---|
| 幕僚长 | 范围、协议、状态、合并请求 | 未跑检查写通过；擅自抬预算 |
| 开发助手 | 指定工作区改码与自检 | 直接合并；改 must_run；改验证证据 |
| 验证助手 | 真跑 must_run、留证 | 未跑写 pass |
| Nancy | 汇总进度、升级阻塞 | 写码、标验证通过、merge |
| Matcha | 指派/跟踪 Eng stub | 输出代码字段、标验证通过 |
| Eng-A/B | 占位确认 | 宣称 Full Eng 已交付 |

## 相关

- 说明：[`docs/team-v0.2.md`](../../docs/team-v0.2.md)
- Lite 可导入物：[`../lauren-lite.botmrr.md`](../lauren-lite.botmrr.md)、[`../team.mausteam.json`](../team.mausteam.json)
- 旁路清单：`team.manifest.md`
