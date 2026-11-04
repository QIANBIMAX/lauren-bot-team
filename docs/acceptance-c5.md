# acceptance-c5：filter `--limit` 真实开发闭环

## 规格

| 输入 | 行为 |
|---|---|
| `limit is None` | 不限制（与改前一致） |
| `limit == 0` | 返回 `[]` |
| `limit > 0` | 最多 N 条，保持筛选顺序 |
| `limit < 0` | API：`ValueError`；CLI：exit ≠ 0 |

API：`filter_tasks(..., limit: int | None = None)`  
CLI：`PYTHONPATH=src python -m demo_app filter --limit N`

## 与 C2 的区别（硬性）

| | C2 | C5 |
|---|---|---|
| 缺陷形态 | `--impl buggy` / `filter_buggy.py` 预置开关 | **直接改 `filter.py`** 的受控 off-by-one |
| 修复形态 | 切回 `--impl fixed` | **新 commit 改正** `[:limit]` / `0→[]` |
| 目的 | 预置缺陷演示返工协议 | 证明真实代码修改影响验证与合并 |

**不得**把 C5 描述成 buggy/fixed 开关切换。

## must_run（见 `workspace/runs/demo-c5/task.json`）

1. `C5-LIMIT-ONE`
2. `C5-LIMIT-ZERO`
3. `C5-LIMIT-NEG`
4. `C5-CLI-LIMIT`
5. `C5-PYTEST`
6. `C5-EMPTY-QUERY`

## 两轮

1. Round1：写入受控缺陷 → 验证失败 → `需修改`
2. Round2：真修复新提交 → 验证通过 → `待合并` → `merge --confirm`

## 回归

- C1–C3 脚本与空 query 测试不得被破坏
- `filter_buggy.py` 保持 C2 用途，不承担 C5 limit 语义
