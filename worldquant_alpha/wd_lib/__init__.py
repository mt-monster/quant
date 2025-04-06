"""
WorldQuant Brain API SDK
提供对WorldQuant平台的API调用封装
"""

import logging

# 配置根日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

# 导入客户端类
from .client import WorldQuantClient

# 导入认证模块
from .auth import create_session, refresh_session, get_session, SessionManager

# 导入API模块
from .api import (
    get_datafields, 
    submit_simulation, 
    get_datasets, 
    get_alpha_details,
    update_alpha_properties,
    check_alpha_status,
    get_alphas
)

# 导入回测模块
from .backtest import (
    Backtester, 
    run_backtest,
    analyze_backtest_result,
    calculate_performance_metrics
)

# 导入常量和配置
from .config.constants import (
    REGIONS, 
    INSTRUMENT_TYPES, 
    UNIVERSES, 
    NEUTRALIZATIONS,
    BASIC_OPS,
    TS_OPS,
    OPS_SET,
    ALPHA_COLORS,
    DEFAULT_BACKTEST_SETTINGS
)
from .config.settings import WQConfig

# 导入Alpha相关类
from .alpha.factory import AlphaFactory
from .alpha.builder import AlphaBuilder
from .alpha.validator import AlphaValidator

# 导入工具函数
from .utils.helpers import (
    safe_sleep,
    load_task_pool,
    generate_sim_data
)
from .utils.retry import with_retry
from .utils.exceptions import (
    WQAPIError,
    AuthenticationError,
    SimulationError,
    APIError,
    ValidationError,
    ConfigError
)

__all__ = [
    # 主客户端
    'WorldQuantClient',
    
    # 认证
    'create_session',
    'refresh_session',
    'get_session',
    'SessionManager',
    
    # API功能
    'get_datafields',
    'submit_simulation',
    'get_datasets',
    'get_alpha_details',
    'get_alphas',
    'update_alpha_properties',
    'check_alpha_status',
    
    # 回测
    'Backtester',
    'run_backtest',
    'analyze_backtest_result',
    'calculate_performance_metrics',
    
    # 常量
    'REGIONS',
    'INSTRUMENT_TYPES',
    'UNIVERSES',
    'NEUTRALIZATIONS',
    'BASIC_OPS',
    'TS_OPS',
    'OPS_SET',
    'ALPHA_COLORS',
    'DEFAULT_BACKTEST_SETTINGS',
    
    # 配置
    'WQConfig',
    
    # Alpha工具
    'AlphaFactory',
    'AlphaBuilder',
    'AlphaValidator',
    
    # 工具函数
    'safe_sleep',
    'load_task_pool',
    'generate_sim_data',
    'with_retry',
    
    # 异常类
    'WQAPIError',
    'AuthenticationError',
    'SimulationError',
    'APIError',
    'ValidationError',
    'ConfigError'
]

__version__ = '0.2.0' 