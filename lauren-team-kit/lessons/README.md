# lessons store

候选 → 审核 → 发布。**T4**：`review` 批准必须绑定探针证据（`probe_result`/`evidence`，含 probe_id、passed=True、evidence 或 stdout 摘要）；发布后 store JSON 与 rules 文件 `rules_version`/`content_hash` 一致；Eng 用 `lesson-rule-load`、Developer 用 `lesson-rule-receive` 记回执。
