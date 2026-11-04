# C2 验收：失败返工（预置缺陷 → 失败证据 → 修复 → 再验）

对齐：批件 §六「预置缺陷返工」；M0 C2。

## 与 C1 的关系

- **C1** 使用已修复实现 `filter.py`：空 query → `[]`、exit 0。
- **C2** 不破坏 C1：另加 `filter_buggy.py` 作为 round1 缺陷；默认 CLI 仍走 fixed。
- C1 的 `pytest` / `scripts/smoke.sh` 必须继续全绿。

## 预置缺陷

空关键词 `query=""`（或仅空白）在 buggy 实现中抛未捕获 `ValueError`（CLI 非 0 退出）。

## 两轮命令

### Round1（期望失败，并留下证据）

```bash
cd demo-app
bash scripts/c2_round1_fail.sh
```

- 强制 `DEMO_FILTER_IMPL=buggy`
- 跑空 query 验收：**必须失败**
- 证据写入 `evidence/c2/round1/`
- 脚本语义：成功演示了失败 → **exit 0**；若 buggy 竟通过 → exit 1

### Round2（修复后再验，须全过）

```bash
bash scripts/c2_round2_pass.sh
```

- `DEMO_FILTER_IMPL=fixed`（默认）
- 空 query → `[]` + pytest 相关用例
- 证据写入 `evidence/c2/round2/`

### 一键

```bash
bash scripts/c2_rework_demo.sh
# 或
bash scripts/smoke-c2.sh
```

## Pass 标准

| 轮次 | 必须 | 证据 |
|------|------|------|
| round1 | buggy 空 query 失败（异常 / 非 0） | `evidence/c2/round1/report.json` 含 `"result":"fail"` |
| round2 | fixed 空 query 安全 + pytest 通过 | `evidence/c2/round2/report.json` 含 `"result":"pass"` |
| 回归 | C1 `pytest` + `smoke.sh` 仍绿 | — |

任一轮未真实执行 ⇒ 不得标「验证通过」。两轮 report 均须保留。

## CLI 切换

```bash
# 环境变量
DEMO_FILTER_IMPL=buggy python -m demo_app filter --query ""
DEMO_FILTER_IMPL=fixed python -m demo_app filter --query ""

# 或 flag
python -m demo_app filter --impl buggy --query ""
python -m demo_app filter --impl fixed --query ""
```
