## 提交记录 (USA/D1 PPA, fundamental93)

- 数据集: fundamental93 (Earnings Tax Data)
- 区域/宇宙/延迟: USA/TOP3000/D1
- 中性化/衰减: REVERSION_AND_MOMENTUM/0 | 截断: 0.08
- 目标: 找到可提交 alpha 2/2
- 硬闸门: 生产相关性必须出且 < 0.7（否则绝不提交）
- 前序: fnd67/fnd69 信号弱，切换至应计与递延税质量字段

| # | Alpha ID | Expression | Sharpe | Fitness | ProdCorr | Status |
|---|---|---|---|---|---|---|
| B1 | 78nEoJXO | group_rank(ts_regression(exp_t,liab_t,126),ind) | 0.76 | 0.44 | — | 候选 2Y=1.18 |
| B1 | rKPvdALj | group_rank(ts_zscore(dte31/dtl13,66),ind) | 0.62 | 0.30 | — | 观察 |
| B2 | O0xEAznd | signed_power(regression...,3) RAM | 0.78 | 0.42 | — | 2Y=1.36 |
| B3 | rKPv0la9 | 同式 STATISTICAL | 0.65 | 0.20 | — | 2Y=1.82 PASS |
| B4 | xAd05O1g | 同式 SLOW sp3 | 0.36 | 0.08 | — | SLOW 弱 |
| B5 | vRv3ondG | FAST sp3 win126 | 1.02 | 0.51 | — | 2Y=1.71 PASS |
| B6 | GrepNGx3 | FAST sp3 win252 d0 | 1.05 | 0.53 | — | 2Y=1.50 |
| B7 | QP9LRYqw | FAST sp3 win252 decay=2 | 1.06 | 0.54 | — | 2Y=1.52 |
| B8 | le3bnYM8 | expense max−min zscore FAST d2 | 1.09 | 0.54 | — | SubU PASS; 2Y=0.81 FAIL |
| B9 | np8MLz3w | **−**ts_corr(exp_t,liab_t,252) FAST d2 | 1.18 | 0.77 | — | **2Y=1.62 PASS** |
| B9 | O0xElmoJ | −ts_corr win126 FAST d2 | 1.22 | 0.84 | — | 2Y=1.57 差一线 |
| B9 | Vk3gAlpV | max−min zscore win504 sp2 FAST d2 | 1.36 | 0.78 | — | 2Y=1.26 |
| B9 | kqZ2zmKK | max−min sector | 1.11 | 0.55 | — | 观察 |
| B10 | RR1WJQjb | max−min win504 sp1.5 | 1.38 | 0.82 | — | 2Y=1.28 |
| B10 | Xg86jQG5 | max−min win400 sp2 | 1.38 | 0.79 | — | 2Y=1.17 |
| B10 | 78n9kbWx | max−min win630 sp2 FAST d2 | 1.41 | 0.82 | — | 2Y=1.29 |
| B10 | YPgqjKrW | −corr win126 sp2.5 | 1.23 | 0.85 | — | 2Y=1.58 贴线 FAIL |
| B11 | 78n98bxx | max−min win630 sp1.5 | 1.42 | 0.86 | — | 观察 |
| B11 | rKPXKgA1 | max−min + ts_decay_linear5 | 1.43 | 0.84 | — | 观察 |
| B11 | A17K1Zne | max−min bf126 win630 sp2 FAST d2 | 1.53 | 0.93 | — | 2Y=1.77 PASS |
| B12 | vRvgwMm3 | bf150 win630 sp2 | 1.55 | 0.94 | — | 观察 |
| B13 | LLdJVake | bf126 win630 sp1.5 | 1.54 | 0.97 | — | 观察 |
| B13 | **A17K90KQ** | bf150 win630 **sp1.2** FAST d2 | **1.55** | **1.01** | — | **F PASS** 2Y=1.75；差 S+0.03 |
| B13 | MPLmO1A9 | bf150 无 sp | 1.54 | 1.03 | — | F PASS 2Y=1.74 |
| B13 | 3qeLwWE6 | bf150 sp1.5 **decay=3** | 1.55 | 0.98 | — | 2Y=1.76 |
| B13 | vRvgqnoA | bf150 sp1.2 **decay=4** | 1.55 | 1.01 | — | F PASS |
| B14 | 9q70drAo | max−min **STATISTICAL** sp1.2 | **1.59** | 0.78 | — | **S PASS** 2Y=2.35 |
| B14 | **kqZlO50P** | max−min **STATISTICAL** 无sp | **1.61** | 0.81 | — | **S PASS** 2Y=2.38；差 F+0.19 |
| — | SLOW_AND_FAST | 同结构 | ≤0.46 | — | — | 弱于 FAST |

进度快照 (30m tick #11/#12):
- 已提交: 0/2
- **突破**: STATISTICAL 中性化下 Sharpe 过线
  - **kqZlO50P** / 78n9MV1v: **S=1.61 PASS**, F=0.81, 2Y=2.38 PASS, SubU PASS
  - 9q70drAo: S=1.59 PASS, F=0.78, 2Y=2.35
- 仅差 Fitness（需 ≥1.0）；FAST 有 F≥1.0 但 S=1.55
- 阻塞: MCP 断开；下一步扫 STATISTICAL 的 decay/trunc 抬 F
