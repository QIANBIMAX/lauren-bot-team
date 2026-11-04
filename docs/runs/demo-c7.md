# demo-c7 运行归档（Lite L4 预算硬门）

归档时间：2026-11-04（Asia/Shanghai）  
证据根：`workspace/runs/demo-c7/`（tokens 场景见 `demo-c7-tokens/`）

## 一句话结论

| 能力 | 状态 |
|---|---|
| `budget.max_attempts` / `max_duration_sec` / `max_tokens` | ✅ schema + CLI `set-budget` |
| 进入 `执行中` 前硬门；超额 → `受阻` + `BUDGET_*` | ✅ |
| `record-tokens` / `check-budget` | ✅ |
| 未跑检查标 pass | ❌ 禁止 |
| Team（Matcha/Nancy） | ⏭ 未做 |

## 怎么演示（一段话）

在交付根执行 `bash lauren-team-kit/scripts/c7_budget_smoke.sh`：给任务 `set-budget --max-attempts 2`，两次进入 `执行中` 后第三次应失败并看到 `BUDGET_ATTEMPTS` 与状态 `受阻`；另建任务 `set-budget --max-tokens 50`，`record-tokens` 累加超过 50 后再 `transition 执行中` 应得到 `BUDGET_TOKENS`。

## 说明

只覆盖 Lite L4 协议层硬门；抬高已有 `max_*` 须 `set-budget --allow-raise`（幕僚长确认）。不引入 Team 角色。
