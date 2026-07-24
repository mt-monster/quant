## 提交记录 (USA/D1, behavioral_signals, Model)

- 数据集: behavioral_signals (Behavioral Finance Signal Factors)
- 区域/宇宙/延迟: USA / TOP3000 / D1
- 金字塔: USA/D1/MODEL ×1.4
- 字段类型: VECTOR → `vec_avg`/`vec_sum` + `ts_backfill(≥120)`
- 设置起点: STATISTICAL, decay=4→30 扫, trunc=0.08
- 经验: reference/global_mining_experience.md；降相关优先 group_rank+STAT
- 吞吐: multi 满 8、串行

| # | Alpha ID | Expression | Sharpe | Fitness | ProdCorr | Status |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | 首批回测中 |
