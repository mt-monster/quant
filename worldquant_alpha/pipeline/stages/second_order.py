"""
二阶生成阶段执行器

从一阶Alpha生成分组操作后的二阶Alpha。
"""

import logging
from typing import List, Dict, Any

from .base import StageExecutor, StageResult, PipelineContext
from ..core.alpha_factory import AlphaFactory

try:
    from database import get_session, save_pipeline_alphas, get_untested_pipeline_alphas
except ImportError:
    from worldquant_alpha.database import get_session, save_pipeline_alphas, get_untested_pipeline_alphas

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

            logger.info("=" * 60)
            logger.info("[Step 1/5] 开始提取一阶Alpha表达式...")
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
            logger.info(f"[Step 1/5] 完成提取一阶Alpha表达式，共 {len(first_order_exprs)} 个")

            logger.info("[Step 2/5] 开始生成二阶Alpha...")
            all_alphas = []
            total_generated = 0
            for region in config.regions:
                logger.info(f"[Step 2/5] 为区域 {region} 生成二阶Alpha...")
                alphas = AlphaFactory.second_order(
                    first_order_exprs,
                    config.group_operations,
                    region
                )
                total_generated += len(alphas)
                all_alphas.extend(alphas)
                logger.info(f"[Step 2/5] 区域 {region} 生成 {len(alphas)} 个二阶Alpha")
            logger.info(f"[Step 2/5] 二阶Alpha生成完成，共 {total_generated} 个")

            logger.info("[Step 3/5] 开始保存二阶Alpha到数据库...")
            session = get_session()
            try:
                settings = {
                    "region": region,
                    "universe": global_settings.universe,
                    "delay": global_settings.delay,
                    "instrumentType": global_settings.instrument_type
                }
                saved_count, skipped_count = save_pipeline_alphas(
                    session, all_alphas, order=2, stage='second_order', settings=settings
                )
                logger.info(f"[Step 3/5] 保存到数据库完成: 新增 {saved_count} 个，跳过 {skipped_count} 个")

                logger.info("[Step 4/5] 从数据库加载未回测的二阶Alpha...")
                existing_alphas = get_untested_pipeline_alphas(session, order=2, stage='second_order')
                all_alphas = [alpha.alpha_expression for alpha in existing_alphas]
                context.pipeline_alphas = existing_alphas
                logger.info(f"[Step 4/5] 加载完成，共 {len(all_alphas)} 个未回测的二阶Alpha")
            except Exception as e:
                logger.warning(f"[Step 3/5] 保存二阶Alpha到数据库失败: {e}，使用内存中的Alpha")
            finally:
                session.close()

            context.second_order_alphas = all_alphas

            logger.info("[Step 5/5] 检查生成结果...")
            if not all_alphas:
                logger.error("[Step 5/5] 没有生成任何二阶Alpha，二阶生成失败")
                return StageResult(
                    success=False,
                    message="没有生成任何二阶Alpha",
                    metadata={
                        "input_alphas": len(first_order_exprs),
                        "output_alphas": 0
                    }
                )

            logger.info(f"[Step 5/5] 二阶生成成功，共 {len(all_alphas)} 个Alpha")
            logger.info("=" * 60)
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
