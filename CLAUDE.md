# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a WorldQuant BRAIN alpha strategy generation and backtesting tool. It integrates with the WorldQuant Brain platform via API to automate the alpha factor lifecycle: generation, backtesting, analysis, and submission.

## Working Directory

**Important:** All Python commands must run from the `worldquant_alpha/` subdirectory.

## Common Commands

```bash
cd worldquant_alpha

# Initialize the system (create database tables)
python -m main init

# Fetch data fields from platform
python -m main fetch --dataset fundamental6

# Generate alpha expressions from template
python -m main generate --template 0 --limit 10

# Batch generate alphas
python -m main generate_batch --start_template 5 --end_template 10 --limit_per_template 5

# Run backtest on alphas in database
python -m main backtest --from_db --limit 10

# Analyze backtest results
python -m main analyze --ir_threshold 0.1 --limit 100

# Run complete pipeline
python -m main pipeline --template 0 --limit 10 --ir_threshold 0.1

# Run continuous execution (checks for daily submission)
python -m main run
```

## VSCode Debugging

The project includes VSCode debug configurations in `.vscode/launch.json`. Use the Debug panel (Ctrl+Shift+D) to run pre-configured debug sessions:

- **WorldQuant Alpha - Init** - Initialize database
- **WorldQuant Alpha - Fetch Data** - Fetch fundamental data
- **WorldQuant Alpha - Generate (Template 0-4)** - Generate alphas from specific templates
- **WorldQuant Alpha - Backtest** - Run backtests
- **WorldQuant Alpha - Analyze** - Analyze results
- **WorldQuant Alpha - Pipeline** - Run full pipeline
- **WorldQuant Alpha - Run Full Process** - Continuous execution mode

## Architecture

### Main Components

- **`worldquant_alpha/`** - Main application code (run from this directory)
  - **`wd_lib/`** - Core library for WorldQuant BRAIN API integration
    - **`client.py`** - Main `WorldQuantClient` class providing unified API access
    - **`auth/`** - Session management and authentication
    - **`api/`** - API endpoints (datasets, alphas, simulation)
    - **`alpha/`** - Alpha builder, factory, validator
    - **`backtest/`** - Backtest executor and analyzer
    - **`config/`** - Configuration and settings
    - **`utils/`** - Utilities (exceptions, helpers, retry)
  - **`main.py`** - CLI entry point using Click
  - **`database.py`** - MySQL database operations
  - **`alpha_generator.py`** - Alpha expression generation from templates
  - **`backtest.py`** - Backtest functionality wrapper

### Data Flow

1. `AlphaFactory` generates alpha expressions from templates
2. `AlphaValidator` validates syntax and structure
3. `WorldQuantClient` submits alphas via API
4. Backtest results stored in MySQL database
5. `analyze_results` calculates performance metrics (IR, Sharpe)

### Templates

Templates are defined in `alpha_generator.py` with economic logic:
- **Template 0**: Industry-neutralized residual momentum
- **Template 1**: Analyst expectation steepness
- **Template 2**: Price-volume divergence
- **Template 3**: Macro-factor timing
- **Template 4**: Additional specialized templates

### Configuration

Environment variables in `worldquant_alpha/.env`:
- `WQ_USERNAME`, `WQ_PASSWORD` - WorldQuant credentials
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` - MySQL config
- Optional SMTP settings for email notifications
- `LOG_LEVEL` - Logging level (default: INFO)
