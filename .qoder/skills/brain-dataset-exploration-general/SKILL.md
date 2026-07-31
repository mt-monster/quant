---
name: brain-dataset-exploration-general
description: "Provides a comprehensive workflow for deep-diving into entire WorldQuant BRAIN datasets. Includes steps for dataset selection, field categorization, detailed description generation, and cross-platform research. Use when the user wants to \"audit a dataset\", \"categorize fields\", or \"explore a new dataset\"."
---

# Dataset Exploration Expert Workflow

This workflow guides the deep analysis and categorization of datasets.
For the detailed job duty manual and specific MCP tool strategies, see [reference.md](reference.md).

## Phase 1: Dataset Selection & Initial Assessment
1. **Identify Dataset**: Select based on strategic importance or user needs.
2. **Initial Exploration**:
   - Use `get_datasets` to find datasets.
   - Use `get_datafields` to count fields and check coverage.
   - Use `get_documentations` to find related docs.

## Phase 2: Field Categorization
Group data fields into logical categories:
- **Business Function**: Financials, Market Data, Estimates, etc.
- **Data Type**: Matrix, Vector.
- **Update Frequency**: Daily, Quarterly.
- **Hierarchy**: Primary -> Secondary -> Tertiary (e.g., Financials -> Income Statement -> Revenue).

## Phase 3: Enhanced Description & Analysis
1. **Describe**: Write detailed descriptions (Business context, Methodology, Typical values).
2. **Analyze**: Use `brain-datafield-exploration` techniques on key fields to understand distributions and patterns.

## Phase 4: Integration
1. **Research**: Check forum posts for community insights.
2. **Alpha Ideas**: Brainstorm alpha concepts based on the dataset characteristics.

## Core Responsibilities
- **Deep Dive**: Focus on one dataset at a time.
- **Inventory**: Catalog all fields.
- **Documentation**: Improve descriptions.