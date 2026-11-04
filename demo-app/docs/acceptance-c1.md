# C1 验收命令草案：任务筛选（主路径）

对齐：`lauren-bot-demo-plan/M0-调研与协议.md` §C1；批件 §六「功能开发」。

## 前置

```bash
cd demo-app
python -m demo_app seed --fixture fixtures/basic.json
# 或：PYTHONPATH=src python -m demo_app seed --fixture fixtures/basic.json
```

## 必做检查（must_run）

```bash
export PYTHONPATH=src
# A1 关键词命中（中文）
python -m demo_app filter --status open --query "发票" | grep -q "发票"

# A2 status 过滤：done 结果不含 open-only-task
python -m demo_app filter --status done | tee /tmp/filter-done.out
! grep -q "open-only-task" /tmp/filter-done.out

# A3 空 query 安全：exit 0 且空列表
python -m demo_app filter --query "" | grep -q '\[\]'

# A4 单元测试
PYTHONPATH=src python -m pytest -q
```

## 烟雾一键

```bash
bash scripts/smoke.sh
```

## Pass 标准

- 全部 must_run 检查真实执行且 exit 0 / 断言命中。
- 任一条未执行 ⇒ 不得标「验证通过」。
