# institutions6 USA FAST Session — 2026-03-29

## Result: SUCCESS ✅

## Submitted Alpha: QPlrQkoM
- **Name**: inst6_event_buyer_seller_flow
- **Expression**: `if_else(days_from_last_change(count_institutional_buyers_security) < 5, group_rank(subtract(ts_rank(count_institutional_buyers_security, 22), ts_rank(count_institutional_sellers_security, 22)), sector), 0)`
- **Settings**: USA/TOP3000/D1, FAST neut, decay=35, truncation=0.08
- **Metrics**: S=1.60, F=0.97, TVR=10.27%, Margin=9.01bp, Returns=4.63%, DD=3.98%
- **IC Metrics**: S=1.59, F=0.97
- **ProdCorr**: 0.6456 < 0.70 ✅
- **2Y_Sharpe**: 1.96 ✅
- **SubU**: 0.72 ✅
- **Pyramid**: USA/D1/INSTITUTIONS (1x, FIRST LIT!)
- **Theme**: USA HighTurnover Datasets Theme (2x)

## Key Optimization Journey

### Field Discovery
- Only COUNT fields (buyers/sellers/holders) have signal
- VALUE fields (market_value, shares_bought/sold) have NEGATIVE signal
- SHARE QUANTITY fields have NO signal

### Structural Breakthroughs
1. **Event gating**: `days_from_last_change < 5` → +30% Sharpe (0.89→1.17)
2. **ts_rank >> ts_zscore**: S jumped from 1.34 → 1.56 (same params). ts_rank is vastly superior for discrete integer count data
3. **Decay scaling**: Higher decay (35) dramatically boosts Fitness without hurting Sharpe for quarterly institutional data

### Parameter Sweep Results

#### ts_rank Window Sweep (decay=15)
| Window | S | F | IC_S | IC_F |
|--------|------|------|------|------|
| 15 | 1.52 | 0.78 | 1.57 | 0.89 |
| 18 | 1.55 | 0.82 | 1.59 | 0.94 |
| **22** | **1.56** | **0.86** | **1.59** | **0.94** |
| 25 | 1.55 | 0.87 | 1.58 | 0.94 |
| 33 | 1.51 | 0.87 | 1.51 | 0.89 |
| 44 | 1.45 | 0.83 | 1.42 | 0.82 |

#### Decay Sweep (window=22, ts_rank)
| Decay | S | F | Margin | Notes |
|-------|------|------|--------|-------|
| 10 | 1.50 | 0.74 | 4.82bp | |
| 15 | 1.56 | 0.86 | 6.03bp | |
| 20 | 1.57 | 0.92 | 6.93bp | |
| 25 | 1.58 | 0.94 | 7.69bp | S PASS! |
| 30 | 1.58 | 0.95 | 8.38bp | |
| **35** | **1.60** | **0.97** | **9.01bp** | **OPTIMAL** |
| 40 | 1.59 | 0.97 | 9.46bp | SubU FAIL |

### ts_zscore vs ts_rank Comparison (w=33, d=15)
| Operator | S | F |
|----------|------|------|
| ts_zscore | 1.34 | 0.75 |
| ts_rank | 1.51 | 0.87 |

### Anti-Patterns
- signed_power(1.5) HURTS institutional data (S: 1.34→1.25)
- holders as gate variable WORSE than buyers (S: 1.34→1.20)
- ts_zscore inferior to ts_rank for integer count data
- Window too short (15) → noise; too long (44+) → stale signal
- Decay too high (40+) → SubU check fails

## Economic Rationale
Institutional 13F filing disclosure creates an information event. In the 5 days following new disclosure, stocks where buyer count rank exceeds seller count rank (relative to own history) outperform within their sector. The signal captures "institutional consensus" — when many independent institutions buy vs sell, it reveals private information about stock quality.
