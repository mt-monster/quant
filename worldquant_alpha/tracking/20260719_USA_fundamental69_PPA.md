## 提交记录 (USA/D1 PPA, fundamental69)

- 数据集: fundamental69 (Quarterly Fundamental Data)
- 区域/宇宙/延迟: USA/TOP3000/D1
- 中性化/衰减: REVERSION_AND_MOMENTUM/0 | 截断: 0.08
- 目标: 找到可提交 alpha 2/2
- 硬闸门: 生产相关性必须出且 < 0.7（否则绝不提交）
- 前序: fundamental67 信号弱(max S=0.60)，已切换至此

| # | Alpha ID | Expression | Sharpe | Fitness | ProdCorr | Status |
|---|---|---|---|---|---|---|
| B1 | bld5jAeN | group_rank(ts_zscore(OCF/Assets,126),ind) RAM | 0.57 | 0.20 | — | 最佳但不足；2Y=1.48 |
| B2 | — | signed_power 增强 | ≤0.24 | — | — | 恶化 |
| B3 | — | SLOW/subindustry/quantile | ≤0.09 | — | — | 弱 → 切换 fnd93 |
