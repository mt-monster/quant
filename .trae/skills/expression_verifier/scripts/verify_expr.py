import sys
import json
import os

# Ensure the current directory is in sys.path so we can import validator locally
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from validator import ExpressionValidator
except ImportError as e:
    print(json.dumps({
        "valid": False,
        "errors": [f"Error importing validator module: {e}. Ensure validator.py is in the same directory."],
        "tokens": [],
        "ast": None
    }, ensure_ascii=False))
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "valid": False,
            "errors": ["No expression provided. Usage: python verify_expr.py 'expression'"],
            "tokens": [],
            "ast": None
        }, ensure_ascii=False))
        sys.exit(1)
    
    # Combine arguments in case the expression was split by shell
    expression = " ".join(sys.argv[1:])
    
    try:
        validator = ExpressionValidator()
        result = validator.check_expression(expression)
        
        # Serialize the result to JSON
        # default=str is used to handle objects like tokens or AST nodes that might not be directly serializable
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        
    except Exception as e:
        print(json.dumps({
            "valid": False,
            "errors": [f"Exception during validation: {str(e)}"],
            "tokens": [],
            "ast": None
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
