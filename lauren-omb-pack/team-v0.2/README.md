# Team 产品线包（可导入）

与根目录 **Lite** 包平行、对等：要协调 / 调度角色时 **直接 Import 本目录**，不必先装 Lite 再「旁路扩展」。  
**Full** 是未来第三条产品线；本目录名 `team-v0.2/` 为历史切片名，可先保留。

本目录一次导入：三角色 + Nancy私人助理 / 工程主管Matcha / 工程bot①② stub，配合 `lauren-team-kit` 的 Team API。显示名对照 Lauren 组织图。

## 陌生人怎么用（主路径）

```bash
git clone https://github.com/QIANBIMAX/lauren-bot-team.git
cd lauren-bot-team
```

### 优先：BotMRR Markdown（OMB Templates → Import）

1. 打开本机 OpenMausBot（Mac 建议 **0.1.140**）。
2. 走 **Templates → Import**（菜单名以界面为准）。
3. 选择本地文件：
   - `lauren-omb-pack/team-v0.2/lauren-team.botmrr.md`
4. 或（仓库已公开且该文件已 push 后）粘贴 raw GitHub URL，例如：
   - `https://raw.githubusercontent.com/QIANBIMAX/lauren-bot-team/main/lauren-omb-pack/team-v0.2/lauren-team.botmrr.md`
   - 分支名以实际默认分支为准。

### 兼容 0.1.140：旧格式 `team.mausteam.json`

若界面更认旧团队模板：

- 文件：`lauren-omb-pack/team-v0.2/team.mausteam.json`
- 走 Import / 团队模板导入（菜单名以界面为准）。

## 导入后请注意

- **优先私聊幕僚长派活。** Team Room 可导入，但多人同房更耗 token；需要齐人再开群。
- **Skills 默认关**；**routines 保持暂停**——须你手动启用。
- **包内不含任何密钥 / API Key**。
- **Nancy私人助理**做日常协调与进度汇总；**工程主管Matcha**只调度；验证 / 合并仍走 **验证助手 + 幕僚长**；**工程bot①/②** 本期 **stub**（③④未建）。
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
| 幕僚长 | 只派活、给背景、盯质量；范围、协议、状态、合并请求 | 亲自干重活；未跑检查写通过；擅自抬预算 |
| 云端编程助手 | 指定工作区改码与自检 | 直接合并；改 must_run；改验证证据 |
| 验证助手 | 真跑 must_run、留证 | 未跑写 pass |
| Nancy私人助理 | 日常协调、汇总进度、升级阻塞 | 写码、标验证通过、merge |
| 工程主管Matcha | 排任务、指派/跟踪工程bot stub | 亲自干重活；输出代码字段、标验证通过 |
| 工程bot①/② | 占位确认 | 宣称 Full Eng 已交付 |

## 相关

- 说明：[`docs/team-v0.2.md`](../../docs/team-v0.2.md)
- Lite 平行线：[`../lauren-lite.botmrr.md`](../lauren-lite.botmrr.md)、[`../team.mausteam.json`](../team.mausteam.json)
- 清单：`team.manifest.md`
