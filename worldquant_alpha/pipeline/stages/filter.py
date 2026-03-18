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
            use_multi_dim = config.use_multi_dimension_score
            keep_top_n = config.keep_top_n
            score_weights = config.score_weights
            max_turnover = config.max_turnover

            backtest_results = getattr(context, self.input_alphas_attr, [])

            logger.info("=" * 60)
            logger.info(f"[筛选阶段] 开始筛选回测结果")
            logger.info(f"[筛选阶段] 筛选前Alpha数量: {len(backtest_results)}")
            logger.info(f"[筛选阶段] 筛选阈值: sharpe >= {sharpe_th}, fitness >= {fitness_th}, turnover <= {max_turnover}")

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
                # 兼容dict和object两种格式
                if isinstance(result, dict):
                    sharpe = result.get("sharpe", 0) or 0
                    fitness = result.get("fitness", 0) or 0
                    turnover = abs(result.get("turnover", 0) or 0)
                else:
                    # 假设是BacktestResult对象
                    sharpe = getattr(result, 'sharpe', 0) or 0
                    fitness = getattr(result, 'fitness', 0) or 0
                    turnover = abs(getattr(result, 'turnover', 0) or 0)

                # 三重过滤：sharpe + fitness + turnover
                if abs(sharpe) >= sharpe_th and abs(fitness) >= fitness_th and turnover <= max_turnover:
                    filtered.append(result)
                    filtered_count += 1

                if (idx + 1) % 100 == 0:
                    logger.debug(f"[筛选阶段] 已处理 {idx + 1}/{len(backtest_results)} 个Alpha")

            logger.info(f"[筛选阶段] 阈值筛选完成: 通过 {filtered_count}/{len(backtest_results)} 个Alpha")

            # 多维度评分筛选
            if use_multi_dim and filtered:
                logger.info(f"[筛选阶段] 开始多维度评分筛选...")
                scored = []
                for result in filtered:
                    score = self._calculate_alpha_score(result, score_weights)
                    scored.append((score, result))

                scored.sort(reverse=True, key=lambda x: x[0])

                if keep_top_n > 0 and len(scored) > keep_top_n:
                    logger.info(f"[筛选阶段] 取Top {keep_top_n} 个Alpha")
                    scored = scored[:keep_top_n]

                filtered = [r for _, r in scored]
                logger.info(f"[筛选阶段] 多维度评分筛选完成，保留 {len(filtered)} 个Alpha")

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
                    "fitness_threshold": fitness_th,
                    "max_turnover": max_turnover,
                    "use_multi_dimension_score": use_multi_dim,
                    "keep_top_n": keep_top_n
                }
            )

        except Exception as e:
            logger.exception("筛选失败")
            return StageResult(
                success=False,
                message=f"筛选失败: {str(e)}"
            )

    def _calculate_alpha_score(self, result: Dict[str, Any], weights: Dict[str, float]) -> float:
        """
        计算Alpha综合评分

        参数:
        - result: 回测结果字典或BacktestResult对象
        - weights: 各维度权重

        返回:
        - 综合评分 (0-1)
        """
        if weights is None:
            weights = {"sharpe": 0.25, "fitness": 0.45, "turnover": 0.20, "self_corr": 0.10}

        # 兼容dict和object两种格式
        if isinstance(result, dict):
            sharpe = result.get("sharpe", 0) or 0
            fitness = result.get("fitness", 0) or 0
            turnover = result.get("turnover", 0) or 0
            self_corr = result.get("self_corr", 0) or 0
        else:
            sharpe = getattr(result, 'sharpe', 0) or 0
            fitness = getattr(result, 'fitness', 0) or 0
            turnover = getattr(result, 'turnover', 0) or 0
            self_corr = getattr(result, 'self_corr', 0) or 0

        # 归一化 (假设范围 -2 到 2)
        norm_sharpe = max(0, min(1, (sharpe + 2) / 4))
        norm_fitness = max(0, min(1, (fitness + 2) / 4))
        norm_turnover = max(0, min(1, 1 - abs(turnover)))  # 低换手好
        norm_self_corr = max(0, min(1, 1 - abs(self_corr)))  # 低自相关好

        score = (
            weights.get("sharpe", 0.25) * norm_sharpe +
            weights.get("fitness", 0.45) * norm_fitness +
            weights.get("turnover", 0.20) * norm_turnover +
            weights.get("self_corr", 0.10) * norm_self_corr
        )
        return score
