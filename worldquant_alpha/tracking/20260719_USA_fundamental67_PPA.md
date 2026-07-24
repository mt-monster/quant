## 提交记录 (USA/D1 PPA, fundamental67)

- 数据集: fundamental67 (Predictive Sales)
- 区域/宇宙/延迟: USA/TOP3000/D1
- 中性化/衰减: MARKET/4 | 截断: 0.08
- 目标: 找到可提交 alpha 2/2
- 硬闸门: 生产相关性必须出且 < 0.7（否则绝不提交）
- 说明: USA/D1/fundamental 金字塔已点亮(16)；本会话改挖低饱和 fundamental67

| # | Alpha ID | Expression | Sharpe | Fitness | ProdCorr | Status |
|---|---|---|---|---|---|---|

## Batch 结果摘要
- Batch1 (predict_label_hc vs transaction_revenue, MARKET/4): max S=0.60 (9q7Lr9Ex)
- Batch2 (多字段对 P4/P5, SLOW/2): max S=0.28 → 信号弱，切换 fundamental69

| # | Alpha ID | Expression | Sharpe | Fitness | ProdCorr | Status |
|---|---|---|---|---|---|---|
| B1 | 9q7Lr9Ex | group_rank(ts_zscore(divide(hc,rev),66),ind) | 0.60 | 0.30 | — | 弱 |
| B1 | akEqnNVW | rank(ts_zscore(subtract(...))) | -0.07 | -0.01 | — | 弃 |
| B2 | qM6ojmOP | group_rank(ts_regression(pred,ihh,66),ind) | 0.28 | 0.05 | — | 弃 |
