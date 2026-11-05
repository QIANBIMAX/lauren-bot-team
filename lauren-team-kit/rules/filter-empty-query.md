# 规则：空 query 必须安全

**来源**：Demo C2 失败返工（预置缺陷 → 修复）。**C3 经验复用**：新任务再引入同类缺陷时必须被本规则拦住。

## 硬约束

- 筛选 API / CLI：当 `query` 为 `""` 或仅空白时，**不得抛异常**，必须返回空列表 `[]`，进程 exit 0。
- `query=None` 表示不做关键词过滤（可仅按 status）。
- 默认实现：`demo_app.filter.filter_tasks`。
- 故意缺陷对照：`demo_app.filter_buggy`（仅 C2/C3 教学注入，不得作为默认）。

## 验收探针

requires_bash: true

```bash
DEMO_FILTER_IMPL=fixed python -m demo_app filter --query "" | grep -q '\[\]'
PYTHONPATH=src python -c "from demo_app.filter import filter_tasks; assert filter_tasks([], query='') == []"
PYTHONPATH=src python -m pytest -q tests/test_filter_empty_query.py
```

Bash 探针只在 POSIX bash 可用时执行。Windows 不把 Git Bash 当成已支持；不能跑时结果是 cannot_run，不是 pass。默认验收走下面的结构化探针。

## 结构化探针

```json
{
  "requires_bash": false,
  "probes": [
    {
      "id": "cli-empty",
      "argv": ["{python}", "-m", "demo_app", "filter", "--query", ""],
      "env": {"PYTHONPATH": "{pythonpath}", "DEMO_FILTER_IMPL": "{impl}"},
      "expect_exit": 0,
      "expect_stdout_contains": "[]"
    },
    {
      "id": "lib-empty",
      "argv": ["{python}", "-c", "import importlib, os; name = 'demo_app.filter_buggy' if os.environ.get('DEMO_FILTER_IMPL') == 'buggy' else 'demo_app.filter'; mod = importlib.import_module(name); assert mod.filter_tasks([], query='') == []"],
      "env": {"PYTHONPATH": "{pythonpath}", "DEMO_FILTER_IMPL": "{impl}"},
      "expect_exit": 0
    },
    {
      "id": "pytest-empty",
      "argv": ["{python}", "-m", "pytest", "-q", "tests/test_filter_empty_query.py"],
      "env": {"PYTHONPATH": "{pythonpath}", "DEMO_FILTER_IMPL": "{impl}"},
      "expect_exit": 0
    }
  ]
}
```

## 回流落点

- 规则文件：本文件（kit `rules/`）
- C2 证据：`demo-app/evidence/c2/round{1,2}/`
- C3 证据：`demo-app/evidence/c3/blocked/`（注入被拦）、`demo-app/evidence/c3/clean/`（fixed 对照）
- C3 脚本：`demo-app/scripts/c3_lesson_reuse_demo.sh`
