# lauren-team-kit

工程闭环：任务协议校验、状态机、验收门、合并预检。对标 pstack 系「写验回流」思路，**独立实现**，非 OMB 源码。

权威 schema：`contracts/task-protocol.schema.json`（`schemas/` 可放副本）。

## 安装

```bash
cd lauren-team-kit
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

可选：`pip install -e ".[schema]"` 启用 jsonschema 全量校验。

## CLI

交付根示例：`/workspace/lauren-bot-team-v0.1`。任务落在 `workspace/runs/<task_id>/task.json`。

```bash
ROOT=/workspace/lauren-bot-team-v0.1
KIT=lauren-team-kit/.venv/bin/python

$KIT -m lauren_team_kit create \
  --title "demo filter smoke" --task-id demo-c1 --root "$ROOT"

$KIT -m lauren_team_kit transition \
  --task-id demo-c1 --to 执行中 --actor chief --root "$ROOT"

$KIT -m lauren_team_kit transition \
  --task-id demo-c1 --to 待验证 --actor developer --root "$ROOT"

$KIT -m lauren_team_kit validate --task-id demo-c1 --root "$ROOT"
$KIT -m lauren_team_kit preflight --task-id demo-c1 --root "$ROOT"
$KIT -m lauren_team_kit init-evidence --task-id demo-c1 --root "$ROOT"
```

也可用 `--task-file PATH` 代替 `--task-id` + `--root`。

非法迁移以非零退出码失败并打印允许的出边。

## 包结构

- `state_machine.py` — 合法迁移表
- `protocol.py` — 创建 / 读写 / 结构校验（可选 jsonschema）
- `evidence.py` — `workspace/runs/<id>/{logs,artifacts,checks}/`
- `cli.py` — create / transition / validate / preflight / init-evidence

## 测试

```bash
.venv/bin/python -m pytest tests/ -q
```

## C2 kit 失败返工烟雾

演示：`待验证` 无合格 checks → verify-gate / →验证通过 失败 → `需修改` → 再执行 → record-check → `验证通过`（**不真 merge**）。

```bash
ROOT=/workspace/lauren-bot-team-v0.1
bash lauren-team-kit/scripts/c2_kit_rework_smoke.sh
# 日志：workspace/runs/demo-c2/logs/c2-kit-rework-smoke.log
# 失败证据：workspace/runs/demo-c2/logs/verify-gate-fail.log
# 证据指针：workspace/runs/demo-c2/artifacts/c2/{round1,round2} → demo-app/evidence/c2/
```

## 延后

C3 Demo、OMB 真机导入、真 merge：延后。verify-gate/merge-precheck 已有薄实现 + C2 烟雾脚本。

## C3 经验复用（规则探针）

```bash
cd /workspace/lauren-bot-team-v0.1
K=lauren-team-kit/.venv/bin/python
$K -m lauren_team_kit check-rule --rule lauren-team-kit/rules/filter-empty-query.md --against demo-app             # PASS exit 0
$K -m lauren_team_kit check-rule --rule lauren-team-kit/rules/filter-empty-query.md --against demo-app --impl buggy # FAIL exit 1
$K -m lauren_team_kit preflight --task-id demo-c3 --root . --rules lauren-team-kit/rules/filter-empty-query.md --against demo-app
bash lauren-team-kit/scripts/c3_kit_lesson_smoke.sh   # 拦 buggy→需修改→fixed→验证通过；不真 merge
```
日志：`workspace/runs/demo-c3/logs/{c3-kit-lesson-smoke,check-rule-fail,verify-gate-fail}.log`；种子 `task.seed.json`。
