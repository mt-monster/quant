"""
三阶Alpha生成Pipeline模块

提供可配置、可扩展的三阶Alpha生成和回测Pipeline。

主要组件:
- PipelineEngine: 管道引擎，协调各阶段执行
- StageExecutor: 阶段执行器基类
- AlphaFactory: Alpha表达式工厂
- BacktestManager: 并发回测管理器
- Pruner: Alpha剪枝器

使用示例:
    from pipeline import PipelineEngine

    engine = PipelineEngine("config/third_order_default.yaml")
    engine.run()
"""

from .engine import PipelineEngine, PipelineContext, StageResult
from .stages.base import StageExecutor
from .core.alpha_factory import AlphaFactory
from .core.backtest_mgr import BacktestManager
from .core.pruner import Pruner
from .core.state import PipelineState

__all__ = [
    "PipelineEngine",
    "PipelineContext",
    "StageResult",
    "StageExecutor",
    "AlphaFactory",
    "BacktestManager",
    "Pruner",
    "PipelineState",
]