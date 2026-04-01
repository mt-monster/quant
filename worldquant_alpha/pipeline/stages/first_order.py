"""
一阶生成阶段执行器

从数据字段生成一阶Alpha表达式。
"""

import logging
import re
import hashlib
from typing import List

from .base import StageExecutor, StageResult, PipelineContext
from ..core.alpha_factory import AlphaFactory
from ..services import fetch_dataset_fields

try:
    from database import get_session, save_pipeline_alphas, get_untested_pipeline_alphas, PipelineAlpha
except ImportError:
    from worldquant_alpha.database import get_session, save_pipeline_alphas, get_untested_pipeline_alphas, PipelineAlpha

logger = logging.getLogger(__name__)


def _load_template_manager(dataset_ids: List[str]):
    """按数据集加载最新可用模板文件"""
    try:
        from template_manager import TemplateManager
    except ImportError:
        from worldquant_alpha.template_manager import TemplateManager

    candidate_datasets = [dataset_id for dataset_id in dataset_ids if dataset_id]
    if not candidate_datasets:
        return TemplateManager()

    for dataset_id in candidate_datasets:
        manager = TemplateManager(dataset=dataset_id)
        if manager.get_template(next(iter(manager._templates), "")):
            return manager

        dates = manager.get_available_dates(dataset_id)
        if dates:
            latest_manager = manager.load_from_date(dates[0])
            logger.info(f"[Step 4/6] 加载数据集 {dataset_id} 的最新模板文件: {dates[0]}")
            return latest_manager

    return TemplateManager()


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

            # 检查是否有自定义模板配置或显式 force - 这些场景都应忽略数据库中的现有 pending Alpha
            template_names = context.metadata.get('template_names', [])
            direct_templates = context.metadata.get('templates', [])
            force_regenerate = bool(template_names or direct_templates or context.metadata.get('force'))

            # 优先从数据库加载未回测的Alpha（除非强制重新生成）
            session = get_session()
            try:
                existing_alphas = get_untested_pipeline_alphas(session, order=1, stage='first_order')
                if existing_alphas and not force_regenerate:
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
                elif force_regenerate:
                    logger.info(f"检测到强制重新生成，忽略数据库中的 {len(existing_alphas)} 个现有Alpha")
            except Exception as e:
                logger.warning(f"从数据库加载Alpha失败: {e}，将重新生成")
            finally:
                session.close()

            # 获取数据字段
            if not context.datafields:
                logger.info("[Step 2/6] 从API获取数据字段...")
                datasets = data_config.datasets

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
                logger.info(f"[Step 2/6] 数据字段搜索范围: {search_scope}")
                all_fields = fetch_dataset_fields(
                    client=context.client,
                    datasets=datasets,
                    search_scope=search_scope,
                )

                context.datafields = all_fields
                logger.info(f"[Step 2/6] 数据字段获取完成，共 {len(all_fields)} 个字段")

            if not context.datafields:
                logger.error("[Step 2/6] 没有可用的数据字段")
                return StageResult(
                    success=False,
                    message="没有可用的数据字段"
                )

            logger.info(f"[Step 3/6] 预处理数据字段...")
            processed_fields = AlphaFactory.preprocess_fields(
                context.datafields,
                backfill_days=data_config.preprocessing.backfill_days,
                winsorize_std=data_config.preprocessing.winsorize_std
            )
            logger.info(f"[Step 3/6] 数据字段预处理完成")

            # 检查是否有自定义模板配置
            template_names = context.metadata.get('template_names', [])
            direct_templates = context.metadata.get('templates', [])
            
            if template_names or direct_templates:
                # 使用模板生成模式
                logger.info("[Step 4/6] 使用模板生成Alpha...")
                if template_names:
                    logger.info(f"[Step 4/6] 指定模板: {template_names}")
                if direct_templates:
                    logger.info(f"[Step 4/6] 直接模板数量: {len(direct_templates)}")
                
                alphas = []
                
                # 如果有直接模板表达式
                if direct_templates:
                    alphas.extend(direct_templates)
                    logger.info(f"[Step 4/6] 添加 {len(direct_templates)} 个直接模板Alpha")
                
                # 如果有模板名称，从模板管理器加载
                if template_names:
                    try:
                        manager = _load_template_manager(data_config.datasets)
                        
                        for tmpl_name in template_names:
                            tmpl = manager.get_template(tmpl_name)
                            if tmpl:
                                # 使用模板的dataset获取数据字段
                                if tmpl.dataset and tmpl.dataset not in data_config.datasets:
                                    logger.info(f"[Step 4/6] 切换数据集到: {tmpl.dataset}")
                                    # 临时获取模板指定的数据字段
                                    try:
                                        df = context.client.get_datafields(
                                            search_scope={
                                                'instrumentType': global_settings.instrument_type,
                                                'region': global_settings.region,
                                                'delay': global_settings.delay,
                                                'universe': global_settings.universe
                                            },
                                            dataset_id=tmpl.dataset,
                                            field_type="MATRIX"
                                        )
                                        if not df.empty:
                                            template_fields = df[df['type'] == "MATRIX"]["id"].tolist()
                                            logger.info(f"[Step 4/6] 从数据集 {tmpl.dataset} 获取 {len(template_fields)} 个字段")
                                        else:
                                            template_fields = None
                                    except Exception as field_err:
                                        logger.warning(f"[Step 4/6] 获取模板数据集字段失败: {field_err}")
                                        template_fields = None
                                else:
                                    template_fields = context.datafields
                                
                                generated = AlphaFactory.generate_from_template(tmpl, template_fields)
                                if generated:
                                    alphas.extend(generated)
                                    logger.info(f"[Step 4/6] 模板 '{tmpl.name}' 生成了 {len(generated)} 个Alpha")
                                else:
                                    logger.warning(f"[Step 4/6] 模板 '{tmpl.name}' 未生成任何Alpha")
                            else:
                                logger.warning(f"[Step 4/6] 模板 '{tmpl_name}' 不存在")
                    except Exception as e:
                        logger.warning(f"[Step 4/6] 从模板加载失败: {e}，回退到默认生成模式")
                        alphas = []
                
                if not alphas:
                    logger.warning("[Step 4/6] 模板模式未生成Alpha，回退到默认生成模式")
                    alphas = AlphaFactory.first_order(
                        processed_fields,
                        config.operations,
                        config.time_windows,
                        config.operation_weights
                    )
                else:
                    logger.info(f"[Step 4/6] 模板Alpha生成完成，共 {len(alphas)} 个")
            else:
                # 默认一阶生成模式
                logger.info("[Step 4/6] 开始生成一阶Alpha...")
                alphas = AlphaFactory.first_order(
                    processed_fields,
                    config.operations,
                    config.time_windows,
                    config.operation_weights
                )
                logger.info(f"[Step 4/6] 一阶Alpha生成完成，共 {len(alphas)} 个")

            # 预筛选无效组合
            logger.info("[Step 4.5/6] 预筛选无效组合...")
            promising_alphas = []
            for alpha in alphas:
                # 提取操作名进行判断
                match = re.search(r'^(\w+)\(', alpha)
                if match:
                    op = match.group(1)
                    # 简单检查：必须有函数调用
                    if AlphaFactory._is_promising_for_first_order(alpha):
                        promising_alphas.append(alpha)
                else:
                    promising_alphas.append(alpha)
            alphas = promising_alphas
            logger.info(f"[Step 4.5/6] 预筛选完成，保留 {len(alphas)} 个Alpha")

            # 同源去重
            logger.info("[Step 4.6/6] 同源去重...")
            is_template_mode = bool(template_names or direct_templates)
            alphas = AlphaFactory.deduplicate(alphas, preserve_datafield=is_template_mode)
            logger.info(f"[Step 4.6/6] 去重完成，保留 {len(alphas)} 个Alpha (preserve_datafield={is_template_mode})")

            # 应用第一阶段数量限制
            if context.first_order_limit > 0 and len(alphas) > context.first_order_limit:
                logger.info(f"[Step 4.7/6] 应用数量限制: 从 {len(alphas)} 个限制到 {context.first_order_limit} 个")
                alphas = alphas[:context.first_order_limit]
                logger.info(f"[Step 4.7/6] 数量限制应用完成")

            # 预筛选无效组合
            logger.info("[Step 4.5/6] 预筛选无效组合...")
            promising_alphas = []
            for alpha in alphas:
                # 提取操作名进行判断
                match = re.search(r'^(\w+)\(', alpha)
                if match:
                    op = match.group(1)
                    # 简单检查：必须有函数调用
                    if AlphaFactory._is_promising_for_first_order(alpha):
                        promising_alphas.append(alpha)
                else:
                    promising_alphas.append(alpha)
            alphas = promising_alphas
            logger.info(f"[Step 4.5/6] 预筛选完成，保留 {len(alphas)} 个Alpha")

            # 同源去重
            logger.info("[Step 4.6/6] 同源去重...")
            alphas = AlphaFactory.deduplicate(alphas)
            logger.info(f"[Step 4.6/6] 去重完成，保留 {len(alphas)} 个Alpha")

            logger.info("[Step 5/6] 保存一阶Alpha到数据库...")
            session = get_session()
            try:
                settings = {
                    "region": global_settings.region,
                    "universe": global_settings.universe,
                    "delay": global_settings.delay,
                    "instrumentType": global_settings.instrument_type
                }
                generated_hashes = [
                    hashlib.sha256(alpha_expr.encode()).hexdigest()
                    for alpha_expr in alphas
                ]
                saved_count, skipped_count = save_pipeline_alphas(
                    session,
                    alphas,
                    order=1,
                    stage='first_order',
                    settings=settings,
                    dataset_id=",".join(data_config.datasets),
                )
                logger.info(f"[Step 5/6] 保存到数据库完成: 新增 {saved_count} 个，跳过 {skipped_count} 个")

                # 强制重生成时，只回测本轮生成的Alpha，避免把历史 pending 样本一起带入当前运行
                if force_regenerate:
                    logger.info("[Step 6/6] 仅加载本轮生成的一阶Alpha...")
                    existing_alphas = session.query(PipelineAlpha).filter(
                        PipelineAlpha.order == 1,
                        PipelineAlpha.stage == 'first_order',
                        PipelineAlpha.expression_hash.in_(generated_hashes)
                    ).all()
                else:
                    logger.info("[Step 6/6] 从数据库加载未回测的一阶Alpha...")
                    existing_alphas = get_untested_pipeline_alphas(session, order=1, stage='first_order')
                alphas = [alpha.alpha_expression for alpha in existing_alphas]
                context.pipeline_alphas = existing_alphas
                context.pipeline_alphas_map = {
                    alpha.alpha_expression: alpha.expression_hash
                    for alpha in existing_alphas
                }
                logger.info(f"[Step 6/6] 加载完成，共 {len(alphas)} 个一阶Alpha")
            except Exception as e:
                logger.warning(f"[Step 5/6] 保存一阶Alpha到数据库失败: {e}，使用内存中的Alpha")
            finally:
                session.close()

            context.first_order_alphas = alphas

            if not alphas:
                logger.error("[Step 6/6] 没有生成任何一阶Alpha，一阶生成失败")
                return StageResult(
                    success=False,
                    message="没有生成任何一阶Alpha，请检查数据字段和配置",
                    metadata={
                        "input_fields": len(processed_fields),
                        "output_alphas": 0
                    }
                )

            logger.info(f"[Step 6/6] 一阶生成成功，共 {len(alphas)} 个Alpha")
            logger.info("=" * 60)
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
