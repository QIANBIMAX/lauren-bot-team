# filter-empty-query

空 query（`""` / 仅空白）筛选必须返回 `[]` 且 exit 0，不得抛异常。

- 规则正文：`lauren-team-kit/rules/filter-empty-query.md`（C2 沉淀，C3 复用）
- 探针：`bash demo-app/scripts/c3_inject_blocked.sh`（再注入必须拦住）
- 对照：`bash demo-app/scripts/c3_clean_pass.sh`
