# techindi_model EUR RAM — SUBMITTED ✅

## Submitted Alpha

| Field | Value |
|-------|-------|
| Alpha ID | kqmmX3wP |
| Expression | `rank(ts_zscore(subtract(predicted_fifth_quantile_ten_day_return_14, predicted_first_quantile_ten_day_return_14), 130))` |
| Dataset | techindi_model (Deep Learning Technical Indicator Returns) |
| Category | Other → EUR/D1/OTHER pyramid (1.6x) |
| Region | EUR / TOPCS1600 / D1 |
| Neutralization | REVERSION_AND_MOMENTUM |
| Decay | 30 |
| Truncation | 0.08 |
| nan_handling | ON |
| pasteurization | ON |

## IS Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Sharpe | 2.42 | > 1.58 | ✅ PASS |
| Fitness | 1.59 | > 1.0 | ✅ PASS |
| TVR | 16.77% | 1-70% | ✅ PASS |
| Margin | 8.61bp | > 8bp floor | ✅ PASS (warning) |
| Returns | 7.22% | > 5% | ✅ PASS |
| Drawdown | 3.79% | < Returns | ✅ PASS |
| 2Y Sharpe | 2.03 | > 1.58 | ✅ PASS |
| SubU Sharpe | 1.45 | > 1.28 | ✅ PASS |
| Robust | 0.75 | > 0.70 | ✅ PASS |
| ProdCorr | 0.5126 | < 0.70 | ✅ PASS |
| SelfCorr | 0.0954 | < 0.50 | ✅ PASS |

## Competition & Themes

- Power Pool: All regions/D1 Power Pool Apr'26 (1x multiplier)
- Theme: After Cost HTVR Theme (2x multiplier)
- Competition: DCC2026 (Data Creation Challenge 2026)
- Classification: Power Pool Alpha, Single Data Set Alpha, Regular Alpha

## Signal Description

**Idea**: Captures predicted return dispersion (spread between fifth and first quantile of 10-day predicted returns) as a volatility regime signal. Higher dispersion z-scored over time reveals shifts in stock-level risk.

**Rationale for data**: techindi_model provides deep learning return quantile predictions at multiple horizons. The 10-day return quantiles from model 14 offer a forward-looking dispersion measure derived from technical indicators.

**Rationale for operators**: subtract computes the quantile spread; ts_zscore normalizes over 130 days to detect regime shifts; rank provides cross-sectional ordering.

## Exploration Summary

### Datasets Exhausted (EUR/RAM)
| Dataset | Best Sharpe | Issue |
|---------|-----------|-------|
| insiders1 | 0.64 | Weak signal, low coverage |
| earnings6 | 0.32 | CONCENTRATED_WEIGHT failures |
| socialmedia12 | 0.26 | No signal with RAM |
| news84 | 0.11 | Transfer sentiment no signal |
| other699 | 0.56 | Investor data too weak |

### Winning Dataset: techindi_model
- 399 MATRIX fields, coverage=1.0, EUR/TOPCS1600
- Field structure: predicted_{quantile}_quantile_{horizon}_return_{model_version}
- Best signal: fifth-minus-first quantile spread (return dispersion)

### Optimization Path
| Variant | S | F | TVR | Margin | Robust | Issue |
|---------|-----|------|------|--------|--------|-------|
| 5-day d=4 w=66 | 3.86 | 1.82 | 49.9% | 4.43bp | 1.51 | Margin < 8bp |
| 10-day d=4 w=66 | 3.96 | 1.77 | — | — | — | SubU FAIL |
| 10-day d=30 w=130 | **2.42** | **1.59** | **16.8%** | **8.61bp** | **0.75** | **✅ SUBMITTED** |
| 10-day d=40 w=130 | 2.18 | 1.46 | 14.9% | 8.93bp | 0.57 | Robust FAIL |
| sp(rank(),1.5) d=30 | 2.43 | 1.61 | 16.7% | 8.75bp | 0.69 | Robust FAIL |
| gr(sector) d=40 | 2.15 | 1.44 | 14.2% | 8.99bp | 0.55 | Robust FAIL |
| 5-day d=30 w=130 | 2.39 | 1.51 | 18.2% | 7.97bp | 0.96 | Margin < 8bp |

### Key Discoveries
1. **Submission async checks take 70+ min for EUR** — IS checks (SELF_CORRELATION, PROD_CORRELATION) stay PENDING after submit, resolve asynchronously
2. **Margin 8bp hard floor** — MCP tool blocks below 8bp, platform accepts with warning
3. **decay=30 is the sweet spot** — d=40 causes Robust FAIL, d=4 gives TVR/margin issues
4. **Model version 14 is best** — Model 15/16/17 all weaker for EUR
5. **10-day horizon optimal** — 5-day has better Robust but lower margin; 1-day has SubU issues

## Backup Alphas
- JjXXgA6O: filter=true variant (submitted, may also activate)
- qMzzk2qO: 5-day d=4 (S=3.86, blocked by margin)
- ZYllprXQ: 5-day d=30 (S=2.39, blocked by margin)

## Timeline
- Session start: ~2026-03-30 02:00 EDT
- techindi_model breakthrough: ~02:45
- kqmmX3wP created: 03:09
- First submit attempt: ~03:17
- Alpha confirmed OS/ACTIVE: 04:50 (dateSubmitted: 04:27)
- Total: ~2h 50min from start to successful submission
