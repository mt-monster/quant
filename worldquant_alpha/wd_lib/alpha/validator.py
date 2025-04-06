"""
Alpha 验证器模块
提供Alpha表达式的验证功能
"""

import logging
import re
from typing import Tuple, Optional

# 配置日志
logger = logging.getLogger(__name__)

class AlphaValidator:
    """Alpha表达式验证器，提供对表达式的合法性验证"""
    
    @staticmethod
    def validate(expression: str) -> Tuple[bool, Optional[str]]:
        """
        验证Alpha表达式的合法性
        
        参数:
        - expression: Alpha表达式
        
        返回:
        - (是否有效, 错误信息)元组，如果有效则错误信息为None
        """
        if not expression or not isinstance(expression, str):
            return False, "表达式不能为空且必须是字符串"
        
        # 检查括号匹配
        if not AlphaValidator._check_brackets(expression):
            return False, "表达式括号不匹配"
        
        # 检查函数调用格式
        if not AlphaValidator._check_function_calls(expression):
            return False, "表达式函数调用格式不正确"
        
        # 检查操作符
        if not AlphaValidator._check_operators(expression):
            return False, "表达式包含无效操作符"
        
        logger.debug(f"Alpha表达式验证通过: {expression}")
        return True, None
    
    @staticmethod
    def _check_brackets(expression: str) -> bool:
        """检查括号是否匹配"""
        stack = []
        for char in expression:
            if char in "({[":
                stack.append(char)
            elif char in ")}]":
                if not stack:
                    return False
                
                top = stack.pop()
                if (char == ")" and top != "(") or \
                   (char == "}" and top != "{") or \
                   (char == "]" and top != "["):
                    return False
        
        return len(stack) == 0
    
    @staticmethod
    def _check_function_calls(expression: str) -> bool:
        """检查函数调用格式"""
        # 简单检查：函数名后应该跟着括号
        pattern = r'[a-zA-Z_][a-zA-Z0-9_]*\s*\('
        matches = re.findall(pattern, expression)
        
        # 如果有函数调用，其数量应该与左括号的数量匹配
        left_parentheses = expression.count('(')
        return len(matches) <= left_parentheses
    
    @staticmethod
    def _check_operators(expression: str) -> bool:
        """检查表达式中的操作符是否有效"""
        # 简单检查：确保没有连续的操作符（如 +-, */, 等）
        pattern = r'[+\-*/]{2,}'
        return not re.search(pattern, expression) 