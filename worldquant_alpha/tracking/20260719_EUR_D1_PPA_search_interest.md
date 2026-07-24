# EUR/D1 PPA Session — 2026-07-19

## Goal
- Region EUR / Universe TOPCS1600 / Delay D1
- Type: PPA (single-dataset ATOM), 2-field combos
- Target: 2 submittable alphas
- Hard gate: ProdCorr must be available AND < 0.7 (never submit otherwise)

## Pyramid
- EUR/D1 all categories unlit (alphaCount=0)
- Selected OTHER 1.6x: `search_interest` (after `news_sentiment_nlp` PROBABLE_FAIL)

## Progress: 0/2 submitted

### Best candidates (search_interest)

| ID | Neut | Decay | Trunc | S | F | TVR | Margin | SUB | 2Y | Robust | ProdCorr | Status |
|----|------|-------|-------|---|---|-----|--------|-----|-----|--------|----------|--------|
| MPLoYbWr | STAT+ts_decay | 12 | 0.05 | 1.33W | 0.61W | 13.7% | 42bp | PASS | 1.06W | **0.67 FAIL** | **0.464** | PPA path, fix ROBUST |
| d5RAKx1K | CROWDING | 16 | 0.05 | 1.61 | 1.00 | 14.4% | 76.5bp | 0.74 FAIL | 1.02 FAIL | 0.73 PASS | **0.588** | Fix SUB/2Y |
| le3bMVMx | CROWDING | 16 | 0.05 | 1.61 | 1.01 | 14.2% | 78.2bp | 0.75 FAIL | 0.99 FAIL | 0.77 PASS | — | Near |
| LLdAMnje | STATISTICAL | 12 | 0.05 | 1.62 | 0.66 | 21.7% | 33bp | FAIL | **1.53** | FAIL | — | 2Y almost pass |
| E5eXpGR9 | CROWDING | 18 | 0.08 | 1.59 | 1.02 | 13.2% | 82.5bp | 0.70 FAIL | 0.98 FAIL | 0.72 PASS | — | Near |

### Core expression
```
signed_power(
  group_rank(
    ts_rank(
      divide(
        ts_backfill(vec_avg(relative_interest_score_7), 22),
        ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)
      ),
      126
    ),
    industry
  ),
  3.0
)
```

### Blockers
1. SUB_UNIVERSE ~0.74 vs limit ~0.85
2. LOW_2Y_SHARPE ~1.0 vs 1.58 (STATISTICAL lifts 2Y to ~1.48 but kills Fitness)
3. check_correlation MCP currently errors (NoneType) — must resolve before any submit

### Discarded
- news_sentiment_nlp: max S≈0.44 after 2 batches → switched
- acquisition_model early probes: S≤0.20
