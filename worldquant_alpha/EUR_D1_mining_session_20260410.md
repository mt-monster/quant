# EUR D1 PPA Alpha Mining Session - 2026-04-10

## Summary
Successfully mined EUR region D1 delay PPA alphas from unlit pyramid datasets, focusing on fundamental17 (Direct Fundamental Data).

## Top Performing Alphas

### Alpha 1: 9qAqeKLo ⭐⭐⭐
- **Expression**: `signed_power(group_zscore(ts_zscore(fnd17_10_rhsfcfq, 66), subindustry), 1.5)`
- **Dataset**: fundamental17 (FCF per share Q annualized)
- **Region**: EUR
- **Universe**: TOP2500
- **Delay**: 1
- **Decay**: 0
- **Neutralization**: MARKET
- **Truncation**: 0.08

**Performance Metrics**:
- Sharpe: **1.65** ✅ (PASS)
- Fitness: **0.83**
- Turnover: 19.3%
- Margin: 5.1bp
- Returns: 4.9%
- Drawdown: 3.5%
- 2Y Sharpe: 1.49

**Status**: Ready for correlation check and submission

### Alpha 2: E5r5jzrJ ⭐⭐⭐
- **Expression**: `signed_power(group_zscore(ts_zscore(fnd17_10_rhsfcfq, 66), subindustry), 1.5)`
- **Dataset**: fundamental17 (FCF per share Q annualized)
- **Region**: EUR
- **Universe**: TOP2500
- **Delay**: 1
- **Decay**: 0
- **Neutralization**: SLOW
- **Truncation**: 0.08

**Performance Metrics**:
- Sharpe: **1.63** ✅ (PASS)
- Fitness: 0.65
- Turnover: 23.7%
- Margin: 3.1bp
- Returns: 3.7%
- Drawdown: 3.7%
- 2Y Sharpe: 1.36

**Status**: Ready for correlation check and submission

## Mining Process

### Datasets Explored
1. **analyst69** (Fundamental Analyst Estimates) - Weak signals (Sharpe < 0.6)
2. **sentiment21** (AI Sentiment Score Data) - High turnover (>150%), unstable
3. **fundamental17** (Direct Fundamental Data) - ✅ **SUCCESS**

### Key Findings
- **Winning field**: `fnd17_10_rhsfcfq` (Free Cash Flow per share Q, annualized)
  - Coverage: 70.01%
  - User count: 284 (relatively unlit)
  - Alpha count: 705
  - Pyramid multiplier: 1.2

- **Winning pattern**: 
  - `ts_zscore(field, 66)` for time-series normalization
  - `group_zscore(..., subindustry)` for cross-sectional ranking within subindustry
  - `signed_power(..., 1.5)` for non-linear transformation to amplify signal
  - `decay=0` for no signal decay (quarterly data updates slowly)

### Batches Executed
- Batch 1-3: analyst69, sentiment21 exploration (failed)
- Batch 4: fundamental17 revenue/income growth (weak signals, Sharpe 0.58)
- Batch 6: fundamental17 FCF fields ✅ (Sharpe 1.29, 1.22)
- Batch 7: Enhanced with signed_power ✅ (Sharpe 1.42)
- Batch 8: Optimized decay=0 ✅ (Sharpe 1.65)
- Batch 10: Tested SLOW neutralization ✅ (Sharpe 1.63)

## Next Steps
1. Check production correlation for both alphas (must be < 0.7)
2. If ProdCorr < 0.7, submit both alphas
3. Set alpha properties with proper naming and tags
4. Continue mining for additional alphas if needed

## Economic Rationale
**Signal**: Free Cash Flow per share quality signal
- Companies with improving FCF per share (after normalization and industry adjustment) tend to outperform
- The signal captures fundamental quality that is not fully reflected in prices
- Subindustry neutralization removes sector biases
- Signed_power transformation amplifies strong signals while dampening noise
