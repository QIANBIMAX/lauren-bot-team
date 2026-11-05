# Lite 发布前可勾选清单（对照 lite-audit §六）

> 日期：2026-11-05（Asia/Shanghai）  
> tip 基线（Lite-B L4 已 push）：`b6dea14`；本清单覆盖 **Lite-A～E 程序侧收口**后的发布检查。  
> **规则：未跑过的项不得勾「通过」。** kit 静态度过 ≠ OMB GUI / 三平台实测。

图例：
- `[x]` = 本仓程序/文档侧已具备证据（pytest / 脚本 / 静态校验）
- `[ ]` = 须陛下本机 OMB / 真机 / 跨平台再验
- **预览限制** = 可演示程序闭环，但不得对外宣称该项已验收

---

## 0. 产品线边界（先勾）

- [x] 只宣称 **Lite 三角**（幕僚长 / 云端编程助手 / 验证助手）；不含 Nancy / Matcha / Eng
- [x] 独立导入文件：`lauren-omb-pack/lauren-lite.botmrr.md`（兼容 `team.mausteam.json`）
- [x] 不要求先装 Team；不把 Full 写进 Lite 必装
- [x] 公开样例无私人路径 / 账号 / 密钥（`.env.example` 仅占位）

---

## 1. 干净安装与仅导入 Lite（§六.1）

| 步骤 | 程序/文档 | 陛下真机 |
|---|---|---|
| clone 公开仓 | [x] README / 安装指南 | [ ] 新人机复现 |
| 装 OMB 0.1.140（Mac） | [x] 版本钉死说明 | [ ] 本机 About 核对 |
| Import `lauren-lite.botmrr.md` | [x] 可导入物 + 静态校验脚本 | [ ] **OMB GUI 导入**（**预览限制**） |
| 侧栏出现三角 + 身份明确 | [x] botmrr agents 字段 | [ ] GUI 侧栏目视 |
| 启用 skills / 解冻 routines（按需） | [x] 文档写明默认关 | [ ] 本机点选 |
| 配置模型 / 执行器 / 本机权限 | [x] 安装指南占位 | [ ] 本机实际登录 |

**预览限制：** Mac 0.1.140 **真机 GUI 导入尚未验收**。Import 文件已备 ≠ 已实测导入成功。兜底：手工粘贴 `bots/*.instructions.md`（见新手入门 §6.2）。

最小无 GUI 闭环（可先跑）：

```bash
cd "${PROJECT_ROOT}/demo-app" && bash scripts/smoke.sh   # 期望 SMOKE OK
cd "${PROJECT_ROOT}/lauren-team-kit"
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q                            # 期望全绿
.venv/bin/python scripts/validate_lite_pack.py           # 期望 LITE PACK OK
```

---

## 2. 正常任务闭环（§六.2）

| 项 | kit/文档 | 陛下 OMB 真派 |
|---|---|---|
| 冻结验收 → 实现 → 独立验证 → confirm → 本地集成 → 完成回执 | [x] 状态机 / verify-gate / merge-precheck / merge confirm；Lite-D 真实 commit 闭环测 | [ ] 三角真委派跑通 |
| 默认 `MERGE_POLICY=confirm`；不合公司主仓 | [x] merge-policy.md | [ ] 目视确认 |

**预览限制：** 多助手真委派属延后；终端 / pytest 证据不能冒充 OMB 委派已通。

---

## 3. 失败 → 修复 → 新 attempt 再验（§六.3）

- [x] 失败留证、不覆盖失败记录（C2 / Lite-D / lessons 路径）
- [x] Developer「需修改 → 须先回执行中再待验证」与状态机一致（Lite-C L6）
- [ ] 陛下在 OMB 里走一遍打回返工（**预览限制**）

---

## 4. 反例拒绝（§六.4）

| 反例 | 程序证据 | 真机 |
|---|---|---|
| 伪造执行 / 假 exit_code / 假日志 | [x] L1 / test_t1_authz / verify-gate | [ ] |
| 错 SHA / 旧报告 / 验收变更未重绑 | [x] attempt 绑定 / L2 | [ ] |
| 越权写入 / Developer 自填验收推进完成 | [x] L1 已覆盖 | [ ] |
| 无合并标完成 | [x] 完成门禁 | [ ] |

---

## 5. 合并异常（§六.5）

- [x] 冲突 / 目标基线前进 / 后置失败 / 重复请求 / 不确认 → 不得意外推远程（merge 门 + L3）
- [x] `already_merged` 在 fail / checks 空 / 后置缺失时不可标完成（Lite 重探针 + 底座）
- [ ] 陛下对本机脏工作区 / 分支保护的目视确认（可选）

---

## 6. 预算异常（§六.6）

- [x] tokens / attempts / duration 超限 → 受阻或拒绝进入执行中（Lite-B L4：`resume` 硬门）
- [x] 无 `--allow-raise` 不得抬限
- [ ] 真模型账单级耗尽场景（**未测 / 预览限制**）

恢复步骤见 [`lite-failure-recovery.md`](lite-failure-recovery.md)。

---

## 7. 中断 / 取消 / 重启对账（§六.7）

| 项 | 程序 | 真 OS |
|---|---|---|
| cancel → 已取消 + lease `cancel_requested`（尽力 SIGTERM） | [x] Lite-C | [ ] **真杀进程未验收** |
| resume 前对账：lease / Git HEAD / 脏文件；未知 → 受阻 | [x] Lite-C | [ ] 应用重启真机 |
| 断网 / 应用崩溃恢复 | — | [ ] **未测** |

**预览限制：** 协议层租约 + 尽力信号 ≠ 已证明 OS 级杀进程与断网恢复。

---

## 8. 经验样例与跨平台（§六.8）

- [x] 正反样例 + 后续任务加载回执（T4 + Lite-D L7）
- [x] 中文/空格路径：Mac 主路径文档已覆盖说明
- [x] 跨平台入口优先 `python3 -m lauren_team_kit`（见 platforms.md）
- [ ] Windows 11 新人验收
- [ ] Ubuntu 24.04 新人验收
- [ ] 编码 / 跨平台 shell 差异全矩阵

平台矩阵：[`platforms.md`](platforms.md) · 兼容表：[`compatibility.md`](compatibility.md)。

---

## 汇总：什么可以对外说

| 说法 | 可否 |
|---|---|
| Lite 程序侧 A～E 收口；kit pytest 全绿；干净导入**文档与静态包**齐 | **可以**（以 STATUS / 本清单勾选为准） |
| OMB GUI 真机导入 / 委派 / 重启已验收 | **不可以** |
| Windows / Linux 已支持完成 | **不可以**（`platforms: any` ≠ 实测） |
| Full 已交付 | **不可以** |

发布签字前：勾完「程序」列 → 陛下自测勾「真机」列 → 未勾项写进发布说明的「预览限制」。
