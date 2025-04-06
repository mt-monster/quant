"""
WorldQuant Brain API客户端
提供统一的接口访问WorldQuant Brain API
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Tuple
from urllib.parse import urljoin

from .auth import SessionManager, get_session
from .config.settings import WQConfig
from .alpha.builder import AlphaBuilder
from .alpha.factory import AlphaFactory
from .alpha.validator import AlphaValidator

# 导入API模块
from .api.datasets import get_datasets, get_datafields
from .api.simulation import submit_simulation
from .api.alphas import (
    get_alpha_details, 
    update_alpha_properties, 
    check_alpha_status,
    get_alphas,
    process_datafields
)

# 导入回测模块
from .backtest.executor import Backtester, run_backtest
from .backtest.analyzer import analyze_backtest_result, calculate_performance_metrics

from .utils.retry import with_retry
from .utils.exceptions import ValidationError, APIError, AuthenticationError

# 配置日志
logger = logging.getLogger(__name__)

# API基础URL
API_BASE_URL = "https://api.worldquantbrain.com/"

class WorldQuantClient:
    """
    WorldQuant Brain API客户端
    提供对WorldQuant Brain API的所有功能的统一访问接口
    """
    
    def __init__(self, config_file: str = None):
        """
        初始化客户端
        
        参数:
        - config_file: 配置文件路径，如果不提供则使用默认配置
        """
        self.config = WQConfig(config_file)
        self.session_manager = SessionManager()
        self.session = None
        logger.info("WorldQuantClient初始化完成")
    
    def login(self, username: str = None, password: str = None) -> bool:
        """
        登录WorldQuant平台
        
        参数:
        - username: 用户名，如果不提供则从配置或环境变量获取
        - password: 密码，如果不提供则从配置或环境变量获取
        
        返回:
        - 是否登录成功
        """
        try:
            if not username and not password:
                # 如果没有提供用户名和密码，尝试从配置获取
                username, password = self.config.get_credentials()
                
            self.session = self.session_manager.create_session(username, password)
            logger.info("成功登录WorldQuant平台")
            return True
        except AuthenticationError as e:
            logger.error(f"登录失败: {str(e)}")
            return False
    
    def get_datasets(self, instrument_type: str = 'EQUITY', region: str = 'USA', 
                     delay: int = 1, universe: str = 'TOP3000') -> pd.DataFrame:
        """
        获取数据集列表
        
        参数:
        - instrument_type: 工具类型，如'EQUITY'
        - region: 地区，如'USA'
        - delay: 延迟
        - universe: 宇宙，如'TOP3000'
        
        返回:
        - 数据集的DataFrame
        """
        if not self.session:
            self.session = get_session()
            
        return get_datasets(
            session=self.session,
            instrument_type=instrument_type,
            region=region,
            delay=delay,
            universe=universe
        )
    
    def get_datafields(self, search_scope: Dict[str, Any] = None, dataset_id: str = '',
                      search: str = '', field_type: str = None) -> pd.DataFrame:
        """
        获取数据字段
        
        参数:
        - search_scope: 搜索范围参数，默认为None使用默认设置
        - dataset_id: 数据集ID
        - search: 搜索关键词
        - field_type: 字段类型过滤，如"MATRIX"
        
        返回:
        - 数据字段的DataFrame
        """
        if not self.session:
            self.session = get_session()
            
        if search_scope is None:
            search_scope = {
                'instrumentType': 'EQUITY',
                'region': 'USA',
                'delay': 1,
                'universe': 'TOP3000'
            }
            
        return get_datafields(
            search_scope=search_scope,
            dataset_id=dataset_id,
            search=search,
            field_type=field_type,
            session=self.session
        )
    
    def process_datafields(self, datafields_df: pd.DataFrame) -> List[str]:
        """
        处理数据字段DataFrame，生成Alpha友好的字段列表
        
        参数:
        - datafields_df: 数据字段DataFrame
        
        返回:
        - 处理后的字段列表
        """
        return process_datafields(datafields_df)
    
    def get_alphas(self, limit: int = 50, offset: int = 0, 
                  filters: Dict[str, Any] = None) -> pd.DataFrame:
        """
        获取Alpha列表
        
        参数:
        - limit: 每页数量
        - offset: 偏移量
        - filters: 过滤条件
        
        返回:
        - Alpha列表的DataFrame
        """
        if not self.session:
            self.session = get_session()
            
        return get_alphas(
            limit=limit,
            offset=offset,
            filters=filters,
            session=self.session
        )
    
    def submit_simulation(self, simulation_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        提交模拟请求
        
        参数:
        - simulation_data: 模拟请求数据
        
        返回:
        - 成功时返回(True, alpha_id)，失败时返回(False, error_message)
        """
        if not self.session:
            self.session = get_session()
            
        return submit_simulation(
            simulation_data=simulation_data,
            session=self.session
        )
    
    def create_alpha_builder(self) -> AlphaBuilder:
        """
        创建Alpha构建器
        
        返回:
        - Alpha构建器实例
        """
        return AlphaBuilder()
    
    def validate_alpha(self, expression: str) -> Tuple[bool, Optional[str]]:
        """
        验证Alpha表达式
        
        参数:
        - expression: Alpha表达式
        
        返回:
        - (是否有效, 错误信息)元组
        """
        return AlphaValidator.validate(expression)
    
    def create_alpha(self, expression: str, validate: bool = True) -> str:
        """
        创建Alpha
        
        参数:
        - expression: Alpha表达式
        - validate: 是否验证表达式
        
        返回:
        - Alpha表达式
        
        异常:
        - ValidationError: 如果表达式无效且validate=True
        """
        if validate:
            is_valid, error_msg = self.validate_alpha(expression)
            if not is_valid:
                raise ValidationError(error_msg)
        
        return expression
    
    def create_ts_alpha(self, op: str, field: str, days: List[int] = None) -> List[str]:
        """
        创建时间序列Alpha
        
        参数:
        - op: 操作符
        - field: 字段
        - days: 时间周期列表
        
        返回:
        - Alpha表达式列表
        """
        return AlphaFactory.create_ts_alpha(op, field, days)
    
    def create_first_order_alphas(self, fields: List[str], ops_set: List[str] = None) -> List[str]:
        """
        创建一阶Alpha表达式
        
        参数:
        - fields: 字段列表
        - ops_set: 操作符集合
        
        返回:
        - Alpha表达式列表
        """
        return AlphaFactory.create_first_order_alphas(fields, ops_set)
    
    def run_backtest(self, alpha_expression: str, settings: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        运行单个Alpha回测
        
        参数:
        - alpha_expression: Alpha表达式
        - settings: 回测设置，如果为None则使用默认设置
        
        返回:
        - 回测结果字典
        """
        if not self.session:
            self.session = get_session()
            
        # 如果没有提供设置，使用默认设置
        if settings is None:
            settings = self.config.get_default_settings()
            
        # 验证Alpha表达式
        is_valid, error_msg = self.validate_alpha(alpha_expression)
        if not is_valid:
            raise ValidationError(error_msg)
            
        return run_backtest(alpha_expression, settings, self.session)
    
    def run_batch_backtest(self, alpha_expressions: List[str], 
                         settings: Dict[str, Any] = None,
                         max_parallel: int = 5) -> List[Dict[str, Any]]:
        """
        批量运行Alpha回测
        
        参数:
        - alpha_expressions: Alpha表达式列表
        - settings: 回测设置
        - max_parallel: 最大并行回测数量
        
        返回:
        - 回测结果字典列表
        """
        if not self.session:
            self.session = get_session()
            
        # 如果没有提供设置，使用默认设置
        if settings is None:
            settings = self.config.get_default_settings()
            
        # 验证所有Alpha表达式
        valid_alphas = []
        for alpha in alpha_expressions:
            is_valid, error_msg = self.validate_alpha(alpha)
            if is_valid:
                valid_alphas.append(alpha)
            else:
                logger.warning(f"Alpha表达式无效，已跳过: {alpha[:50]}... - {error_msg}")
                
        if not valid_alphas:
            raise ValidationError("没有有效的Alpha表达式")
            
        backtester = Backtester(self.session)
        return backtester.run_batch_backtest(valid_alphas, settings, max_parallel)
    
    def analyze_backtest_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析回测结果
        
        参数:
        - result: 回测结果字典
        
        返回:
        - 分析报告字典
        """
        return analyze_backtest_result(result)
    
    def calculate_performance_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        计算多个Alpha的整体性能指标
        
        参数:
        - results: 回测结果字典列表
        
        返回:
        - 整体性能指标字典
        """
        return calculate_performance_metrics(results)
    
    def check_alpha_status(self, alpha_id: str) -> Tuple[bool, str]:
        """
        检查Alpha状态
        
        参数:
        - alpha_id: Alpha ID
        
        返回:
        - (成功状态, 颜色)元组
        """
        if not self.session:
            self.session = get_session()
            
        return check_alpha_status(alpha_id, self.session)
    
    def update_alpha_properties(self, alpha_id: str, properties: Dict[str, Any]) -> bool:
        """
        更新Alpha属性
        
        参数:
        - alpha_id: Alpha ID
        - properties: 属性字典
        
        返回:
        - 是否更新成功
        """
        if not self.session:
            self.session = get_session()
            
        return update_alpha_properties(alpha_id, properties, self.session)
    
    def get_alpha_details(self, alpha_id: str) -> Dict[str, Any]:
        """
        获取Alpha详情
        
        参数:
        - alpha_id: Alpha ID
        
        返回:
        - Alpha详情字典
        """
        if not self.session:
            self.session = get_session()
            
        try:
            return get_alpha_details(alpha_id, self.session)
        except Exception as e:
            logger.error(f"获取Alpha详情失败: {str(e)}")
            return {}
    
    def get_alpha_check(self, alpha_id: str) -> Dict[str, Any]:
        """
        获取Alpha检查结果
        
        参数:
        - alpha_id: Alpha ID
        
        返回:
        - Alpha检查结果字典
        """
        if not self.session:
            self.session = get_session()
            
        try:
            url = urljoin(API_BASE_URL, f"alphas/{alpha_id}/check")
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取Alpha检查结果失败: {str(e)}")
            return {}
    
    def set_alpha_color(self, alpha_id: str, color: str) -> bool:
        """
        设置Alpha颜色
        
        参数:
        - alpha_id: Alpha ID
        - color: 颜色值，可选值为"GREEN", "BLUE", "YELLOW", "RED"
        
        返回:
        - 是否设置成功
        """
        if not self.session:
            self.session = get_session()
            
        try:
            return update_alpha_properties(alpha_id, {"color": color}, self.session)
        except Exception as e:
            logger.error(f"设置Alpha颜色失败: {str(e)}")
            return False 