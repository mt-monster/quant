---
name: brain-Calculate-alpha-selfcorrQuick
description: Calculates self-correlation and PPAC (Power Pool Alpha Correlation) for WorldQuant BRAIN alphas Locally, this can be very fast than query the platform via mcp. Use this when the user calculates alpha correlations, checks PPAC.
---

# Alpha Self and PPAC Correlation Calculator

This skill helps calculate self-correlation and PPAC for alphas.
For usage instructions and parameter details, see [reference.md](reference.md).

## Why you would use this skill
- Quickly assess alpha self-correlation and PowerPool Alpha Correlation (PPAC) without platform delays.
- If the self-corr is higher than 0.7, you do not even need to query the production correlation from the platform since it will also be higher than 0.7 and fail the submission test.

## Utility Scripts
To perform the calculation, run the `skill.py` script located in the `scripts` directory.

Example:
```bash
python .claude/skills/brain-calculate-alpha-selfcorrQuick/scripts/skill.py --start-date 01-10 --end-date 01-11 --region IND
```

Ensure dependencies from `.claude/skills/brain-calculate-alpha-selfcorrQuick/scripts/requirements.txt` are installed.