# lauren-bot-team v0.1 进度（2026-11-05 14:30 Asia/Shanghai）

公开仓：https://github.com/QIANBIMAX/lauren-bot-team.git（主路径 = clone → OMB Import）  

更新：2026-11-05 14:30 Asia/Shanghai — **Lite-E（独立发布）已补**（落 F，**勿 push**）。干净导入路径文档交叉一致；可勾选发布清单；三平台矩阵诚实；故障恢复文档；静态包校验脚本。**Lite 整包程序侧收口；GUI / 三平台待陛下。**

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
| Lite-A～D | 程序侧齐（含未提交 C+D+E 工作树） |
| Lite-E | 文档 + 静态校验齐 |
| OMB GUI / 委派 / 重启 | **未验收（预览限制）** |
| Win / Linux | **未测** |
| Full | **未批开干** |

## 公开仓
- https://github.com/QIANBIMAX/lauren-bot-team.git
- tip（已 push）：`b6dea14`；本机工作树含 Lite-C/D/E **未提交**

## 延后 / 未验收
- **OMB GUI 真机导入验收**（blocked）
- Windows / Linux 三平台新人验收（platforms:any 非证据）
- **真 OS 杀进程 / 断网 / 应用重启**级恢复
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
