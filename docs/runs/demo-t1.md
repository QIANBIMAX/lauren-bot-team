# demo-t1 — Team 双任务烟雾

日期：2026-11-04（Asia/Shanghai）

## 目标

一个 team run 下两条并发子任务：Matcha 指派 Eng stub，Nancy 汇总进度；**不**伪造验证通过。

## 怎么跑

```bash
cd /path/to/lauren-bot-team-v0.1
bash lauren-team-kit/scripts/t1_dual_task_smoke.sh
```

期望：退出码 0；`workspace/runs/demo-t1/team.json` 含 2 个 child、assignments、Nancy summary；`demo-t1-beta` 为「受阻」并有升级记录。

## 证据布局

```
workspace/runs/demo-t1/
  team.json
  nancy/ matcha/ eng/ logs/ summaries/
workspace/runs/demo-t1-alpha/task.json
workspace/runs/demo-t1-beta/task.json
```

## 通过条件

1. `team-create` + 两条 `team-add-task`
2. Matcha `team-assign` → Eng-A / Eng-B
3. Nancy `team-summarize` 写出 summary 文件
4. 子任务 `verification.result` 均非 `pass`（本切片不验真过）
5. kit pytest（含 `test_team.py`）绿

## 未覆盖

Full Eng、OMB GUI、push、真 OS 杀进程恢复。
