# AGENTS.md

## Cursor Cloud specific instructions

This is a small Python quant-analytics project (Python 3.12). There is no test suite, no linter config, and no build step — the "application" is two standalone scripts run directly with `python3`.

- Dependencies install to the user site-packages (`~/.local/...`) via `pip install -r requirements.txt`; there is no virtualenv (the `python3.12-venv` system package is not installed, so `python3 -m venv` fails out of the box). Import as `empyrical` is provided by the `empyrical-reloaded` package (the original `empyrical` is unmaintained and incompatible with numpy 2.x / pandas 3.x).
- `script.py` — offline empyrical calculations (alpha/beta, Sharpe). Run with `python3 script.py`; prints results, no network needed.
- `ratios.py` — fetches US stock data via `akshare` (Eastmoney/Sina endpoints) and generates a QuantStats HTML tearsheet at `output.html`. NOTE: the akshare data hosts (e.g. `63.push2his.eastmoney.com`) are NOT reachable from the Cursor Cloud VM (connection times out / empty reply), so `ratios.py` fails at the data-fetch step here. This is an environment egress limitation, not a code/dependency problem. To verify the QuantStats reporting stack without akshare, feed `qs.reports.html(...)` a locally-generated returns `pd.Series` instead.
- matplotlib prints harmless `findfont: Font family 'Arial' not found` warnings (falls back to the default font); this does not affect report generation.
