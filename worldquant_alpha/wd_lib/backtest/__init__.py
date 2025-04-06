"""
WorldQuant Brain API回测模块
提供Alpha回测功能
"""

from .executor import Backtester, run_backtest
from .analyzer import analyze_backtest_result, calculate_performance_metrics

__all__ = [
    'Backtester',
    'run_backtest',
    'analyze_backtest_result',
    'calculate_performance_metrics'
] 