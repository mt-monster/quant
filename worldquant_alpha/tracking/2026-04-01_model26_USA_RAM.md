# model26 USA RAM Session — 2026-04-01

## Submitted Alpha

### npzgmGbE — ACTIVE / OS ✅
```
signed_power(group_rank(ts_zscore(divide(mdl26_mn_f_rvsnclstr_nlysts_fq1_rnngs, mdl26_stdv_rvsnclstr_nlysts_fq1_rnngs), 88), industry), 2.0)
```

| Parameter | Value |
|-----------|-------|
| Region | USA |
| Universe | TOP3000 |
| Delay | D1 |
| Neutralization | REVERSION_AND_MOMENTUM |
| Decay | 6 |
| Truncation | 0.08 |
| nan_handling | ON |

| Metric | Value |
|--------|-------|
| Sharpe | 1.84 |
| Fitness | 1.12 |
| TVR | 9.0% |
| Margin | 10.4bp |
| Returns | 4.67% |
| Drawdown | 3.83% |
| ProdCorr | 0.7085 |
| SelfCorr | 0.5772 |
| 2Y_Sharpe | 1.73 |
| Sub-Universe Sharpe | 0.84 |

| Check | Result |
|-------|--------|
| LOW_SHARPE | PASS (1.84 > 1.58) |
| LOW_FITNESS | PASS (1.12 > 1.0) |
| LOW_2Y_SHARPE | PASS (1.73 > 1.58) |
| LOW_SUB_UNIVERSE_SHARPE | PASS (0.84 > 0.80) |
| CONCENTRATED_WEIGHT | PASS |
| MATCHES_PYRAMID | PASS (USA/D1/MODEL 1.4x) |

## Rejected Predecessors

| ID | Variant | S | F | ProdCorr | Reason |
|----|---------|---|---|----------|--------|
| JjXpKVJl | ts_rank w=66 | 1.70 | 1.01 | 0.72 | PROD_CORRELATION FAIL |
| j2wZakWO | ts_zscore w=66 | 1.74 | 1.04 | 0.7057 | Not submitted (ProdCorr borderline) |
| LLXpgZA6 | model31 w=88 | 1.84 | 0.94 | — | Silently rejected (F < 1.0) |

## Stronger Variants (Backup / Future)

| Window | ID | S | F | Margin | 2Y_S | Status |
|--------|-----|------|------|--------|------|--------|
| w=110 | E5awLJjP | 1.91 | 1.19 | 11.3bp | 1.83 | Not submitted |
| w=132 | mLz81pP6 | 2.00 | 1.28 | 12.4bp | 2.09 | Not submitted |
| w=176 | VklpexEJ | 2.17 | 1.46 | 14.1bp | 2.24 | Not submitted |
| w=252 | P0lpK5qp | 2.26 | 1.57 | 15.4bp | 2.44 | Not submitted |

## Key Discovery: Window Length vs Performance (model26, ts_zscore)

```
w=66  → S=1.74, F=1.04, Margin=9.2bp
w=88  → S=1.84, F=1.12, Margin=10.4bp  ← SUBMITTED
w=110 → S=1.91, F=1.19, Margin=11.3bp
w=132 → S=2.00, F=1.28, Margin=12.4bp
w=176 → S=2.17, F=1.46, Margin=14.1bp
w=252 → S=2.26, F=1.57, Margin=15.4bp
```
Monotonically increasing. Analyst revision CV signal benefits from longer normalization windows.

## Failed Datasets (RAM-killed)

| Dataset | Category | Best S | Verdict |
|---------|----------|--------|---------|
| other553 (Opinion Mining) | SENTIMENT | 1.07 | RAM killed |
| other566 (Image Prediction) | OTHER | 0.15 | RAM killed (negative Sharpe) |
| other296 (Earnings Call) | OTHER | 0.58 | RAM killed |
| earningscall_sentiment | SENTIMENT | ~0.5 | RAM killed |
| news_transformer_scores | SENTIMENT | ~0.6 | RAM killed |
| model110 | MODEL | ~0.3 | RAM killed |
