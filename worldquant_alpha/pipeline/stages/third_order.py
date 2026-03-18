"""
三阶生成阶段执行器

从二阶Alpha生成trade_when事件触发的三阶Alpha。
"""

import logging
from typing import List, Dict, Any

from .base import StageExecutor, StageResult, PipelineContext
from ..core.alpha_factory import AlphaFactory

logger = logging.getLogger(__name__)


class ThirdOrderExecutor(StageExecutor):
    """三阶生成执行器"""

    def __init__(self):
        super().__init__("third_order")

    def pre_execute(self, context: PipelineContext) -> bool:
        """检查配置和输入数据"""
        if not context.config.stages.third_order.enabled:
            logger.info("三阶生成已禁用，跳过")
            return False

        if not context.filtered_second_order:
            logger.error("没有可用的二阶Alpha，请先运行二阶筛选")
            return False

        return True

    def execute(self, context: PipelineContext) -> StageResult:
        """执行三阶生成"""
        try:
            config = context.config.stages.third_order
            global_settings = context.config.settings

            # 从二阶筛选结果中提取表达式
            second_order_exprs = []
            for rec in context.filtered_second_order:
                if isinstance(rec, dict):
                    expr = rec.get("expression", "")
                elif isinstance(rec, (list, tuple)) and len(rec) >= 2:
                    expr = rec[0]
                else:
                    expr = str(rec)

                if expr:
                    second_order_exprs.append(expr)

            logger.info(f"输入二阶Alpha数量: {len(second_order_exprs)}")

            all_alphas = []
            for region in context.config.stages.second_order.regions:
                alphas = AlphaFactory.third_order(
                    second_order_exprs,
                    region,
                    config.entry_events,
                    config.exit_events
                )
                all_alphas.extend(alphas)

            context.third_order_alphas = all_alphas

            return StageResult(
                success=True,
                data=all_alphas,
                message=f"生成 {len(all_alphas)} 个三阶Alpha",
                metadata={
                    "input_alphas": len(second_order_exprs),
                    "output_alphas": len(all_alphas)
                }
            )

        except Exception as e:
            logger.exception("三阶生成失败")
            return StageResult(
                success=False,
                message=f"生成失败: {str(e)}"
            )
