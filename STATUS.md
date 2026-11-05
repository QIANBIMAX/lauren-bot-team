# lauren-bot-team v0.1 进度（2026-11-05 Asia/Shanghai）

公开仓：https://github.com/QIANBIMAX/lauren-bot-team.git（主路径 = clone → OMB Import）

## 下一焦点

**Windows / Linux 原生 kit**（Lite + Team 共用 `lauren-team-kit`）。目标是 Windows 11 x64 与 Ubuntu 24.04 x64，macOS 只做回归。**不是 VibeX 的 Win/Linux，也不是 Full。** 已有 VibeX 材料保持延后，不删。

计划：[`docs/win-linux-development-plan.md`](docs/win-linux-development-plan.md)。

本切片做 W0 doctor、Windows 探活隔离（不再走 `os.kill(pid, 0)`；已退出的进程不算仍在执行），以及 Windows 读改写用的最小 `msvcrt` 字节锁（不再把锁降级成 no-op）。完整 W3、W1 命令契约、W4 Demo、W5–W6、W7 工作台都在后续 PR。`omb_delegate` 真实桥接仍未接通，单独记账，不能写成已可用。

代码、CI、自动测试在仓库里推进。OMB GUI 真机（桌面导入 / 委派 / 重启）留给人工在桌面环境做。没有证据之前，Win/Linux 仍是 **未测**，`platforms: any` 不是发布结论。

更新：2026-11-05 — 焦点从 Lite 收口转到上述原生 kit。Lite-E 程序侧与文档仍以 `f0d1734` 为基线；GUI / 三平台验收没有因此变成已完成。

## 已齐
- **Lite-E / 独立发布**：`docs/lite-release-checklist.md`（对照 §六 1–8）；`docs/lite-failure-recovery.md`；`docs/platforms.md` 矩阵；`lauren-team-kit/scripts/validate_lite_pack.py` + `tests/test_lite_e.py`
- **Lite-D / L7–L8**：test_lite_d；正反样例回执；假断言清理；C2/C3 历史样例标注
- **Lite-C / L5–L6**：真 worktree、原子 RMW、租约取消、resume 对账、Developer 契约
- **Lite-B / L4**：resume → 执行中 统一预算硬门（已 push `b6dea14`）
- **Lite-A / L1–L3 等**：共享底座覆盖（重探针结案）
- **T4–T0** 保留（lessons+E2E / Nancy / handoff / authz / 口径）
- 三角色 pack；kit 状态机 / verify-gate / merge-precheck / 真实本地 merge（confirm）
- Demo C1–C8（C2/C3 kit 脚本 = 历史样例）；OMB 可导入物（文件已备 ≠ GUI 已验收）

## Lite 整包结论
| 段 | 状态 |
|---|---|
| Lite-A～D | 程序侧齐（基线 `f0d1734`） |
| Lite-E | 文档 + 静态校验齐 |
| OMB GUI / 委派 / 重启 | **未验收（预览限制）** |
| Win / Linux | **未测**（原生 kit 已是当前焦点；尚无验收证据） |
| Full | **未批开干** |

## 公开仓
- https://github.com/QIANBIMAX/lauren-bot-team.git
- 本线基线：`f0d1734`（Lite-C/D/E 已在该提交）。Win/Linux 原生 kit 接在其后。

## 延后 / 未验收
- **OMB GUI 真机导入验收**（blocked）
- Windows / Linux 新人验收与 OMB 工作台（**仍未测**；`platforms: any` 非证据；原生 kit 见文首「下一焦点」，不是 VibeX）
- **真 OS 杀进程 / 断网 / 应用重启**级恢复（Windows 探活已改为无副作用查询；受控取消进程树仍未做，不得宣称 OS 杀进程已验收）
- **Full 产品线**（未批开干）

## 原则
装好 OpenMausBot → **自选 Import Lite 或 Team** → 日常 **私聊幕僚长** 派活。未跑过的检查不得标通过。合并默认 confirm。Lite 仍三角直派；Team 默认 engineering_chain。Eng 永不写业务代码。

## 新人只跑 Lite（摘要）
1. `git clone https://github.com/QIANBIMAX/lauren-bot-team.git`
2. OMB Import：`lauren-omb-pack/lauren-lite.botmrr.md`（GUI 真机仍待陛下）
3. 终端最小闭环见 `docs/新手入门.md`；发布勾选见 `docs/lite-release-checklist.md`；故障见 `docs/lite-failure-recovery.md`
4. 静态自检：`lauren-team-kit` 内 `python scripts/validate_lite_pack.py` → `LITE PACK OK`

## kit 测试备注
- 一键测：`python3 -m venv .venv && pip install -e '.[dev]' && pytest -q`
- Lite-E 目标全量 **≥126**（含 test_lite_e）
