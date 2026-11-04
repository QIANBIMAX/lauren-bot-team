# C3 验收：经验复用（同类空 query 必须被拦住）

对齐：批件 §六「经验复用」；M0 切片 C3。

## 与 C1 / C2 的关系

- **C2** 已沉淀规则：`lauren-team-kit/rules/filter-empty-query.md`（空 query → `[]`、exit 0，不得抛异常）。
- **C3** 模拟「新任务再次引入同类缺陷」：用已发布规则探针拦截，不得合并。
- **不破坏** C1/C2：仍用 `filter_buggy` 作注入对照；默认 CLI 仍是 fixed。不改 `evidence/c2/`。

## 故事线

1. 幕僚长把 C2 经验标为 `lessons.published`，新任务 acceptance 注入空 query 硬检查。
2. 开发助手在新任务里又提交了 buggy 等价实现。
3. 验证助手跑规则探针 → **fail** → 状态 **需修改**；不得 `验证通过` / 合并。
4. 对照：同一探针打在 fixed 上必须 **pass**（不得误伤）。

## 规则探针（对齐 `filter-empty-query.md`）

```bash
# CLI：空 query 必须 [] 且 exit 0
DEMO_FILTER_IMPL=<fixed|buggy> python -m demo_app filter --query "" | grep -q '\[\]'

# 库调用安全（对选中 impl）
python -c "from demo_app.<impl> import filter_tasks; assert filter_tasks([], query='') == []"
```

## 两轮命令

### Inject（期望：缺陷被拦住）

```bash
cd demo-app
bash scripts/c3_inject_blocked.sh
```

- 强制 `DEMO_FILTER_IMPL=buggy`
- 规则探针必须失败 → 证据 `evidence/c3/blocked/`，`report.json` 的 `result=blocked`
- 脚本语义：成功演示拦截 → **exit 0**；若 buggy 竟通过探针 → exit 1（规则泄漏）

### Clean（期望：fixed 全过）

```bash
bash scripts/c3_clean_pass.sh
```

- `DEMO_FILTER_IMPL=fixed`
- 探针全过 → `evidence/c3/clean/`，`result=pass`

### 一键

```bash
bash scripts/c3_lesson_reuse_demo.sh
# 或
bash scripts/smoke-c3.sh
```

## Pass 标准

| 轮次 | 必须 | 证据 |
|------|------|------|
| blocked | buggy 被规则探针拦住 | `evidence/c3/blocked/report.json` 含 `"result":"blocked"` |
| clean | fixed 探针通过 | `evidence/c3/clean/report.json` 含 `"result":"pass"` |
| 回归 | C1 `pytest` + C2 `smoke-c2.sh` 仍绿 | — |
| 回流 | 规则文件仍在 `lauren-team-kit/rules/filter-empty-query.md` | — |

任一轮未真实执行 ⇒ 不得标「验证通过」。

## kit 接线（交 Codex）

- `check-rule` / `preflight --rules rules/filter-empty-query.md --against <demo-root>`：对工作区默认实现跑上述探针。
- 新任务 `lessons.published` 引用该规则；acceptance 含 `must_run` 空 query 项。
- 烟雾：`lauren-team-kit/scripts/c3_kit_lesson_smoke.sh`（仿 C2：注入失败→需修改；clean→验证通过；不真 merge）。
