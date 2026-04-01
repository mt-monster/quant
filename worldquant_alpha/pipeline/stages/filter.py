"""
筛选阶段执行器

对回测结果进行筛选和剪枝。
"""

import logging
from typing import List, Dict, Any

from .base import StageExecutor, StageResult, PipelineContext
from ..core.pruner import Pruner
from ..services import CandidateRule

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
            seed_mode = self.filter_config_name == "first_order_filter" and context.config.stages.second_order.enabled
            effective_sharpe = config.seed_sharpe_threshold if seed_mode and config.seed_sharpe_threshold is not None else sharpe_th
            effective_fitness = config.seed_fitness_threshold if seed_mode and config.seed_fitness_threshold is not None else fitness_th
            effective_turnover = config.seed_max_turnover if seed_mode and config.seed_max_turnover is not None else max_turnover
            candidate_rule = CandidateRule(
                sharpe_threshold=effective_sharpe,
                fitness_threshold=effective_fitness,
                max_turnover=effective_turnover,
            )

            backtest_results = getattr(context, self.input_alphas_attr, [])

            logger.info("=" * 60)
            logger.info(f"[筛选阶段] 开始筛选回测结果")
            logger.info(f"[筛选阶段] 筛选前Alpha数量: {len(backtest_results)}")
            if seed_mode:
                logger.info(
                    f"[筛选阶段] 一阶进二阶种子筛选阈值: sharpe >= {effective_sharpe}, "
                    f"fitness >= {effective_fitness}, turnover <= {effective_turnover}"
                )
                logger.info(
                    f"[筛选阶段] 最终 candidate 阈值仍保持独立配置: "
                    f"sharpe >= {sharpe_th}, fitness >= {fitness_th}, turnover <= {max_turnover}"
                )
            else:
                logger.info(f"[筛选阶段] 筛选阈值: sharpe >= {effective_sharpe}, fitness >= {effective_fitness}, turnover <= {effective_turnover}")

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
                    alpha_id = result.get("alpha_id") or result.get("id")
                    normalized_result = result
                else:
                    # 假设是BacktestResult对象
                    sharpe = getattr(result, 'sharpe', 0) or 0
                    fitness = getattr(result, 'fitness', 0) or 0
                    turnover = abs(getattr(result, 'turnover', 0) or 0)
                    alpha_id = getattr(result, 'alpha_id', None) or getattr(result, 'id', None)
                    normalized_result = {
                        "sharpe": sharpe,
                        "fitness": fitness,
                        "turnover": turnover,
                        "self_corr": getattr(result, 'self_corr', None),
                        "checks": getattr(result, 'checks', []),
                        "color": getattr(result, 'color', None),
                    }

                decision = candidate_rule.evaluate(normalized_result)

                # 统一口径：平台 checks 无 FAIL，且通过 sharpe/fitness/turnover/self_corr 阈值
                if decision.candidate:
                    filtered.append(result)
                    filtered_count += 1

                if (idx + 1) % 100 == 0:
                    logger.debug(f"[筛选阶段] 已处理 {idx + 1}/{len(backtest_results)} 个Alpha")

            logger.info(f"[筛选阶段] 阈值筛选完成: 通过 {filtered_count}/{len(backtest_results)} 个Alpha")

            # 根据阶段获取上下文中的控制参数
            # 第一阶段筛选
            if self.filter_config_name == "first_order_filter":
                # ID列表优先于数量限制
                if context.first_order_to_second_ids:
                    logger.info(f"[筛选阶段] 使用指定ID列表筛选: {context.first_order_to_second_ids}")
                    filtered = self._filter_by_ids(filtered, context.first_order_to_second_ids)
                elif context.first_order_to_second_count > 0:
                    logger.info(f"[筛选阶段] 使用数量限制筛选: 取前 {context.first_order_to_second_count} 个")
                    filtered = self._filter_by_count(filtered, context.first_order_to_second_count, score_weights if use_multi_dim else None)
                elif seed_mode and config.seed_keep_top_n > 0:
                    logger.info(f"[筛选阶段] 使用默认一阶种子池限制: 取前 {config.seed_keep_top_n} 个")
                    filtered = self._filter_by_count(filtered, config.seed_keep_top_n, score_weights if use_multi_dim else None)
            
            # 第二阶段筛选
            elif self.filter_config_name == "second_order_filter":
                if context.second_order_to_third_ids:
                    logger.info(f"[筛选阶段] 使用指定ID列表筛选: {context.second_order_to_third_ids}")
                    filtered = self._filter_by_ids(filtered, context.second_order_to_third_ids)
                elif context.second_order_to_third_count > 0:
                    logger.info(f"[筛选阶段] 使用数量限制筛选: 取前 {context.second_order_to_third_count} 个")
                    filtered = self._filter_by_count(filtered, context.second_order_to_third_count, score_weights if use_multi_dim else None)

            # 多维度评分筛选
            if use_multi_dim and filtered:
                logger.info(f"[筛选阶段] 开始多维度评分筛选...")
                scored = []
                for result in filtered:
                    score = self._calculate_alpha_score(result, score_weights)
                    scored.append((score, result))

                scored.sort(reverse=True, key=lambda x: x[0])

                # 避免重复限制：如果已经按数量限制了，不再应用keep_top_n
                already_limited = (
                    (self.filter_config_name == "first_order_filter" and (context.first_order_to_second_ids or context.first_order_to_second_count > 0)) or
                    (self.filter_config_name == "second_order_filter" and (context.second_order_to_third_ids or context.second_order_to_third_count > 0))
                )
                
                if not already_limited and keep_top_n > 0 and len(scored) > keep_top_n:
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
                    "sharpe_threshold": effective_sharpe,
                    "fitness_threshold": effective_fitness,
                    "max_turnover": effective_turnover,
                    "seed_mode": seed_mode,
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

    def _filter_by_ids(self, results: List, ids: List[int]) -> List:
        """根据ID列表筛选结果"""
        filtered = []
        for result in results:
            if isinstance(result, dict):
                alpha_id = result.get("alpha_id") or result.get("id")
            else:
                alpha_id = getattr(result, 'alpha_id', None) or getattr(result, 'id', None)
            
            if alpha_id and alpha_id in ids:
                filtered.append(result)
        
        logger.info(f"[筛选阶段] ID筛选: 从 {len(results)} 中选取 {len(filtered)} 个")
        return filtered

    def _filter_by_count(self, results: List, count: int, score_weights: Dict = None) -> List:
        """根据数量限制筛选结果（取评分最高的）"""
        if len(results) <= count:
            return results
        
        if score_weights:
            # 按评分排序
            scored = []
            for result in results:
                score = self._calculate_alpha_score(result, score_weights)
                scored.append((score, result))
            scored.sort(reverse=True, key=lambda x: x[0])
            return [r for _, r in scored[:count]]
        else:
            # 直接取前N个
            return results[:count]

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
