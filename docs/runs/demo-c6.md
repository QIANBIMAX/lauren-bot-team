# demo-c6 运行归档（Lite L3 中断恢复）

归档时间：2026-11-04（Asia/Shanghai）  
证据根：`workspace/runs/demo-c6/`

## 一句话结论

| 能力 | 状态 |
|---|---|
| `受阻 → 待执行/执行中/待验证/已取消` 状态机边 | ✅ |
| `block` 写 `blockers[]` + `resume` 锚点 | ✅ |
| `resume` 按 `resume_point` 恢复 | ✅ |
| 已有 `artifact.commit` 与中断 SHA 相同时不要求重提 | ✅ `already_have_artifact=true` |
| 未跑检查标 pass | ❌ 禁止（本 smoke 保持 `executed=false`） |
| Team（Matcha/Nancy） | ⏭ 未做（L4/L5 已另档收齐） |
| OMB GUI | ⏭ 未做 |

## 场景

1. **中断恢复**：`执行中` → `block(KILL)` → `受阻` → `resume` → `执行中`
2. **环境受阻**：`待验证` → `block(MISSING_DEP)` + recovery_hint → `resume` → `待验证`

## 怎么演示（一段话）

在交付根执行 `lauren-team-kit/scripts/c6_resume_smoke.sh`（或手动：`create demo-c6` → `transition 执行中` → `record-check` 写入 artifact.commit → `block --resume-point 执行中` → `resume`，应看到 JSON 里 `already_have_artifact=true` 且 artifact 未被清空；再 `transition 待验证` → `block --resume-point 待验证` → `resume` 回到待验证）。history 里应有 block/resume 记录。

## 说明

只覆盖 Lite L3 协议层恢复。L4/L5 见 demo-c7 / demo-c8。不引入 Team 角色。
