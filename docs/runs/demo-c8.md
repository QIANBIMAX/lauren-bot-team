# demo-c8 运行归档（Lite L5 经验发布）

归档时间：2026-11-04（Asia/Shanghai）  
证据根：`workspace/runs/demo-c8/`  
Store：`lauren-team-kit/lessons/store/`

## 一句话结论

| 能力 | 状态 |
|---|---|
| `lesson-add` → candidates | ✅ |
| `lesson-review approve\|reject` | ✅ |
| `lesson-publish` → store + optional `rules/*.md` + `lessons.published` | ✅ |
| `lesson-show` / `lesson-list` 可读已发布经验 | ✅ |
| 未审核不可发布 | ✅ |
| Team 双任务 | ⏭ 未做 |

## 怎么演示（一段话）

执行 `bash lauren-team-kit/scripts/c8_lessons_smoke.sh`：`lesson-add` 提名 → 未审核时 `lesson-publish` 应失败 → `lesson-review --verdict approve` → `lesson-publish` 写入 `lauren-team-kit/lessons/store/<id>.json`（及规则文件）→ `lesson-show` 能读回摘要与正文。

## 说明

打通候选→审核→发布→可读全路径；C3 的 `lessons.published` 注入演示仍可用，本切片补齐发布流水线。
