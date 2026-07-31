# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a WorldQuant BRAIN alpha strategy generation and backtesting tool. It integrates with the WorldQuant Brain platform via API to automate the alpha factor lifecycle: generation, backtesting, analysis, and submission.

## Working Directory

**Important:** Run the pipeline CLI from the repository root (the directory containing `worldquant_alpha/`), using the module path `worldquant_alpha.pipeline.cli`.

## Common Commands

```bash
# Run the full pipeline (default config)
python -m worldquant_alpha.pipeline.cli run

# Run with dataset and template options
python -m worldquant_alpha.pipeline.cli run --dataset analyst14 --region USA --universe TOP3000 --delay 1 --template-names "EPS Consensus (analyst14)"

# Run specific stages only
python -m worldquant_alpha.pipeline.cli run --from-stage first_order --to-stage first_order_backtest

# Force re-run of completed stages
python -m worldquant_alpha.pipeline.cli run --force

# Check pipeline status / resume from checkpoint / reset state
python -m worldquant_alpha.pipeline.cli status
python -m worldquant_alpha.pipeline.cli resume
python -m worldquant_alpha.pipeline.cli reset

# Validate a config file / list available configs
python -m worldquant_alpha.pipeline.cli validate --config third_order_default.yaml
python -m worldquant_alpha.pipeline.cli list-configs

# Template management
python -m worldquant_alpha.pipeline.cli template list
python -m worldquant_alpha.pipeline.cli template show "EPS Consensus (analyst14)"
python -m worldquant_alpha.pipeline.cli template stats
```

Available stages (in order): `first_order`, `first_order_backtest`, `first_order_filter`, `second_order`, `second_order_backtest`, `second_order_filter`, `third_order`, `third_order_backtest`, `third_order_filter`.

The full CLI reference lives in `worldquant_alpha/docs/PIPELINE_COMMANDS.md`.

## Architecture

### Main Components

- **`worldquant_alpha/`** - Main application code
  - **`pipeline/`** - Three-order alpha generation pipeline
    - **`cli.py`** - CLI entry point using Click (`python -m worldquant_alpha.pipeline.cli`)
    - **`engine.py`** - `PipelineEngine`: stage orchestration, checkpoint/resume via a state file
    - **`stages/`** - Stage executors (`base.py`, `first_order.py`, `second_order.py`, `backtest.py`, `filter.py`)
    - **`core/`** - Alpha factory, backtest manager, pruner, state management
    - **`services/`** - Data fetch and candidate-rule services
    - **`config/`** - YAML config loader and schema
    - **`README.md`** / **`ARCHITECTURE.md`** - Pipeline design docs
  - **`wd_lib/`** - Core library for WorldQuant BRAIN API integration
    - **`client.py`** - Main `WorldQuantClient` class providing unified API access
    - **`auth/`** - Session management and authentication
    - **`api/`** - API endpoints (datasets, alphas, simulation)
    - **`alpha/`** - Alpha builder, factory, validator
    - **`backtest/`** - Backtest executor and analyzer
    - **`scan/`** - Scan runners (e.g. tri-mode runner)
    - **`config/`** - Configuration and settings
    - **`utils/`** - Utilities (exceptions, helpers, retry)
  - **`configs/`** - Pipeline YAML configs (`third_order_default.yaml`, `third_order_aggressive.yaml`, `third_order_conservative.yaml`)
  - **`docs/PIPELINE_COMMANDS.md`** - Full pipeline CLI reference

### Data Flow

1. Data fields are fetched and preprocessed (backfill, winsorize)
2. `first_order` stage generates time-series alphas, which are backtested and filtered
3. `second_order` stage applies group operations to survivors, backtested and filtered
4. `third_order` stage applies event-trigger (`trade_when`) logic, backtested and filtered
5. Stage progress is checkpointed to a state file (default `.pipeline_state.json`) for resume

### Templates

Alpha templates are managed through the `template` CLI command group (`list`, `show`, `add`, `update`, `delete`, `enable`, `disable`, `export`, `stats`). Templates are parameterized expressions with `<component>` placeholders bound to dataset fields.

### Configuration

Pipeline behavior is configured through YAML files in `worldquant_alpha/configs/` (see `list-configs` and `validate` commands).

Environment variables in `worldquant_alpha/.env`:
- `WQ_USERNAME`, `WQ_PASSWORD` - WorldQuant credentials
- Optional SMTP settings for email notifications
- `LOG_LEVEL` - Logging level (default: INFO)
