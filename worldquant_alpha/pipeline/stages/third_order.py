"""
三阶生成阶段执行器

从二阶Alpha生成trade_when事件触发的三阶Alpha。
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

            logger.info("=" * 60)
            logger.info("[Step 1/5] 开始提取二阶Alpha表达式...")
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
            logger.info(f"[Step 1/5] 完成提取二阶Alpha表达式，共 {len(second_order_exprs)} 个")

            logger.info("[Step 2/5] 开始生成三阶Alpha...")
            all_alphas = []
            total_generated = 0
            for region in context.config.stages.second_order.regions:
                logger.info(f"[Step 2/5] 为区域 {region} 生成三阶Alpha...")
                alphas = AlphaFactory.third_order(
                    second_order_exprs,
                    region,
                    config.entry_events,
                    config.exit_events
                )
                total_generated += len(alphas)
                all_alphas.extend(alphas)
                logger.info(f"[Step 2/5] 区域 {region} 生成 {len(alphas)} 个三阶Alpha")
            logger.info(f"[Step 2/5] 三阶Alpha生成完成，共 {total_generated} 个")

            # 同源去重
            logger.info("[Step 2.5/5] 同源去重...")
            all_alphas = AlphaFactory.deduplicate(all_alphas)
            logger.info(f"[Step 2.5/5] 去重完成，保留 {len(all_alphas)} 个三阶Alpha")

            logger.info("[Step 3/5] 开始保存三阶Alpha到数据库...")
            session = get_session()
            try:
                settings = {
                    "region": region,
                    "universe": global_settings.universe,
                    "delay": global_settings.delay,
                    "instrumentType": global_settings.instrument_type
                }
                saved_count, skipped_count = save_pipeline_alphas(
                    session, all_alphas, order=3, stage='third_order', settings=settings
                )
                logger.info(f"[Step 3/5] 保存到数据库完成: 新增 {saved_count} 个，跳过 {skipped_count} 个")

                logger.info("[Step 4/5] 从数据库加载未回测的三阶Alpha...")
                existing_alphas = get_untested_pipeline_alphas(session, order=3, stage='third_order')
                all_alphas = [alpha.alpha_expression for alpha in existing_alphas]
                context.pipeline_alphas = existing_alphas
                logger.info(f"[Step 4/5] 加载完成，共 {len(all_alphas)} 个未回测的三阶Alpha")
            except Exception as e:
                logger.warning(f"[Step 3/5] 保存三阶Alpha到数据库失败: {e}，使用内存中的Alpha")
            finally:
                session.close()

            context.third_order_alphas = all_alphas

            logger.info("[Step 5/5] 检查生成结果...")
            if not all_alphas:
                logger.error("[Step 5/5] 没有生成任何三阶Alpha，三阶生成失败")
                return StageResult(
                    success=False,
                    message="没有生成任何三阶Alpha",
                    metadata={
                        "input_alphas": len(second_order_exprs),
                        "output_alphas": 0
                    }
                )

            logger.info(f"[Step 5/5] 三阶生成成功，共 {len(all_alphas)} 个Alpha")
            logger.info("=" * 60)
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
