## 提交记录 (USA/D1, Model 数据集)

- 金字塔: USA/D1/MODEL ×1.4
- 吞吐: multi 满 8、串行；EUR `scan_eur_v4` 已减至 1 组

### 各数据集结论
| 数据集 | 最佳结构 | 最佳 S / F | 结论 |
|---|---|---|---|
| forward_beta_risk | residual vol STAT | 0.70 / 0.25 | 放弃 |
| behavioral_signals | visual path INDUSTRY | 1.05 / 0.47 | 搁置 |
| model253 | mdl253_nice | 0.72 / 0.38 | 放弃 |
| model313 | iai/ico | ~0 | 放弃 |
| board_network | centrality | <0.3 | 放弃 |
| expected_move | downward_lognorm | 0.70 | 弱 |
| model144 | mdl144_score 方向不稳 | ~1.2 级 | 次选 |
| **event_stock_model** | **winsorize(group_zscore(add(corp2,earn2))) STAT d8** | **1.43 / 0.64** | **主攻，距 1.58 差 ~0.15** |

### event_stock_model 关键梯队 (TOP3000)
| Alpha ID | 设置 | S | F | 2Y | 备注 |
|---|---|---|---|---|---|
| e7xA3rVJ | STAT/d8 + winsorize std4 | **1.43** | **0.64** | 1.81 | 当前最佳 |
| omg2NYa5 | STAT/d8 group_zscore | 1.42 | 0.64 | 1.81 | |
| 58kVKOPo | STAT/d6 group_zscore | 1.42 | 0.59 | 1.80 | |
| e7xJM0MM | STAT/d6 rank | 1.41 | 0.59 | 1.84 | |

核心表达式:
```
winsorize(group_zscore(ts_zscore(ts_backfill(add(vec_avg(corporate_structure_event_score_2), vec_avg(earnings_financial_event_score_2)), 120), 252), industry), std=4)
```

### 已验证无效杠杆
- ILLIQUID：S 掉到 ~0.95
- INDUSTRY / FAST / CROWDING：均劣于 STAT
- returns 叠加：无增益
- hump：信号抹掉
- model313 / board_network：近似噪声

### 下一步
1. 继续 STAT 微调（decay 10–12、trunc、ts_mean 平滑）冲 S≥1.58
2. 并行扫 `ai_factor_transfer`（alphaCount 低、cov=1.0）
3. 过门槛后查 ProdCorr
