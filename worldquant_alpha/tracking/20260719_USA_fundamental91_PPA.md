## 提交记录 (USA/D1 PPA, fundamental91)

- 数据集: fundamental91 (Quantitative Filings Data) — 自 fnd93 平台切换探索
- 区域/宇宙/延迟: USA/TOP3000/D1
- 中性化/衰减: FAST/2 | 截断: 0.08
- 目标: 找到可提交 alpha 2/2（与 fnd93 合计）
- 硬闸门: 生产相关性必须出且 < 0.7（否则绝不提交）
- 前序: fnd93 最佳 S≈1.55 / F≥1.01 卡住；低饱和 fnd22/25 多为 VECTOR

| # | Alpha ID | Expression | Sharpe | Fitness | ProdCorr | Status |
|---|---|---|---|---|---|---|
| B1 | KPEarW38 | cat11 sent0−sent1 zscore | −0.36 | −0.10 | — | 弱 |
| B1 | P0O9gkNw | cat0_cnt0−cnt1 | 0.02 | 0.00 | — | 无信号 |
| B1 | 58kWgPxM | cat7 sent regression | 0.41 | 0.12 | — | 弱 |
| — | le3XKod8 | fnd22 a8−a9（对照） | 0.61 | 0.27 | — | 弱于 fnd93 |
