---
name: brain-datafield-exploration-general
description: "Provides 6 proven methods to evaluate new datasets on the WorldQuant BRAIN platform. Includes methods for checking coverage, non-zero values, update frequency, bounds, central tendency, and distribution. Use when the user wants to understand a specific datafield (e.g., \"what is this field?\", \"how often does it update?\")."
---

# 6 Ways to Evaluate a New Dataset

This skill provides 6 methods to quickly evaluate a new datafield on the WorldQuant BRAIN platform.
For the complete guide and detailed examples, see [reference.md](reference.md).

**Important**: Run these simulations with **Neutralization: None**, **Decay: 0**, **Test Period: P0Y0M**.
**Metrics**: Check **Long Count** and **Short Count** in the IS Summary.

## 1. Basic Coverage Analysis
*   **Expression**: `datafield` (or `vec_op(datafield)` for vectors)
*   **Insight**: % Coverage  (Long Count + Short Count) / Universe Size.

## 2. Non-Zero Value Coverage
*   **Expression**: `datafield != 0 ? 1 : 0`
*   **Insight**: Real coverage (excluding zeros). Distinguishes missing data (NaN) from actual zero values.

## 3. Data Update Frequency Analysis
*   **Expression**: `ts_std_dev(datafield, N) != 0 ? 1 : 0`
*   **Insight**: Frequency of updates. Vary `N`:
    *   `N=5` (Week): Low count implies weekly updates.
    *   `N=22` (Month): Monthly updates.
    *   `N=66` (Quarter): Quarterly updates.

## 4. Data Bounds Analysis
*   **Expression**: `abs(datafield) > X`
*   **Insight**: Check value range. Vary `X` (e.g., 1, 10, 100) to check scale (e.g., is it normalized -1 to 1?).

## 5. Central Tendency Analysis
*   **Expression**: `ts_median(datafield, 1000) > X`
*   **Insight**: Typical values over time (5-year median). Vary `X` to find the center.

## 6. Data Distribution Analysis
*   **Expression**: `X < scale_down(datafield) && scale_down(datafield) < Y`
*   **Insight**: Distribution shape. `scale_down` maps to 0-1. Vary `X` and `Y` (e.g., 0.1-0.2) to check buckets.

## Note on Vector Data
If the datafield is a **VECTOR** type, wrap it in a vector operator first (e.g., `vec_sum(datafield)` or `vec_mean(datafield)`).