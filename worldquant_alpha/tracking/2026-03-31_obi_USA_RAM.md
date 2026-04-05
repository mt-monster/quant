# OBI Order Book Imbalance - USA D1 RAM (2026-03-31)

## Session Summary
- **Dataset**: order_book_imbalance (Order Book Liquidity and Imbalance Analytics)
- **Region/Universe**: USA / TOP3000 / D1
- **Neutralization**: REVERSION_AND_MOMENTUM (RAM)
- **Pyramid**: USA/D1/OTHER (1.4x)
- **Total Simulations**: ~20

## Submitted Alpha

### 6XqR5zpp (SUBMITTED - AWAITING ASYNC CHECKS)
```
signed_power(group_rank(ts_rank(subtract(vec_avg(bid_order_insertion_count), vec_avg(ask_order_insertion_count_2)), 66), industry), 12.0)
```
- S=1.74, F=1.03, TVR=21%, Margin=7.04bp, Returns=7.39%, DD=3.62%
- SUB_UNIVERSE=0.82, IC_Sharpe=1.56
- ALL immediate IS checks PASS
- LOW_2Y_SHARPE=1.00 (WARNING), HT_RETURNS_RATIO=0.37 (WARNING)
- submit_alpha: success=true, blocked=false
- Properties: name, description, tags=["PowerPoolSelected"]

## Backup Candidates

### pwz8AGKV — Strongest Overall (S=1.84, F=1.22)
```
signed_power(group_rank(ts_zscore(subtract(vec_avg(bid_order_volume_deleted), vec_avg(ask_order_volume_deleted)), 66), industry), 4.0)
```
- S=1.84, F=1.22, TVR=19.9%, Margin=8.8bp, Returns=8.74%, DD=4.11%
- SUB_UNIVERSE=0.92, 2Y=1.16 WARNING
- ALL PASS; Properties set

### Xgl1rqpl — Second Backup (S=1.82, F=1.09)
```
signed_power(group_rank(ts_rank(subtract(vec_avg(bid_order_volume_deleted), vec_avg(ask_order_volume_deleted)), 66), industry), 12.0)
```
- S=1.82, F=1.09, TVR=22%, SUB=0.93, 2Y=1.27 WARNING
- ALL PASS; Properties set

## Field Pair Performance Summary

| Field Pair | L2 Op | sp | S | F | SUB | 2Y | Verdict |
|------------|-------|-----|---|---|-----|-----|---------|
| **volume_deleted** bid-ask | ts_zscore | 4 | **1.84** | **1.22** | 0.92 | 1.16 | **BEST** |
| **volume_deleted** bid-ask | ts_rank | 12 | **1.82** | **1.09** | 0.93 | 1.27 | 2nd |
| insertion_count bid-ask | ts_rank | 12 | 1.74 | 1.03 | 0.82 | 1.00 | Submitted |
| deletion_count bid-ask | ts_rank | 12 | 1.75 | 1.04 | 0.77 | 0.99 | Viable |
| insertion_count bid-ask | ts_zscore | 4 | 1.70 | 1.11 | 0.70❌ | 0.96 | SUB FAIL |
| volume_deleted bid-ask | divide | 12 | 1.69 | 0.94 | 0.80 | 1.15 | F warn |
| execution_count bid-ask | ts_rank | 12 | 1.59 | 0.88 | 0.67 | 0.93 | F FAIL |
| vol_change_modification | ts_rank | 12 | 1.59 | 0.88 | 0.47 | 0.96 | F FAIL |
| vol_change_replacement | ts_rank | 12 | 1.55 | 0.84 | 0.50 | 0.36 | S+F FAIL |
| market_impact/spread | ts_rank | 12 | 1.89 | 1.04 | - | 0.57 | 2Y FAIL |
| auction/spread | ts_rank | 12 | 1.56 | 0.62 | - | 0.89 | F FAIL |
| rest_time_filled bid-ask | ts_rank | 12 | 1.42 | 0.70 | 0.27 | 0.29 | S+F FAIL |
| impact/quote_ratio | ts_rank | 12 | 1.19 | 0.57 | 0.04 | 0.49 | S+F FAIL |
| auction/volatility | ts_rank | 12 | 1.47 | 0.75 | 0.24 | 0.55 | S+F FAIL |
| volume_deleted corr | ts_corr | 12 | -0.82 | -0.5 | - | - | Reversed |

## Key Findings
1. **OBI is a hidden gold mine**: dataset has userCount=0 and alphaCount=0 — completely untouched
2. **volume_deleted > insertion_count > deletion_count**: volume has stronger signal than count
3. **ts_zscore >> ts_rank for volume data**: z-score captures magnitude while rank loses it
4. **sp=4 optimal for ts_zscore**: concentrates enough without overfitting (vs sp=12 for ts_rank)
5. **bid-ask order flow imbalance is the core signal**: non bid-ask fields all fail
6. **2023 signal collapse**: ALL OBI signals have weak 2023 (COVID rotation ended), but WARNING not FAIL
7. **RAM neutralization compatible**: OBI order flow survives RAM (unlike sentiment/news/social)

## Decay Optimization (insertion_count, industry, sp=12, w=66)
| d | S | F | TVR | SUB | 2Y | Notes |
|---|---|---|-----|-----|-----|-------|
| 4 | 1.68 | 0.69 | 41% | 0.77 | 1.06 | F fail |
| 6 | 1.74 | 0.83 | 31% | 0.85 | 1.07 | F fail |
| 8 | 1.74 | 0.91 | 27% | 0.83 | 1.03 | F fail |
| **12** | **1.74** | **1.03** | **21%** | **0.82** | **1.00** | **Sweet spot** |
| 20 | 1.75 | 1.20 | 16% | 0.82 | 0.90 | HT_TVR fail |

## Yearly Performance (6XqR5zpp)
| Year | Sharpe | Notes |
|------|--------|-------|
| 2015 | 2.27 | Strong |
| 2016 | 1.84 | Strong |
| 2017 | 2.42 | Strong |
| 2018 | 1.20 | OK |
| 2019 | 2.85 | Peak |
| 2020 | 1.18 | COVID vol |
| 2021 | 2.53 | Strong |
| 2022 | 1.74 | Strong |
| 2023 | -0.04 | Signal collapse → 2Y=1.00 WARNING |
