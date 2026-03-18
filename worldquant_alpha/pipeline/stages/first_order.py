"""
一阶生成阶段执行器

从数据字段生成一阶Alpha表达式。
"""

import logging
from typing import List

from .base import StageExecutor, StageResult, PipelineContext
from ..core.alpha_factory import AlphaFactory

try:
    from database import get_session, save_pipeline_alphas, get_untested_pipeline_alphas
except ImportError:
    from worldquant_alpha.database import get_session, save_pipeline_alphas, get_untested_pipeline_alphas

logger = logging.getLogger(__name__)


class FirstOrderExecutor(StageExecutor):
    """一阶生成执行器"""

    def __init__(self):
        super().__init__("first_order")

    def pre_execute(self, context: PipelineContext) -> bool:
        """检查配置是否启用一阶生成"""
        if not context.config.stages.first_order.enabled:
            logger.info("一阶生成已禁用，跳过")
            return False
        return True

    def execute(self, context: PipelineContext) -> StageResult:
        """执行一阶生成"""
        try:
            # 获取配置
            config = context.config.stages.first_order
            data_config = context.config.data
            global_settings = context.config.settings

            # 优先从数据库加载未回测的Alpha
            session = get_session()
            try:
                existing_alphas = get_untested_pipeline_alphas(session, order=1, stage='first_order')
                if existing_alphas:
                    alphas = [alpha.alpha_expression for alpha in existing_alphas]
                    context.first_order_alphas = alphas
                    context.pipeline_alphas = existing_alphas  # 保存数据库对象以便后续更新
                    logger.info(f"从数据库加载了 {len(alphas)} 个未回测的一阶Alpha")
                    return StageResult(
                        success=True,
                        data=alphas,
                        message=f"从数据库加载 {len(alphas)} 个一阶Alpha",
                        metadata={
                            "source": "database",
                            "output_alphas": len(alphas)
                        }
                    )
            except Exception as e:
                logger.warning(f"从数据库加载Alpha失败: {e}，将重新生成")
            finally:
                session.close()

            # 获取数据字段
            if not context.datafields:
                # 如果没有提供数据字段，从API获取
                logger.info("从API获取数据字段...")
                datasets = data_config.datasets
                all_fields = []

                # 构建搜索范围，优先使用配置中的 search_scope，否则使用全局设置
                if data_config.search_scope:
                    search_scope = data_config.search_scope
                else:
                    search_scope = {
                        'instrumentType': global_settings.instrument_type,
                        'region': global_settings.region,
                        'delay': global_settings.delay,
                        'universe': global_settings.universe
                    }
                logger.info(f"数据字段搜索范围: {search_scope}")

                for dataset_id in datasets:
                    try:
                        df = context.client.get_datafields(
                            search_scope=search_scope,
                            dataset_id=dataset_id,
                            field_type="MATRIX"
                        )
                        if not df.empty:
                            fields = df[df['type'] == "MATRIX"]["id"].tolist()
                            all_fields.extend(fields)
                            logger.info(f"数据集 {dataset_id}: 获取 {len(fields)} 个字段")
                    except Exception as e:
                        logger.warning(f"获取数据集 {dataset_id} 失败: {e}")

                context.datafields = all_fields

            if not context.datafields:
                return StageResult(
                    success=False,
                    message="没有可用的数据字段"
                )

            logger.info(f"数据字段数量: {len(context.datafields)}")

            # 预处理数据字段
            processed_fields = AlphaFactory.preprocess_fields(
                context.datafields,
                backfill_days=data_config.preprocessing.backfill_days,
                winsorize_std=data_config.preprocessing.winsorize_std
            )

            # 生成一阶Alpha
            alphas = AlphaFactory.first_order(
                processed_fields,
                config.operations,
                config.time_windows
            )

            # 保存到数据库
            session = get_session()
            try:
                settings = {
                    "region": global_settings.region,
                    "universe": global_settings.universe,
                    "delay": global_settings.delay,
                    "instrumentType": global_settings.instrument_type
                }
                saved_count, skipped_count = save_pipeline_alphas(
                    session, alphas, order=1, stage='first_order', settings=settings
                )
                logger.info(f"保存Alpha到数据库: 新增 {saved_count} 个，跳过 {skipped_count} 个")

                # 重新加载未回测的Alpha
                existing_alphas = get_untested_pipeline_alphas(session, order=1, stage='first_order')
                alphas = [alpha.alpha_expression for alpha in existing_alphas]
                context.pipeline_alphas = existing_alphas
            except Exception as e:
                logger.warning(f"保存Alpha到数据库失败: {e}，使用内存中的Alpha")
            finally:
                session.close()

            context.first_order_alphas = alphas

            # 检查是否生成了Alpha
            if not alphas:
                return StageResult(
                    success=False,
                    message="没有生成任何一阶Alpha，请检查数据字段和配置",
                    metadata={
                        "input_fields": len(processed_fields),
                        "output_alphas": 0
                    }
                )

            return StageResult(
                success=True,
                data=alphas,
                message=f"生成 {len(alphas)} 个一阶Alpha",
                metadata={
                    "input_fields": len(processed_fields),
                    "output_alphas": len(alphas),
                    "source": "generated"
                }
            )

        except Exception as e:
            logger.exception("一阶生成失败")
            return StageResult(
                success=False,
                message=f"生成失败: {str(e)}"
            )
