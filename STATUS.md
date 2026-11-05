# lauren-bot-team v0.1 进度（2026-11-05 Asia/Shanghai）

公开仓：https://github.com/QIANBIMAX/lauren-bot-team.git（主路径 = clone → OMB Import）

## 下一焦点

**原生 kit 预览的程序侧（W3–W6）已写进仓库。** Lite 与 Team 仍共用 `lauren-team-kit`。目标平台是 Windows 11 x64 与 Ubuntu 24.04 x64，macOS 做回归。**不是 VibeX，也不是 Full。**

计划：[`docs/win-linux-development-plan.md`](docs/win-linux-development-plan.md)。安装与恢复：[`docs/native-kit-windows.md`](docs/native-kit-windows.md)、[`docs/native-kit-ubuntu.md`](docs/native-kit-ubuntu.md)、[`docs/native-kit-common.md`](docs/native-kit-common.md)。

| 项 | 程序侧 | 还缺什么 |
|---|---|---|
| W0 doctor、Windows 探活不再 `os.kill(pid, 0)` | 已在 `08d0f15` | 两平台归档环境清单仍无；不关闭 M0 |
| W3 锁 / 路径 / common-dir 合并锁 / 只读 Git 诊断 | 已实现，并有测试 | 网络盘未支持。真机文件占用只在单测里模拟重试 |
| W1 argv 验收、同一轮 must_run、旧 shell 不拆词 | 已实现 | Windows 11 桌面尚未手跑 |
| W4 结构化规则探针 + Python 场景 | 已实现。`.sh` / `run-scenario.ps1` 只是入口 | Bash 规则在无 POSIX shell 时是 cannot-run，不是 pass |
| W5 权限不放宽、双进程不丢记录、委派保持 blocked | 测试覆盖 | 无模型场景不是真实助手并发 |
| W6 wheel、运行期 jsonschema、bootstrap | 已实现。CI 会在源码树外装 wheel | 没有 exe/AppImage |
| W2 取消整棵进程树 | POSIX 验收子进程可按进程组停 | **Windows Job Object 仍未做**，取消状态保持 `windows_incomplete` |
| W7 OMB 桌面 | **明确不做** | 导入、真实委派、重启、失败恢复都留给人工桌面 |

`omb_delegate` 仍是 `blocked` / `simulated`，不能写成已接通。`windows-latest` 与 `ubuntu-24.04` 的 CI 不是 Windows 11 / Ubuntu 桌面验收。没有桌面证据之前，这两列仍写 **未测** 或 **CI**，`platforms: any` 不是发布结论。

更新：2026-11-05 — W3–W6 程序侧接在 W0（`08d0f15`）之后。GUI 没有因此变成已验收。

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
| Win / Linux 桌面与 OMB | **未测**（kit 程序侧 W3–W6 已提交；CI ≠ 桌面验收） |
| Full | **未批开干** |

## 公开仓
- https://github.com/QIANBIMAX/lauren-bot-team.git
- 本线基线：`f0d1734`（Lite-C/D/E 已在该提交）。Win/Linux 原生 kit 接在其后。

## 延后 / 未验收
- **OMB GUI 真机导入验收**（blocked）
- Windows / Linux 新人验收与 OMB 工作台（**仍未测**；`platforms: any` 非证据；原生 kit 见文首「下一焦点」，不是 VibeX）
- **真 OS 杀进程 / 断网 / 应用重启**级恢复（Windows 探活已改为无副作用查询；Job Object 取消树仍是 `windows_incomplete`，不得宣称 OS 杀进程已验收）
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
