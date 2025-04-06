"""
Alpha 构建器模块
提供链式API构建Alpha表达式
"""

import logging
from typing import Any, List, Union

# 配置日志
logger = logging.getLogger(__name__)

class AlphaBuilder:
    """
    Alpha表达式构建器
    提供链式API来构建复杂的Alpha表达式
    """
    
    def __init__(self):
        """初始化Alpha构建器"""
        self.expression = ""
        logger.debug("初始化Alpha构建器")
    
    def field(self, name: str) -> 'AlphaBuilder':
        """
        设置基础字段
        
        参数:
        - name: 字段名称
        
        返回:
        - 构建器实例，用于链式调用
        """
        self.expression = name
        return self
        
    def apply(self, op: str, *args: Any) -> 'AlphaBuilder':
        """
        应用操作符
        
        参数:
        - op: 操作符名称
        - args: 操作符参数
        
        返回:
        - 构建器实例，用于链式调用
        """
        if not self.expression:
            raise ValueError("必须先使用field()方法设置字段")
            
        args_str = ", ".join([str(arg) for arg in args])
        if args_str:
            self.expression = f"{op}({self.expression}, {args_str})"
        else:
            self.expression = f"{op}({self.expression})"
            
        return self
        
    # 基础操作符
    def rank(self) -> 'AlphaBuilder':
        """应用rank操作符"""
        return self.apply("rank")
        
    def zscore(self) -> 'AlphaBuilder':
        """应用zscore操作符"""
        return self.apply("zscore")
        
    def inverse(self) -> 'AlphaBuilder':
        """应用inverse操作符"""
        return self.apply("inverse")
        
    def reverse(self) -> 'AlphaBuilder':
        """应用reverse操作符"""
        return self.apply("reverse")
        
    def quantile(self, bins: int = 10) -> 'AlphaBuilder':
        """应用quantile操作符"""
        return self.apply("quantile", bins)
        
    def normalize(self) -> 'AlphaBuilder':
        """应用normalize操作符"""
        return self.apply("normalize")
        
    # 时间序列操作符
    def ts_mean(self, days: int) -> 'AlphaBuilder':
        """应用ts_mean操作符"""
        return self.apply("ts_mean", days)
        
    def ts_sum(self, days: int) -> 'AlphaBuilder':
        """应用ts_sum操作符"""
        return self.apply("ts_sum", days)
        
    def ts_std_dev(self, days: int) -> 'AlphaBuilder':
        """应用ts_std_dev操作符"""
        return self.apply("ts_std_dev", days)
        
    def ts_delta(self, days: int) -> 'AlphaBuilder':
        """应用ts_delta操作符"""
        return self.apply("ts_delta", days)
        
    def ts_rank(self, days: int) -> 'AlphaBuilder':
        """应用ts_rank操作符"""
        return self.apply("ts_rank", days)
        
    def ts_zscore(self, days: int) -> 'AlphaBuilder':
        """应用ts_zscore操作符"""
        return self.apply("ts_zscore", days)
        
    def ts_delay(self, days: int) -> 'AlphaBuilder':
        """应用ts_delay操作符"""
        return self.apply("ts_delay", days)
        
    def ts_arg_max(self, days: int) -> 'AlphaBuilder':
        """应用ts_arg_max操作符"""
        return self.apply("ts_arg_max", days)
        
    def ts_arg_min(self, days: int) -> 'AlphaBuilder':
        """应用ts_arg_min操作符"""
        return self.apply("ts_arg_min", days)
        
    def ts_scale(self, days: int) -> 'AlphaBuilder':
        """应用ts_scale操作符"""
        return self.apply("ts_scale", days)
        
    def ts_quantile(self, days: int) -> 'AlphaBuilder':
        """应用ts_quantile操作符"""
        return self.apply("ts_quantile", days)
    
    # 组合操作
    def add(self, other: Union[str, 'AlphaBuilder']) -> 'AlphaBuilder':
        """
        加法操作
        
        参数:
        - other: 另一个表达式或构建器
        
        返回:
        - 构建器实例，用于链式调用
        """
        if isinstance(other, AlphaBuilder):
            other = other.build()
        self.expression = f"({self.expression} + {other})"
        return self
        
    def sub(self, other: Union[str, 'AlphaBuilder']) -> 'AlphaBuilder':
        """
        减法操作
        
        参数:
        - other: 另一个表达式或构建器
        
        返回:
        - 构建器实例，用于链式调用
        """
        if isinstance(other, AlphaBuilder):
            other = other.build()
        self.expression = f"({self.expression} - {other})"
        return self
        
    def mul(self, other: Union[str, 'AlphaBuilder']) -> 'AlphaBuilder':
        """
        乘法操作
        
        参数:
        - other: 另一个表达式或构建器
        
        返回:
        - 构建器实例，用于链式调用
        """
        if isinstance(other, AlphaBuilder):
            other = other.build()
        self.expression = f"({self.expression} * {other})"
        return self
        
    def div(self, other: Union[str, 'AlphaBuilder']) -> 'AlphaBuilder':
        """
        除法操作
        
        参数:
        - other: 另一个表达式或构建器
        
        返回:
        - 构建器实例，用于链式调用
        """
        if isinstance(other, AlphaBuilder):
            other = other.build()
        self.expression = f"({self.expression} / {other})"
        return self
    
    def build(self) -> str:
        """
        构建最终的Alpha表达式
        
        返回:
        - Alpha表达式字符串
        """
        if not self.expression:
            raise ValueError("表达式为空，请先设置字段和操作符")
            
        logger.debug(f"构建Alpha表达式: {self.expression}")
        return self.expression 