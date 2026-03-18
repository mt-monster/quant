"""
二阶生成阶段执行器

从一阶Alpha生成分组操作后的二阶Alpha。
"""

import logging
from typing import List, Dict, Any

from .base import StageExecutor, StageResult, PipelineContext
from ..core.alpha_factory import AlphaFactory

logger = logging.getLogger(__name__)


class SecondOrderExecutor(StageExecutor):
    """二阶生成执行器"""

    def __init__(self):
        super().__init__("second_order")

    def pre_execute(self, context: PipelineContext) -> bool:
        """检查配置和输入数据"""
        if not context.config.stages.second_order.enabled:
            logger.info("二阶生成已禁用，跳过")
            return False

        if not context.filtered_first_order:
            logger.error("没有可用的一阶Alpha，请先运行一阶筛选")
            return False

        return True

    def execute(self, context: PipelineContext) -> StageResult:
        """执行二阶生成"""
        try:
            config = context.config.stages.second_order
            global_settings = context.config.settings

            # 从一阶筛选结果中提取表达式
            first_order_exprs = []
            for rec in context.filtered_first_order:
                if isinstance(rec, dict):
                    expr = rec.get("expression", "")
                elif isinstance(rec, (list, tuple)) and len(rec) >= 2:
                    expr = rec[0]
                else:
                    expr = str(rec)

                if expr:
                    first_order_exprs.append(expr)

            logger.info(f"输入一阶Alpha数量: {len(first_order_exprs)}")

            all_alphas = []
            for region in config.regions:
                alphas = AlphaFactory.second_order(
                    first_order_exprs,
                    config.group_operations,
                    region
                )
                all_alphas.extend(alphas)

            context.second_order_alphas = all_alphas

            return StageResult(
                success=True,
                data=all_alphas,
                message=f"生成 {len(all_alphas)} 个二阶Alpha",
                metadata={
                    "input_alphas": len(first_order_exprs),
                    "output_alphas": len(all_alphas),
                    "regions": config.regions
                }
            )

        except Exception as e:
            logger.exception("二阶生成失败")
            return StageResult(
                success=False,
                message=f"生成失败: {str(e)}"
            )
