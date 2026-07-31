"""
WorldQuant Brain API SDK
提供对WorldQuant平台的API调用封装
"""

import importlib
import logging

# 配置根日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

# 延迟导入 (PEP 562): 按需加载子模块。
# 轻量子包 (如 wd_lib.scan 被 scan_v* 脚本使用) 不应被迫引入 pandas/yaml 等重依赖。
_LAZY_ATTRS = {
    # 主客户端
    'WorldQuantClient': '.client',
    'BrainApiClient': '.client',

    # 认证
    'create_session': '.auth',
    'refresh_session': '.auth',
    'get_session': '.auth',
    'SessionManager': '.auth',

    # API功能
    'get_datafields': '.api',
    'submit_simulation': '.api',
    'get_datasets': '.api',
    'get_alpha_details': '.api',
    'get_alphas': '.api',
    'update_alpha_properties': '.api',
    'check_alpha_status': '.api',

    # 回测
    'Backtester': '.backtest',
    'run_backtest': '.backtest',
    'analyze_backtest_result': '.backtest',
    'calculate_performance_metrics': '.backtest',

    # 常量
    'REGIONS': '.config.constants',
    'INSTRUMENT_TYPES': '.config.constants',
    'UNIVERSES': '.config.constants',
    'NEUTRALIZATIONS': '.config.constants',
    'BASIC_OPS': '.config.constants',
    'TS_OPS': '.config.constants',
    'OPS_SET': '.config.constants',
    'ALPHA_COLORS': '.config.constants',
    'DEFAULT_BACKTEST_SETTINGS': '.config.constants',

    # 配置
    'WQConfig': '.config.settings',

    # Alpha工具
    'AlphaFactory': '.alpha.factory',
    'AlphaBuilder': '.alpha.builder',
    'AlphaValidator': '.alpha.validator',

    # 工具函数
    'safe_sleep': '.utils.helpers',
    'load_task_pool': '.utils.helpers',
    'generate_sim_data': '.utils.helpers',
    'with_retry': '.utils.retry',

    # 异常类
    'WQAPIError': '.utils.exceptions',
    'AuthenticationError': '.utils.exceptions',
    'SimulationError': '.utils.exceptions',
    'APIError': '.utils.exceptions',
    'ValidationError': '.utils.exceptions',
    'ConfigError': '.utils.exceptions',
}

__all__ = list(_LAZY_ATTRS)


def __getattr__(name):
    module_path = _LAZY_ATTRS.get(name)
    if module_path is None:
        raise AttributeError(f"module 'wd_lib' has no attribute {name!r}")
    value = getattr(importlib.import_module(module_path, __name__), name)
    globals()[name] = value  # 缓存, 后续访问不再走 __getattr__
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_ATTRS))


__version__ = '0.2.0'
