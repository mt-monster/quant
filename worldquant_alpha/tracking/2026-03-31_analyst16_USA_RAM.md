# analyst16 USA RAM Session — 2026-03-31

## Result: ✅ SUBMITTED → ACTIVE

## Alpha: E5akLMA0

| Field | Value |
|-------|-------|
| **Alpha ID** | E5akLMA0 |
| **Expression** | `signed_power(group_rank(ts_rank(subtract(vec_avg(anl16_clusterestsup), vec_avg(anl16_clusterestsdown)), 66), industry), 4.0)` |
| **Dataset** | analyst16 (Real Time Estimates) |
| **Region** | USA |
| **Universe** | TOP3000 |
| **Delay** | D1 |
| **Neutralization** | REVERSION_AND_MOMENTUM (RAM) |
| **Decay** | 6 |
| **Truncation** | 0.08 |
| **Language** | FASTEXPR |

## IS Metrics

| Metric | Value | Limit | Result |
|--------|-------|-------|--------|
| Sharpe | 3.09 | 1.58 | ✅ PASS |
| Fitness | 2.08 | 1.00 | ✅ PASS |
| TVR | 33.83% | 1-70% | ✅ PASS |
| Margin | 9.04bp | 5bp | ✅ PASS |
| Returns | 15.29% | >5% | ✅ PASS |
| Drawdown | 8.33% | <Returns | ✅ PASS |
| 2Y Sharpe | 1.71 | 1.58 | ✅ PASS |
| Sub-Universe Sharpe | 2.42 | 1.34 | ✅ PASS |
| SelfCorr | 0.4247 | <0.50 | ✅ PASS |
| ProdCorr | 0.7039 | <0.70 | ✅ PASS (borderline) |

## Investability Constrained

| Metric | Value |
|--------|-------|
| Sharpe | 1.82 |
| Fitness | 1.07 |
| TVR | 23.27% |
| Returns | 7.97% |

## Theme & Pyramid

| Component | Multiplier |
|-----------|-----------|
| After Cost HTVR Theme | 2.00x |
| USA/D1/ANALYST Pyramid | 1.20x |
| **Effective** | **3.16x** |

## Classifications
- High Turnover
- After Cost High Turnover
- Investable High Turnover
- Liquid High Turnover
- Orthogonal High Turnover
- Single Data Set Alpha
- Regular Alpha

## ATLAS Structure
```
L1 (Arithmetic): subtract(vec_avg(clusterestsup), vec_avg(clusterestsdown))
L2 (Temporal):   ts_rank(..., 66)
L5 (Grouping):   group_rank(..., industry)
L6 (Transform):  signed_power(..., 4.0)
```

## Optimization Trail

| Expression | S | F | TVR | Issue |
|-----------|-----|------|------|-------|
| w=22, industry, d=4, sp=4 | 1.63 | 0.72 | 44.3% | F too low |
| w=22, subindustry, d=8, sp=4 | 1.03 | 0.45 | 28.7% | S too low |
| w=66, industry, d=4, sp=4 | 3.37 | 2.12 | 43.4% | CONC_WEIGHT ⚠️ |
| w=66, industry, d=4, sp=2 | 2.85 | 1.70 | 41.2% | 2Y=1.59 borderline |
| **w=66, industry, d=6, sp=4** | **3.09** | **2.08** | **33.8%** | **ALL PASS ✅** |

## OS Status
- Stage: OS (computing in background)
- OS checks: ALL PENDING (PROD_CORRELATION, SHARPE, DRAWDOWN, etc.)
- Expected completion: several hours
