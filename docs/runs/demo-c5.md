# demo-c5 运行归档

归档时间：2026-11-04（Asia/Shanghai）  
证据根：`workspace/runs/demo-c5/`

## 一句话结论

| 能力 | 状态 |
|---|---|
| 真实改 `filter.py`（非 `--impl buggy`） | ✅ |
| Round1 验证失败（4 红）→ 需修改 | ✅ `bf1fe4f` |
| Round2 真修复后六条 must_run 全绿 | ✅ `a0134e2` |
| confirm 后合入 `demo/integration`（ff） | ✅ 任务状态 **已完成** |
| OMB GUI 委派本轮 | ⏭ 未驱动；委派通路以 demo-c4 为准 |
| 原始运行环境主仓同步 | ⏳ Mac 离线时在权威根 worktree 完成；待 Mac 上线同步至原始环境 |

## 功能

给筛选增加 `limit`：`None` 不限；`0→[]`；`>0` 截断；`<0` → `ValueError` / CLI exit≠0。

## 受控缺陷（Round1）

- 真改 `filter.py`：`result[:limit+1]`，且 `limit==0` 当作不限制
- **不是**切换 `DEMO_FILTER_IMPL=buggy`

## 版本链（权威根 worktree git）

| 项 | SHA |
|---|---|
| 基线 | `c3359218adaf54a834bf6f0e2acc614ec5455002` |
| Round1（缺陷） | `bf1fe4f8303ebc3d77d53974957b68e9875df243` |
| Round2（修复 / 绑定） | `a0134e2a0f54b749ffa64e20a5b66fc2d06392f5` |
| `demo/integration`（合并后） | `a0134e2a0f54b749ffa64e20a5b66fc2d06392f5`（ff） |

## 检查结果

- Round1：LIMIT-ONE/ZERO/CLI/PYTEST 失败；LIMIT-NEG、EMPTY-QUERY 通过 → `需修改`
- Round2：六条 must_run exit 0；verify-gate PASS；pytest 18 passed
- 证据：`verifier/round1/`、`verifier/round2/`、`merge/report.json`

## 角色交接（task history）

`chief → developer(round1) → verifier(需修改) → developer(round2) → verifier(验证通过) → chief(待合并) → merge(已完成)`

## 说明

本轮闭环在权威根 `workspace/runs/demo-c5/worktree` 实跑（Mac/F 当时离线）。代码与证据已落盘；原始运行环境既有 `task/demo-c5`@`f4ca0e1` 待 Mac 恢复后对齐提交并（如需）再 push。
