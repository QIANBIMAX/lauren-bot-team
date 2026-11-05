# lauren-omb-pack

OpenMausBot **可导入**团队包（数据/配置，非 OMB 源码）。

**零基础请先看：** [docs/新手入门.md](../docs/新手入门.md) · [docs/安装指南.md](../docs/安装指南.md)

主路径：**GitHub clone → OMB Import**（BotMRR / mausteam）。手工粘贴 instructions 仅作兜底。

> **诚实声明：Mac 0.1.140 真机 GUI 导入 / 委派 / 重启恢复——尚未在本项目验收通过。**  
> 下列文件是按上游格式准备的可导入物；菜单名若不同，以 OMB 界面为准。

## 两条平行产品线（自选其一）

Lite 与 Team **对等、独立**：选一条 Import，不要当成「先 Lite 再旁路塞 Team」。**Full** 是未来第三条线。

| 产品线 | BotMRR（优先） | 旧格式兼容 | 角色（侧栏显示名） |
|---|---|---|---|
| **Lite** | [`lauren-lite.botmrr.md`](lauren-lite.botmrr.md) | [`team.mausteam.json`](team.mausteam.json) | 幕僚长 / 云端编程助手 / 验证助手 |
| **Team** | [`team/lauren-team.botmrr.md`](team/lauren-team.botmrr.md) | [`team/team.mausteam.json`](team/team.mausteam.json) | 上表三角 + **Nancy私人助理** / **工程主管Matcha** / **工程bot①②**（默认 engineering_chain；Eng 拆解→转交 developer，永不写业务代码） |

Team 使用无版本号目录与导入文件。详见 [团队说明](team/README.md)。

**分流摘要：** Lite = 三角直派闭环（可直派）。Team = 默认 **engineering_chain**（幕僚长→Matcha→Eng→developer→验证助手）+ 可选 **fast_path**（默认关）。口径：原图核心链 + 可选捷径。Eng 拆解转交、永不写业务代码。Team 另有**减负协议**：催进度/列阻塞/复述状态转 Nancy；本包 routines:[] 未预置例程。

### 联系方式（省 token）

- **优先私聊幕僚长**派活、拆任务、盯进度。
- 包内 Room / 群可导入，但多人同房更耗 token；**需要齐人时再开群**，不必默认群聊。

## 建议导入步骤（摘要）

1. `git clone https://github.com/QIANBIMAX/lauren-bot-team.git`
2. 打开 OpenMausBot（Mac 建议 **0.1.140**）
3. **Templates → Import**（或同等菜单）→ 选上表对应的 `.botmrr.md`；若 0.1.140 更认旧格式，改选 `.mausteam.json`
4. 导入后：skills 默认关、routines 暂停；手动启用；包内无密钥；日常找 **幕僚长** 单聊
5. 终端自检（Team）：`bash lauren-team-kit/scripts/t1_dual_task_smoke.sh`（先按安装指南备 venv）


## Lite 干净导入（Lite-E）

1. clone 本仓后，OMB **Templates → Import** → 选本目录 [`lauren-lite.botmrr.md`](lauren-lite.botmrr.md)（不要选 `team/` 下 Team 包，除非你要 Team）。
2. 导入后手动启用 skills；routines 默认暂停；**包内无密钥**。
3. 日常私聊 **幕僚长**；三角 = 幕僚长 / 云端编程助手 / 验证助手。
4. 终端静态自检（不替代 GUI）：在仓库 `lauren-team-kit` 下执行 `python scripts/validate_lite_pack.py`。
5. 发布勾选 / 故障恢复：[`../docs/lite-release-checklist.md`](../docs/lite-release-checklist.md)、[`../docs/lite-failure-recovery.md`](../docs/lite-failure-recovery.md)。

> **预览限制：** Mac 0.1.140 真机 GUI 导入 / 委派 / 重启 — **尚未验收**。Win/Linux — **未测**。

## 手工粘贴（兜底）

若 Import 不可用，仍可按角色分别粘贴：

| 文件 | 角色 |
|---|---|
| `bots/chief.instructions.md` | 幕僚长 |
| `bots/developer.instructions.md` | 云端编程助手 |
| `bots/verifier.instructions.md` | 验证助手 |

Team 角色说明在 `team/bots/`（含 **Team 专用** chief/developer/verifier + Nancy / Matcha / Eng）。Group 参考 `groups/lauren-core.md` / `team/groups/`（群可选）。

## 清单

- Lite：`team.manifest.md`
- Team：`team/team.manifest.md`
- 兼容与延后：`../docs/compatibility.md`
