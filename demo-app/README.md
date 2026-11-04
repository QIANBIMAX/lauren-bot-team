# demo-app（一期筛选切片）

跨平台小型任务列表。本切片实现按 **status / keyword** 筛选；**空 query 安全返回 `[]`**（fixed）。

## 快速验收（C1）

```bash
PYTHONPATH=src python -m pytest -q
bash scripts/smoke.sh
```

详见 `docs/acceptance-c1.md`。

## C2 失败返工

预置缺陷（`filter_buggy`）→ 验证失败证据 → 修复（`filter.py`）→ 再验通过。两轮 report 均保留。

```bash
bash scripts/c2_rework_demo.sh
# 或
bash scripts/smoke-c2.sh
```

详见 `docs/acceptance-c2.md`。证据：`evidence/c2/round1/`、`evidence/c2/round2/`。

CLI 切换：`DEMO_FILTER_IMPL=buggy|fixed` 或 `filter --impl buggy|fixed`（默认 fixed，不破坏 C1）。

## C3 经验复用

C2 已发布规则 `lauren-team-kit/rules/filter-empty-query.md`。新任务再引入同类空 query 缺陷时，规则探针必须拦住。

```bash
bash scripts/c3_lesson_reuse_demo.sh
# 或
bash scripts/smoke-c3.sh
```

详见 `docs/acceptance-c3.md`。证据：`evidence/c3/blocked/`、`evidence/c3/clean/`。

