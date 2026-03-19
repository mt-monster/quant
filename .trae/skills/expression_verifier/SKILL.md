---
name: expression_verifier
description: Verify the syntax of an alpha expression irrespective of field existence. Use when checking if an alpha expression string is syntactically valid, has correct function arguments, and properly matched parentheses.
---

# Expression Verifier

This skill verifies the syntax of a mathematical/logical expression using the project's `ExpressionValidator`.

It performs the following checks:
1. **Lexical Analysis**: Identifies valid tokens (operators, functions, variables).
2. **Syntax Analysis**: specific grammar rules.
3. **Function Validation**: checks argument counts and types for supported functions (e.g., `group_sum`, `rank`).
4. **Parenthesis Matching**.

**Note**: This skill **does not** validate whether the data fields (variables) mentioned in the expression actually exist in the database. It only checks if they are used as valid identifiers.

## How to use

To verify an expression, follow these steps:

1.  **Locate the Script**: The verification script is `scripts/verify_expr.py` inside this skill's folder. 
    *   **Context Check**: Because you (Claude) are running in the user's project directory, `scripts/` might not be in the current path.
    *   **Primary Path (Windows)**: Check `%USERPROFILE%\.claude\skills\expression_verifier\scripts\verify_expr.py` first.
    *   **Alternative**: If running as a project skill, check `.claude/skills/expression_verifier/scripts/verify_expr.py`.

2. **Execute**: Run the script using python. Ensure you quote the expression to handle spaces and special characters.

```bash
# Example (adjust path as needed)
python ".claude/skills/expression_verifier/scripts/verify_expr.py" "ts_rank(close, 10)"
```

## Interpreting Results

The script outputs a JSON object.
- If `valid` is `true`, the expression is syntactically correct.
- If `valid` is `false`, check the `errors` list for details.

## Examples

### Check a valid expression
```bash
python scripts/verify_expr.py "rank(close) / ts_delay(open, 5)"
```

### Check an invalid expression
```bash
python scripts/verify_expr.py "rank(close, 5)"  # rank only takes 1 argument usually
```