"""
Alpha 工厂模块
提供创建各种类型 Alpha 表达式的工厂方法
"""

import logging
from typing import List, Dict, Any, Optional, Union

from ..config.constants import BASIC_OPS, TS_OPS, OPS_SET

# 配置日志
logger = logging.getLogger(__name__)

class AlphaFactory:
    """Alpha表达式工厂类，用于生成各种类型的Alpha表达式"""
    
    @staticmethod
    def create_ts_alpha(op: str, field: str, days: List[int] = None) -> List[str]:
        """
        生成时间序列Alpha表达式
        
        参数:
        - op: 操作符名称
        - field: 字段名称
        - days: 时间周期列表，默认为[5, 22, 66, 120, 240]
        
        返回:
        - 时间序列Alpha表达式列表
        """
        if days is None:
            days = [5, 22, 66, 120, 240]
            
        logger.debug(f"生成时间序列Alpha，操作符: {op}, 字段: {field}, 周期: {days}")
        
        return [f"{op}({field}, {day})" for day in days]
    
    @staticmethod
    def create_basic_alpha(op: str, field: str, params: Any = None) -> str:
        """
        生成基础Alpha表达式
        
        参数:
        - op: 操作符名称
        - field: 字段名称
        - params: 额外参数，如果需要的话
        
        返回:
        - 基础Alpha表达式
        """
        logger.debug(f"生成基础Alpha，操作符: {op}, 字段: {field}")
        
        if params is not None:
            return f"{op}({field}, {params})"
        return f"{op}({field})"
    
    @staticmethod
    def create_group_alpha(op: str, field: str, group: str, region: str = None) -> str:
        """
        生成分组Alpha表达式
        
        参数:
        - op: 分组操作符
        - field: 字段名称
        - group: 分组表达式
        - region: 地区代码
        
        返回:
        - 分组Alpha表达式
        """
        logger.debug(f"生成分组Alpha，操作符: {op}, 字段: {field}, 分组: {group}")
        
        if op.startswith("group_vector"):
            return f"{op}({field}, cap, densify({group}))"
        elif op.startswith("group_percentage"):
            return f"{op}({field}, densify({group}), percentage=0.5)"
        else:
            return f"{op}({field}, densify({group}))"
    
    @classmethod
    def create_first_order_alphas(cls, fields: List[str], ops_set: List[str] = None) -> List[str]:
        """
        为字段列表生成一阶Alpha表达式
        
        参数:
        - fields: 字段列表
        - ops_set: 操作符集合，如果为None则使用默认操作符集合
        
        返回:
        - 一阶Alpha表达式列表
        """
        if ops_set is None:
            ops_set = OPS_SET
            
        logger.info(f"为{len(fields)}个字段生成一阶Alpha表达式")
        
        alpha_set = []
        
        for field in fields:
            # 添加原字段
            alpha_set.append(field)
            
            # 对每个字段应用操作符
            for op in ops_set:
                if op.startswith("ts_"):
                    # 时间序列操作符
                    alpha_set.extend(cls.create_ts_alpha(op, field))
                elif op == "signed_power":
                    # 带参数的特殊操作符
                    alpha_set.append(cls.create_basic_alpha(op, field, 2))
                else:
                    # 普通操作符
                    alpha_set.append(cls.create_basic_alpha(op, field))
        
        logger.info(f"共生成{len(alpha_set)}个一阶Alpha表达式")
        return alpha_set 