# lauren-omb-pack

OpenMausBot 可导入团队包（数据/配置，非 OMB 源码）。

**零基础请先看：** [docs/新手入门.md](../docs/新手入门.md) · [docs/安装指南.md](../docs/安装指南.md)

## 三角色

| 文件 | 角色 |
|---|---|
| `bots/chief.instructions.md` | 幕僚长 |
| `bots/developer.instructions.md` | 开发助手 |
| `bots/verifier.instructions.md` | 验证助手 |

子目录 `bots/{chief,developer,verifier}/SOUL.md` 为补充人格草案。

## 导入说明（建议操作）

> **诚实声明：三角色在 OMB 里的 GUI 正式导入、委派、重启恢复——尚未在本项目验收通过。**  
> 程序接口写入会被拒，需桌面端操作。下列步骤是建议做法；菜单名若不同，以 OMB 界面为准。

1. 打开本机 OpenMausBot（Mac 建议 **0.1.140**）。
2. 按 Templates / Teams 或桌面「新建 bot」流程，分别粘贴各 `*.instructions.md`（及对应 `SOUL.md`）。
3. Group 成员与串行分工参考 `groups/lauren-core.md`（幕僚长拆任务 → 开发改 → 验证跑门禁；验证未过不得宣称完成）。
4. Skills 文本在 `skills/*/SKILL.md`（受 OMB 数量限制，先放三个）。

即使这一步暂时做不成，仍可用终端跑 `demo-app` 的 C1/C2/C3 演示（见新手入门第 7 节）先看懂闭环。

## 清单对照

见 `team.manifest.md`。兼容与延后项见 `../docs/compatibility.md`。
