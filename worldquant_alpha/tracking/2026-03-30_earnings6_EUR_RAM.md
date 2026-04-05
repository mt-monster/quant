# earnings6 EUR RAM Session — 2026-03-30

## Session Info
- **Dataset**: earnings6 (International Findings Data)
- **Region**: EUR | **Universe**: TOPCS1600 | **Delay**: D1
- **Neutralization**: REVERSION_AND_MOMENTUM (RAM)
- **Pyramid**: EUR/D1/EARNINGS (multiplier 1.2x, previously UNLIT)

## Best Alpha: 3q66mRo0

```
signed_power(quantile(ts_rank(divide(ts_backfill(vec_avg(ern6_actual_eps), 66), close), 600)), 3.0)
```

| Metric | Value | Limit | Status |
|--------|-------|-------|--------|
| Sharpe | 1.67 | 1.58 | PASS |
| Fitness | 1.15 | 1.00 | PASS |
| TVR | 22.06% | 1-70% | PASS |
| Margin | 9.43bp | 8bp | PASS |
| Returns | 10.41% | — | OK |
| Drawdown | 9.02% | — | OK |
| IS_LADDER (2Y) | 2.16 | 2.02 | PASS |
| SUB_UNIVERSE | 1.01 | 0.89 | PASS |
| ROBUST_UNIVERSE | 0.95 | 0.70 | PASS |
| ProdCorr | 0.5195 | 0.70 | PASS |
| SelfCorr | — | — | PENDING |

### Yearly Performance
| Year | Sharpe | Returns | Fitness |
|------|--------|---------|---------|
| 2019 | 3.11 | 16.54% | 2.34 |
| 2020 | 0.24 | 1.52% | 0.06 |
| 2021 | 0.89 | 6.22% | 0.51 |
| 2022 | 2.26 | 15.18% | 1.95 |
| 2023 | 2.06 | 11.58% | 1.58 |

### Parameters
- decay=8, truncation=0.08, pasteurization=ON, nan_handling=ON
- Tags: PowerPoolSelected
- Competition: DCC2026
- Themes: After Cost HTVR Theme (2x), PP Apr'26 (PENDING)

## Submission Status: SUCCESS!
- **Status**: ACTIVE
- **Stage**: OS (Out-of-Sample)
- **Classification**: POWER_POOL:POWER_POOL_ELIGIBLE (Power Pool Alpha)
- **dateSubmitted**: 2026-03-30T08:29:41-04:00
- **SelfCorrelation**: 0.1392 (PASS)
- **ProdCorrelation**: 0.5195 (PASS)
- **Themes**: All regions/D1 Power Pool Apr'26 (multiplier 1x)
- **Pyramids**: EUR/D1/PV (1.1x) + EUR/D1/EARNINGS (1.2x) = effective 2x
- **OS Checks**: 11 checks PENDING (RANK_SHARPE, SHARPE, IS_SHARPE, PROD_CORRELATION, SUB_UNIVERSE_SHARPE, NEW_HIGH, MEMORY_USAGE, SUPER_UNIVERSE_SHARPE, SELF_CORRELATION, CONCENTRATED_WEIGHT, DRAWDOWN)

## Other Candidates (All have IS_LADDER_SHARPE issues)

| ID | Expression | sp | d | S | F | Margin | IS_LADDER | Status |
|----|-----------|----|----|------|------|--------|-----------|--------|
| 3q66mRo0 | sp3(quantile(ts_rank(EPS/close,600))) | 3.0 | 8 | 1.67 | 1.15 | 9.43bp | PASS 2.16 | BEST |
| kqmm6Aql | sp2(quantile(ts_rank(EPS/close,600))) | 2.0 | 4 | 1.69 | 1.07 | 8.04bp | WARN 1.31 | Processing |
| blPPJgJK | quantile(ts_rank(EPS/close,600)) | — | 4 | 1.59 | 1.07 | 9.0bp | WARN 1.54 | REJECTED |
| omzzake5 | quantile(ts_rank(EPS/close,600)) | — | 2 | 1.69 | 1.04 | 7.5bp | — | Not submitted |

## Key Findings
1. **Only ern6_actual_eps has signal** in EUR (all other 65 fields produce S≤0.18)
2. **EUR ProdCorr=0.52** — much lower than USA earnings7 (0.79). EUR market not saturated for earnings yield.
3. **signed_power(3.0) is essential** — amplifies recent-year Sharpe enough to pass IS_LADDER_SHARPE
4. **decay=8 is optimal** — balances Fitness (1.15) and Margin (9.43bp) while maintaining S=1.67
5. **RAM neutralization is only viable neut** — SLOW S=0.68, FAST S=1.33, S&F S=0.45, CROWDING S=1.41
6. **ts_rank window=600 optimal** — shorter/longer windows both reduce Sharpe
7. **2-field combinations unsuccessful** — actual_eps vs estimated_eps produce correlated signals; all other field pairs zero
