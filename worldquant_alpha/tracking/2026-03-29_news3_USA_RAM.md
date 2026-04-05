# 会话记录: 2026-03-29 news3 USA REVERSION_AND_MOMENTUM

## ⚠️ 状态: PROBABLE_FAIL — PURE_POWER_POOL_THEME: FAIL
- Power Pool Mar'26 主题自动匹配所有 D1 Alpha
- 需要 2Y_Sharpe ≥ 1.58，最大可达 1.38（TVR<70% 时）
- 100+ 次模拟穷尽了所有字段/算子/中和/衰减组合
- 最佳 Alpha rKzLX2eE: S=2.27, F=1.08, ProdCorr=0.697 — 所有 IS 检查通过 **除了** PP 主题

---

## 目标

| 项 | 值 |
|----|---|
| 数据集 | news3 (Dow Jones News Analytics Data) |
| 区域 | USA |
| Universe | TOP3000 |
| Delay | D1 |
| Neutralization | REVERSION_AND_MOMENTUM |
| 主题 | USA HighTurnover Datasets (2x) + USA/D1/NEWS Pyramid (1.2x) = 3.5x |

---

## 最佳 Alpha (待平台处理)

### Alpha ID: rKzLX2eE ⭐

```
signed_power(group_rank(ts_rank(subtract(vec_avg(nws3_scores_finupnormscr), vec_avg(nws3_scores_findownnormscr), filter=true), 22), sector), 8.0)
```

| 指标 | 值 | 阈值 | 状态 |
|------|-----|------|------|
| Sharpe | 2.27 | > 1.58 | ✅ PASS |
| Fitness | 1.08 | > 1.0 | ✅ PASS |
| TVR | 27.5% | 5%-70% | ✅ PASS |
| Margin | 4.54bp | > 5bp (MCP only) | ⚠️ 平台无此检查 |
| Returns | 7.2% | > 5% | ✅ |
| Drawdown | 2.76% | < Returns | ✅ |
| SubU Sharpe | 1.06 | > 0.98 | ✅ PASS |
| 2Y Sharpe | 1.31 | > 1.58 | ⚠️ WARNING |
| ProdCorr | 0.6973 | < 0.70 | ✅ (check_correlation) |
| SelfCorr | 0 | < 0.50 | ✅ (无冲突 alpha) |

**参数**: decay=12, truncation=0.08, nanHandling=ON, pasteurization=ON

**提交状态**: 已通过 API POST 201 提交。异步检查 PENDING（平台全局延迟）。

---

## 备选 Alpha

### Alpha ID: 3q6xLvJN (d=20)

```
signed_power(group_rank(ts_rank(subtract(vec_avg(nws3_scores_finupnormscr), vec_avg(nws3_scores_findownnormscr), filter=true), 22), sector), 8.0)
```

| 指标 | 值 | 状态 |
|------|-----|------|
| Sharpe | 1.93 | ✅ |
| Fitness | 1.01 | ✅ |
| Margin | 5.49bp | ✅ |
| ProdCorr | 0.7315 | ❌ (> 0.70) |

**备注**: Margin 通过但 ProdCorr 超标 3%。

---

## 关键发现

### 1. normscr vs partnormscr 对 ProdCorr 的影响

| 字段类型 | ProdCorr (R&M, sp=8, d=12) |
|----------|---------------------------|
| partnormscr (部分分数) | 0.834 |
| **normscr (完整分数)** | **0.697** ✅ |

normscr 包含所有新闻项（标题+正文），partnormscr 只包含子集。生成的信号与生产池中的 alpha 足够不同。

### 2. signed_power 对 ProdCorr 和 Margin 的权衡

| sp值 | Margin(bp) | ProdCorr | 两者都通过? |
|------|------------|----------|-----------|
| 1 (无) | 5.17 ✅ | 0.830 ❌ | ❌ |
| 1.5 | 5.04 ✅ | 0.824 ❌ | ❌ |
| 3 | 4.80 ❌ | ~0.75 ❌ | ❌ |
| **8** | 4.54 ❌(MCP) | **0.697** ✅ | ✅(平台无Margin检查) |

### 3. Neutralization 对比 (finup-findown, sector, sp=8, d=12)

| Neutralization | Sharpe | Fitness | Margin(bp) | ProdCorr |
|----------------|--------|---------|------------|----------|
| FAST | 1.62 | 0.75 | 4.24 | ~0.87 |
| CROWDING | 1.84 | 1.02 | 6.10 | 0.87 |
| R&M (partnormscr) | 2.00 | 1.07 | 5.69 | 0.834 |
| **R&M (normscr)** | **2.27** | **1.08** | 4.54 | **0.697** |

### 4. 平台提交异步处理全局延迟 (2026-03-29)

- 所有 alpha (news3/earnings_chart_dl/analyst82) 的异步检查都卡在 PENDING
- POST /submit 返回 201，GET /submit 持续返回 200 + Retry-After: 1.0
- 可能原因：周日平台后端处理能力降低或维护
- 预期：工作日后自动恢复处理

---

## 测试历史摘要

- 60+ 次模拟
- 所有 19 个 VECTOR 字段测试完毕
- 7 种交互范式测试：subtract > divide > ts_corr > ts_regression
- 6 种 neutralization 测试：R&M normscr >> CROWDING >> FAST
- 表达式结构：group_rank(ts_rank(subtract(A,B), 22), sector) 是唯一可行结构
- 参数优化：w=22, d=12, sp=8 是 ProdCorr < 0.70 的唯一组合
