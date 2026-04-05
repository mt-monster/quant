# fundamental17 USA RAM — O0mJ7KKq (ACTIVE)

## Alpha Details
- **Alpha ID**: O0mJ7KKq
- **Name**: FCF_LFY_EV_Yield_SP5_Fnd17
- **Expression**: `signed_power(group_rank(ts_zscore(divide(ts_backfill(fnd17_fcf1a, 252), ts_backfill(fnd17_ev_cur, 66)), 252), industry), 5.0)`
- **Region**: USA | **Universe**: TOP3000 | **Delay**: D1
- **Neutralization**: REVERSION_AND_MOMENTUM | **Decay**: 0 | **Truncation**: 0.08
- **Pasteurization**: ON | **nan_handling**: ON
- **Tags**: PowerPoolSelected | **Color**: GREEN

## Fields Used
| Field | Description | Type | AlphaCount | Coverage |
|-------|-------------|------|------------|----------|
| fnd17_fcf1a | Free Cash Flow (Last Fiscal Year) | MATRIX | 145 | ~0.75 |
| fnd17_ev_cur | Enterprise Value (Current) | MATRIX | 688 | ~0.92 |

## IS Metrics
| Metric | Value | Threshold | Result |
|--------|-------|-----------|--------|
| Sharpe | 1.73 | > 1.58 | PASS |
| Fitness | 1.08 | > 1.0 | PASS |
| TVR | 12.41% | 5%-20% | PASS |
| Margin | 7.85bp | > 5bp | PASS |
| Returns | 4.87% | > 5% | WARNING |
| Drawdown | 4.37% | < Returns | PASS |
| 2Y Sharpe | 1.64 | > 1.58 | PASS |
| ProdCorr | 0.6353 | < 0.70 | PASS |
| SelfCorr | 0.462 | < 0.70 | PASS |

## Pyramid
- USA/D1/FUNDAMENTAL (1.2x) — UNLIT → NOW LIT
- Theme: After Cost HTVR Theme (2x) — WARNING (TVR < 20%)

## Submission Record
- Date Submitted: 2026-04-03T20:37:47-04:00
- Status: **ACTIVE** | Stage: **OS**
- OS Start Date: 2024-01-01 (checks running in background)

## Failed Predecessor: N1jeb61w (sp=3.0)
- Same expression but signed_power=3.0 instead of 5.0
- S=1.71, F=1.04, 2Y_S=1.49 (FAIL, limit=1.58)
- ProdCorr=0.6631 (would have passed)
- Rejected due to LOW_2Y_SHARPE

## Key Insights
1. Annual FCF (`fnd17_fcf1a`, ac=145) vs TTM FCF: annual updates create different signal timing, reducing ProdCorr from 0.7046 to 0.6353
2. Enterprise Value denominator (`fnd17_ev_cur`) better than `close` for avoiding production correlation
3. **signed_power=5.0 vs 3.0**: higher power amplifies extreme signals, boosting 2Y_Sharpe from 1.49 to 1.64 (difference between FAIL and PASS)
4. sp trend: sp=2(1.38) < sp=3(1.49) < sp=4(1.58=limit) < sp=5(1.64) for 2Y_Sharpe
5. decay>0 HURTS both overall and 2Y Sharpe for this signal

## Optimization History
| ID | Expression Variant | S | F | 2Y_S | ProdCorr | Decision |
|----|-------------------|-----|------|------|----------|----------|
| N1jeb61w | sp=3.0, ts_zscore(252) | 1.71 | 1.04 | 1.49 | 0.6631 | 2Y_S FAIL |
| xAz1NoGn | sp=3.0, decay=4 | 1.48 | 0.83 | 1.19 | — | decay kills |
| kqmJPwdk | sp=3.0, ts_zscore(126) | 1.77 | 0.99 | 1.46 | — | F<1.0 |
| N1je7Xqw | sp=3.0, ts_rank(252) | 1.77 | 0.93 | 1.53 | — | F<1.0 |
| wpz9jqrY | sp=2.0, ts_zscore(252) | 1.67 | 1.00 | 1.38 | — | 2Y_S too low |
| 78XojbPb | sp=4.0, ts_zscore(252) | 1.73 | 1.07 | 1.58 | — | borderline |
| **O0mJ7KKq** | **sp=5.0, ts_zscore(252)** | **1.73** | **1.08** | **1.64** | **0.6353** | **✅ SUBMITTED** |
