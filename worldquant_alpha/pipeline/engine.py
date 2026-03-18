"""
Pipeline引擎

核心引擎，协调各阶段执行，支持断点续传。
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from .config.loader import ConfigLoader
from .config.schema import PipelineConfig
from .core.state import PipelineState
from .stages.base import StageExecutor, StageResult, PipelineContext
from .stages.first_order import FirstOrderExecutor
from .stages.second_order import SecondOrderExecutor
from .stages.third_order import ThirdOrderExecutor
from .stages.filter import FilterExecutor
from .stages.backtest import BacktestStage

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Pipeline统计信息"""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_stages: int = 0
    completed_stages: int = 0
    failed_stages: int = 0
    stage_results: Dict[str, Any] = field(default_factory=dict)


class PipelineEngine:
    """三阶Alpha生成Pipeline引擎"""

    # 阶段定义 (名称 -> (执行器类, 配置参数))
    STAGE_DEFINITIONS = {
        "first_order": (FirstOrderExecutor, {}),
        "first_order_backtest": (BacktestStage, {
            "stage_name": "first_order",
            "input_attr": "first_order_alphas",
            "output_attr": "first_order_results"
        }),
        "first_order_filter": (FilterExecutor, {
            "filter_config_name": "first_order_filter",
            "input_alphas_attr": "first_order_results",
            "output_attr": "filtered_first_order"
        }),
        "second_order": (SecondOrderExecutor, {}),
        "second_order_backtest": (BacktestStage, {
            "stage_name": "second_order",
            "input_attr": "second_order_alphas",
            "output_attr": "second_order_results"
        }),
        "second_order_filter": (FilterExecutor, {
            "filter_config_name": "second_order_filter",
            "input_alphas_attr": "second_order_results",
            "output_attr": "filtered_second_order"
        }),
        "third_order": (ThirdOrderExecutor, {}),
        "third_order_backtest": (BacktestStage, {
            "stage_name": "third_order",
            "input_attr": "third_order_alphas",
            "output_attr": "third_order_results"
        }),
        "third_order_filter": (FilterExecutor, {
            "filter_config_name": "third_order_filter",
            "input_alphas_attr": "third_order_results",
            "output_attr": "filtered_third_order"
        }),
    }

    DEFAULT_STAGE_ORDER = [
        "first_order",
        "first_order_backtest",
        "first_order_filter",
        "second_order",
        "second_order_backtest",
        "second_order_filter",
        "third_order",
        "third_order_backtest",
        "third_order_filter",
    ]

    def __init__(self, config_path: str = None, state_file: str = None):
        """
        初始化Pipeline引擎

        参数:
        - config_path: 配置文件路径
        - state_file: 状态文件路径
        """
        self.loader = ConfigLoader()
        self.config = self.loader.load(config_path)
        self.state = PipelineState.load(state_file) or PipelineState()
        if state_file:
            self.state.set_state_file(state_file)

        self.client = None
        self.context = PipelineContext(config=self.config, state=self.state)
        self.stats = PipelineStats()

        logger.info(f"Pipeline引擎初始化完成: {self.config.name}")

    def _init_client(self):
        """初始化API客户端"""
        if self.client is None:
            try:
                from wd_lib import WorldQuantClient
            except ImportError:
                from worldquant_alpha.wd_lib import WorldQuantClient
            self.client = WorldQuantClient()
            if not self.client.login():
                raise RuntimeError("WorldQuant平台登录失败")
            self.context.client = self.client
            logger.info("API客户端初始化完成")

    def _get_stage_executor(self, stage_name: str) -> Optional[StageExecutor]:
        """获取阶段执行器"""
        if stage_name not in self.STAGE_DEFINITIONS:
            logger.error(f"未知阶段: {stage_name}")
            return None

        executor_class, kwargs = self.STAGE_DEFINITIONS[stage_name]
        return executor_class(**kwargs)

    def run(self, start_stage: str = None, end_stage: str = None, force: bool = False):
        """
        运行Pipeline

        参数:
        - start_stage: 从指定阶段开始，如果为None则从第一个未完成的阶段开始
        - end_stage: 运行到指定阶段结束，如果为None则运行到最后
        - force: 是否强制重新运行已完成的阶段
        """
        self.stats.started_at = datetime.now().isoformat()

        try:
            # 初始化客户端
            self._init_client()

            # 确定阶段顺序
            stage_order = self.DEFAULT_STAGE_ORDER.copy()

            # 处理起始阶段
            if start_stage:
                if start_stage not in stage_order:
                    raise ValueError(f"无效的起始阶段: {start_stage}")
                start_idx = stage_order.index(start_stage)
                stage_order = stage_order[start_idx:]
                logger.info(f"从阶段 {start_stage} 开始执行")

            # 处理结束阶段
            if end_stage:
                if end_stage not in stage_order:
                    raise ValueError(f"无效的结束阶段: {end_stage}")
                end_idx = stage_order.index(end_stage)
                stage_order = stage_order[:end_idx + 1]
                logger.info(f"执行到阶段 {end_stage} 结束")

            self.stats.total_stages = len(stage_order)
            logger.info(f"Pipeline执行计划: {stage_order}")

            # 执行各阶段
            for stage_name in stage_order:
                # 检查是否需要跳过
                if not force and self.state.is_stage_completed(stage_name):
                    logger.info(f"阶段 {stage_name} 已完成，跳过")
                    self.stats.completed_stages += 1
                    continue

                # 执行阶段
                success = self._execute_stage(stage_name)

                if success:
                    self.stats.completed_stages += 1
                else:
                    self.stats.failed_stages += 1
                    logger.error(f"阶段 {stage_name} 执行失败，Pipeline中止")
                    break

            self.stats.completed_at = datetime.now().isoformat()
            self._print_summary()

        except Exception as e:
            logger.exception("Pipeline执行异常")
            raise

    def _execute_stage(self, stage_name: str) -> bool:
        """
        执行单个阶段

        参数:
        - stage_name: 阶段名称

        返回:
        - 是否成功
        """
        logger.info(f"=" * 60)
        logger.info(f"执行阶段: {stage_name}")
        logger.info(f"=" * 60)

        # 获取执行器
        executor = self._get_stage_executor(stage_name)
        if not executor:
            return False

        # 标记阶段开始
        self.state.mark_stage_started(stage_name)

        # 执行阶段
        result = executor.run(self.context)

        # 更新状态
        if result.success:
            self.state.mark_stage_completed(
                stage_name,
                output_count=result.metadata.get("output_count", 0),
                metadata=result.metadata
            )
            self.stats.stage_results[stage_name] = result.metadata
            logger.info(f"阶段 {stage_name} 完成: {result.message}")
        else:
            self.state.mark_stage_failed(stage_name, result.message)
            logger.error(f"阶段 {stage_name} 失败: {result.message}")

        return result.success

    def resume(self):
        """从上次中断处恢复执行"""
        last_completed = self.state.get_last_completed_stage()

        if last_completed:
            # 找到下一个阶段
            stage_order = self.DEFAULT_STAGE_ORDER
            if last_completed in stage_order:
                idx = stage_order.index(last_completed)
                if idx + 1 < len(stage_order):
                    next_stage = stage_order[idx + 1]
                    logger.info(f"从阶段 {next_stage} 恢复执行")
                    self.run(start_stage=next_stage)
                else:
                    logger.info("所有阶段已完成")
            else:
                logger.info("未找到可恢复的阶段，从头开始")
                self.run()
        else:
            logger.info("没有之前的执行记录，从头开始")
            self.run()

    def status(self) -> str:
        """获取Pipeline状态"""
        return self.state.get_summary()

    def reset(self):
        """重置Pipeline状态"""
        self.state.reset()
        self.context = PipelineContext(config=self.config, state=self.state)
        logger.info("Pipeline状态已重置")

    def _print_summary(self):
        """打印执行摘要"""
        logger.info(f"=" * 60)
        logger.info("Pipeline执行摘要")
        logger.info(f"=" * 60)
        logger.info(f"开始时间: {self.stats.started_at}")
        logger.info(f"结束时间: {self.stats.completed_at}")
        logger.info(f"总阶段数: {self.stats.total_stages}")
        logger.info(f"成功阶段: {self.stats.completed_stages}")
        logger.info(f"失败阶段: {self.stats.failed_stages}")

        # 最终结果统计
        if self.context.filtered_third_order:
            logger.info(f"最终三阶Alpha数量: {len(self.context.filtered_third_order)}")
        elif self.context.filtered_second_order:
            logger.info(f"最终二阶Alpha数量: {len(self.context.filtered_second_order)}")
        elif self.context.filtered_first_order:
            logger.info(f"最终一阶Alpha数量: {len(self.context.filtered_first_order)}")

        logger.info(f"=" * 60)

    def export_results(self, output_dir: str = "./results"):
        """导出结果到文件"""
        import json
        import os
        from pathlib import Path

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 导出三阶结果
        if self.context.filtered_third_order:
            path = Path(output_dir) / f"third_order_alphas_{timestamp}.json"
            with open(path, "w") as f:
                json.dump(self.context.filtered_third_order, f, indent=2)
            logger.info(f"三阶结果已导出: {path}")

        # 导出二阶结果
        if self.context.filtered_second_order:
            path = Path(output_dir) / f"second_order_alphas_{timestamp}.json"
            with open(path, "w") as f:
                json.dump(self.context.filtered_second_order, f, indent=2)
            logger.info(f"二阶结果已导出: {path}")
