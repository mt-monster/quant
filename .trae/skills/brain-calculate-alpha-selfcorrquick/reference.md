# Alpha Self and PPAC Correlation Calculator

Calculates self-correlation and PPAC (Power Pool Alpha Correlation) for WorldQuant BRAIN alphas. This skill combines two local self-correlation calculation codes into a unified, easy-to-use solution for RA (Research Associates).

## Why you would use this skill
- Quickly assess alpha self-correlation and PowerPool Alpha Correlation (PPAC) without platform delays.
- If the self-corr is higher than 0.7, you do not even need to query the production correlation from the platform since it will also be higher than 0.7 and fail the submission test.


## Parameters

- `--start-date`: Start date in MM-DD format (e.g., "01-10"), this defines the beginning of the date range for alpha retrieval, The year is automatically set to the current year. The retrival alphas will be from submitted alphas by yourself and we will calculate self-correlation and PPAC correlation with each of them to check if the new alpha you are testing is highly correlated with any of your existing alphas.
- `--end-date`: End date in MM-DD format (e.g., "01-11"), this defines the end of the date range for alpha retrieval. The year is automatically set to the current year. The retrival alphas will be from submitted alphas by yourself and we will calculate self-correlation and PPAC correlation with each of them to check if the new alpha you are testing is highly correlated with any of your existing alphas.
- `--region`: Market region (e.g., "IND", "USA", "EUR")
- `--sharpe-threshold`: Sharpe ratio threshold (default: -1.0)
- `--fitness-threshold`: Fitness threshold (default: -1.0)
- `--alpha-num`: Number of alphas to retrieve (default: 100)
- `--username`: BRAIN platform email (optional, uses stored credentials if available)
- `--password`: BRAIN platform password (optional, uses stored credentials if available)
- `--output`: Output Excel file name (default: auto-generated)

## Examples

Example:
```bash
python .claude/skills/brain-calculate-alpha-selfcorrQuick/scripts/skill.py --start-date 01-10 --end-date 01-11 --region IND
```

## Implementation Details

This skill performs the following steps:
1. Authenticates with WorldQuant BRAIN API
2. Retrieves eligible alphas based on date range, region, and threshold filters
3. Calculates self-correlation for each alpha
4. Calculates PPAC correlation for each alpha
5. Saves results to an Excel file with comprehensive alpha metrics

The skill outputs:
- Alpha ID and expression
- Check status (Check OK/FAIL)
- Rank based on Sharpe ratio
- Self-correlation and PPAC correlation values
- Turnover, fitness, margin, and other metrics
- Neutralization settings and other configuration details

## Dependencies

- requests
- pandas
- numpy
- tqdm

## Notes

1. Date format is MM-DD, and the year is automatically set to the current year
2. The skill uses stored credentials from BRAIN MCP configuration if available
3. Results are saved as Excel files in the current directory
4. The skill includes progress bars for long-running calculations
5. Both self-correlation and PPAC correlation are calculated for comprehensive analysis
