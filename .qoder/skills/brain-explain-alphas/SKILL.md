---
name: brain-explain-alphas
description: Provides a step-by-step workflow for analyzing and explaining WorldQuant BRAIN alpha expressions. Use this when the user asks to explain a specific alpha expression, what a datafield does, or how operators work together. Includes steps for data field lookup, operator analysis, and external research.
---

# Alpha Explanation Workflow

This manual provides a workflow for analyzing and explaining a WorldQuant BRAIN alpha expression.
For the full detailed workflow and examples, see [reference.md](reference.md).

## Step 1: Deconstruct the Alpha Expression
Break down the alpha expression into its fundamental components: data fields and operators.
*Example:* `quantile(ts_regression(oth423_find,group_mean(oth423_find,vec_max(shrt3_bar),country),90))`
- **Data Fields**: `oth423_find`, `shrt3_bar`
- **Operators**: `quantile`, `ts_regression`, `group_mean`, `vec_max`

## Step 2: Analyze Data Fields
Use the `get_datafields` tool to get details about each data field.
- Identify: Instrument Type, Region, Delay, Universe, Data Type (Matrix/Vector).
- Note: Vector data requires aggregation (e.g., `vec_max`).

## Step 3: Understand the Operators
Use the `get_operators` tool to understand what each operator does.

## Step 4: Consult Official Documentation
Use `get_documentations` and `read_specific_documentation` for deep dives into concepts (e.g., vector data handling).

## Step 5: Synthesize and Explain
Structure the explanation:
1.  **Idea**: High-level summary of the strategy.
2.  **Rationale for data**: Why these fields? What do they represent?
3.  **Rationale for operators**: How do they transform the data?
4.  **Further Inspiration**: Potential improvements.

## Appendix: Vector Data
Vector data records multiple events per day per instrument (e.g., news). It requires aggregation (like `vec_mean`, `vec_sum`) to become a matrix value usable by other operators.