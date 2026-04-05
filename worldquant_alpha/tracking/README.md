# 会话追踪

每次挖掘会话的结果记录在此目录下，按日期命名。

## 文件命名规则

```
YYYY-MM-DD_<dataset>_<region>.md
```

示例：`2026-03-28_analyst15_ASI.md`

## 记录内容

每个会话记录包含：
1. 目标（数据集 / 区域 / 字段对）
2. 批次结果表（所有回测结果）
3. 优化过程（参数调整记录）
4. 最终决策（提交 / PROBABLE_FAIL / INCONCLUSIVE）
5. 经验总结（可复用的发现）

参考 [session_template.md](session_template.md) 的模板格式。
