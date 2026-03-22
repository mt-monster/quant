---
name: brain-how-to-pass-AlphaTest
description: Provides detailed requirements, thresholds, and improvement tips for WorldQuant BRAIN Alpha submission tests. Covers Fitness, Sharpe, Turnover, Weight, Sub-universe, and Self-Correlation tests. Use this when the user asks about alpha submission failures, how to improve alpha metrics, or test requirements.
---

# BRAIN Alpha Submission Tests: Requirements and Improvement Tips

This skill provides key requirements and expert tips for passing alpha submission tests.
For comprehensive details, thresholds, and community-sourced strategies, please read [reference.md](reference.md).

## Overview

Alphas must pass a series of pre-submission checks to ensure they meet quality thresholds.

## 1. Fitness
### Requirements
- At least "Average": Greater than 1.3 for Delay-0 or Greater than 1 for Delay-1.
- Fitness = Sharpe * sqrt(abs(Returns) / max(Turnover, 0.125)).

### Tips to Improve
- Increase Sharpe/Returns and reduce Turnover.
- Use group operators (e.g., with pv13) to boost fitness.
- Check with `check_submission` tool.

## 2. Sharpe Ratio
### Requirements
- Greater than 2 for Delay-0 or Greater than 1.25 for Delay-1.
- Sharpe = sqrt(252) * IR, where IR = mean(PnL) / stdev(PnL).

### Tips to Improve
- Focus on consistent PnL with low volatility.
- Decay signals separately for liquid/non-liquid stocks.
- If Sharpe is negative (e.g., -1 to -2), try flipping the sign: `-original_expression`.

## 3. Turnover
### Requirements
- 1% < Turnover < 70%.

### Tips to Improve
- Use decay functions (`ts_decay_linear`) to smooth signals.

## 4. Weight Test
### Requirements
- Max weight in any stock <10%.

### Tips to Improve
- Use neutralization (e.g., `neutralize(x, "MARKET")`) to distribute weights.

## 5. Sub-universe Test
### Requirements
- Sub-universe Sharpe >= 0.75 * sqrt(subuniverse_size / alpha_universe_size) * alpha_sharpe.

### Tips to Improve
- Avoid size-related multipliers.
- Decay liquid/non-liquid parts separately.

## 6. Self-Correlation
### Requirements
- <0.7 PnL correlation with own submitted alphas.

### Tips to Improve
- Submit diverse ideas.
- Use `check_correlation` tool.
- Transform negatively correlated alphas.

## General Guidance
- **Start Simple**: Use basic operators like `ts_rank` first.
- **Optimize Settings**: Choose universes like TOP3000 (USA, D1).
- **ATOM Principle**: Avoid mixing datasets to benefit from relaxed "ATOM" submission criteria (Last 2Y Sharpe).