"""
筛选阶段执行器

对回测结果进行筛选和剪枝。
"""

import logging
from typing import List, Dict, Any

from .base import StageExecutor, StageResult, PipelineContext
from ..core.pruner import Pruner

logger = logging.getLogger(__name__)


class FilterExecutor(StageExecutor):
    """筛选执行器"""

    def __init__(self, stage_name: str, filter_config_name: str, input_alphas_attr: str, output_attr: str):
        super().__init__(f"filter_{stage_name}")
        self.filter_config_name = filter_config_name
        self.input_alphas_attr = input_alphas_attr
        self.output_attr = output_attr

    def execute(self, context: PipelineContext) -> StageResult:
        """执行筛选"""
        try:
            config = getattr(context.config.stages, self.filter_config_name)
            sharpe_th = config.sharpe_threshold
            fitness_th = config.fitness_threshold
            keep_per_field = config.prune_keep_per_field

            backtest_results = getattr(context, self.input_alphas_attr, [])

            logger.info("=" * 60)
            logger.info(f"[筛选阶段] 开始筛选回测结果")
            logger.info(f"[筛选阶段] 筛选前Alpha数量: {len(backtest_results)}")
            logger.info(f"[筛选阶段] 筛选阈值: sharpe >= {sharpe_th}, fitness >= {fitness_th}")

            if not backtest_results:
                logger.error("[筛选阶段] 没有回测结果可供筛选")
                return StageResult(
                    success=False,
                    message="没有回测结果可供筛选"
                )

            logger.info("[筛选阶段] 开始阈值筛选...")
            filtered = []
            filtered_count = 0
            for idx, result in enumerate(backtest_results):
                sharpe = result.get("sharpe", 0) if isinstance(result, dict) else 0
                fitness = result.get("fitness", 0) if isinstance(result, dict) else 0

                if abs(sharpe) >= sharpe_th and abs(fitness) >= fitness_th:
                    filtered.append(result)
                    filtered_count += 1

                if (idx + 1) % 100 == 0:
                    logger.debug(f"[筛选阶段] 已处理 {idx + 1}/{len(backtest_results)} 个Alpha")

            logger.info(f"[筛选阶段] 阈值筛选完成: 通过 {filtered_count}/{len(backtest_results)} 个Alpha")

            logger.info("[筛选阶段] 开始数据剪枝...")
            # pruner = Pruner()
            # filtered = pruner.prune(filtered, "field_", keep_per_field)

            setattr(context, self.output_attr, filtered)
            logger.info(f"[筛选阶段] 筛选完成，保留 {len(filtered)} 个Alpha")
            logger.info("=" * 60)

            return StageResult(
                success=True,
                data=filtered,
                message=f"筛选后保留 {len(filtered)} 个Alpha",
                metadata={
                    "input_count": len(backtest_results),
                    "output_count": len(filtered),
                    "sharpe_threshold": sharpe_th,
                    "fitness_threshold": fitness_th
                }
            )

        except Exception as e:
            logger.exception("筛选失败")
            return StageResult(
                success=False,
                message=f"筛选失败: {str(e)}"
            )
