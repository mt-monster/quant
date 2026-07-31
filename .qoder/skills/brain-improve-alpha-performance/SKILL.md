---
name: brain-improve-alpha-performance
description: Provides a systematic 5-step workflow for improving WorldQuant BRAIN alphas. Includes steps for gathering alpha info, evaluating datafields, proposing idea-focused improvements (using arXiv), simulating variants, and validating. Use when the user wants to improve an existing alpha or fix failing submission tests.
---

# Alpha Improvement Workflow

This repeatable workflow enhances alphas by focusing on core idea refinements rather than just mechanical tweaks.
For the detailed steps, analysis techniques, and best practices, see [reference.md](reference.md).

## Step 1: Gather Alpha Information (5-10 mins)
**Goal**: Identify weaknesses (low Sharpe, high correlation, etc.).
- Fetch alpha details (`get_alpha_details`).
- Check PnL, Sharpe, Fitness, Turnover.
- Run submission checks (`get_submission_check`) and correlation checks (`check_correlation`).

## Step 2: Evaluate Core Datafield(s) (5-10 mins)
**Goal**: Understand data properties (sparsity, frequency).
- Run 6 evaluation simulations (Coverage, Non-Zero, Update Frequency, Bounds, Central Tendency, Distribution) using `brain-datafield-exploration` skill methods.

## Step 3: Propose Idea-Focused Improvements (10-15 mins)
**Goal**: Evolve the signal with theory-backed concepts.
- Review docs for tips (ATOM principle, flipping negatives).
- Search arXiv for concepts (e.g., "persistence", "momentum").
- Brainstorm 4-6 variants (e.g., add decay, change normalization).

## Step 4: Simulate and Test Variants (10-20 mins)
**Goal**: Compare ideas via metrics.
- Use `create_multiSim` to test variants.
- Compare Fitness, Sharpe, and Sub-universe performance.

## Step 5: Validate and Iterate (5-10 mins)
**Goal**: Confirm submittability.
- Run final checks.
- If failing, repeat from Step 3 with new ideas.
- If passing, submit!

## Best Practices
- **Cycle Limit**: 3-5 iterations per alpha.
- **Focus**: 70% on ideas, 30% on parameter tweaks.
- **Goal**: Passing checks + stable yearly stats.