---
name: brain-nextMove-analysis
description: "Generates a comprehensive daily report for WorldQuant BRAIN consultants. Covers platform updates, competition progress, alpha performance (IS/OS), pyramid analysis, and actionable advice. Use when the user asks for a \"daily report\", \"morning update\", or \"status check\"."
---

# BRAIN Daily Report Workflow

This workflow generates a structured daily report for WorldQuant BRAIN consultants.
For the detailed step-by-step procedures and expected outputs, see [reference.md](reference.md).

## 0. Executive Summary
Summarize key insights, opportunities, and risks found in the analysis below.

## 1. Platform Updates
- **Messages**: Check `get_messages` for announcements.
- **Leaderboard**: Check `get_leaderboard` for rank changes.
- **Diversity**: Check `value_factor_trendScore` for diversity trends.

## 2. Competition Progress
- **Active Competitions**: `get_user_competitions`.
- **Rules**: `get_competition_details` & `get_competition_agreement`. *Crucial: Verify universe/delay constraints in the agreement.*
- **Action Items**: Recommend alphas fitting specific competition rules.

## 3. Future Events
- **Events**: `get_events` (filter for upcoming).

## 4. Research & Recommendations
- **Strategy**: Suggest next steps based on alpha performance and pyramid gaps.

## 5. Alpha Progress (IS/OS)
- **In-Sample (IS)**: `get_user_alphas(stage="IS")`.
- **Out-of-Sample (OS)**: `get_user_alphas(stage="OS")`.
- **Performance**: Analyze Sharpe, PnL, Fitness (`get_alpha_details`, `get_alpha_yearly_stats`).
- **Optimization**: Suggest improvements (e.g., idea refinement or pyramid targeting using `get_pyramid_multipliers`).