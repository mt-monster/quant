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
            "stage_name": "first_order",
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
            "stage_name": "second_order",
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
            "stage_name": "third_order",
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

    def __init__(self, config_path: str = None, state_file: str = None,
                 first_order_limit: int = 0,
                 first_order_to_second_count: int = 0,
                 first_order_to_second_ids: list = None,
                 second_order_to_third_count: int = 0,
                 second_order_to_third_ids: list = None,
                 third_order_test_ids: list = None,
                 dataset: str = None,
                 region: str = None,
                 universe: str = None,
                 delay: int = None,
                 instrument_type: str = None,
                 template_names: list = None,
                 templates: list = None,
                 operations: list = None,
                 time_windows: list = None):
        """
        初始化Pipeline引擎

        参数:
        - config_path: 配置文件路径
        - state_file: 状态文件路径
        - first_order_limit: 第一阶段生成Alpha数量限制，0表示不限制
        - first_order_to_second_count: 第一阶段到第二阶段的数量，0表示不限制
        - first_order_to_second_ids: 第一阶段到第二阶段的指定ID列表
        - second_order_to_third_count: 第二阶段到第三阶段的数量，0表示不限制
        - second_order_to_third_ids: 第二阶段到第三阶段的指定ID列表
        - third_order_test_ids: 第三阶段测试的指定ID列表
        - dataset: 数据集ID（如 "analyst10", "fundamental6"）
        - region: 地区（如 "USA", "EUR"）
        - universe: 股票池（如 "TOP3000", "TOP2500"）
        - delay: 延迟（如 1）
        - instrument_type: 工具类型（如 "EQUITY"）
        - template_names: 模板名称列表
        - templates: 模板表达式列表（直接传入的模板）
        - operations: 操作符列表
        - time_windows: 时间窗口列表
        """
        self.loader = ConfigLoader()
        self.config = self.loader.load(config_path)
        
        self.state = PipelineState.load(state_file) or PipelineState()
        if state_file:
            self.state.set_state_file(state_file)

        self.client = None
        
        # 初始化阶段控制参数
        from .stages.base import PipelineContext
        self.context = PipelineContext(
            config=self.config,
            state=self.state,
            first_order_limit=first_order_limit,
            first_order_to_second_count=first_order_to_second_count,
            first_order_to_second_ids=first_order_to_second_ids or [],
            second_order_to_third_count=second_order_to_third_count,
            second_order_to_third_ids=second_order_to_third_ids or [],
            third_order_test_ids=third_order_test_ids or []
        )
        
        # 应用命令行参数覆盖配置（覆盖模板、操作符、时间窗口存储到context）
        self._apply_overrides(
            dataset=dataset,
            region=region,
            universe=universe,
            delay=delay,
            instrument_type=instrument_type,
            template_names=template_names,
            templates=templates,
            operations=operations,
            time_windows=time_windows
        )
        
        self.stats = PipelineStats()

        logger.info(f"Pipeline引擎初始化完成: {self.config.name}")
        if dataset:
            logger.info(f"数据集: {dataset}")
        if region:
            logger.info(f"地区: {region}")
        if universe:
            logger.info(f"股票池: {universe}")
        if first_order_limit > 0:
            logger.info(f"第一阶段Alpha数量限制: {first_order_limit}")
        if first_order_to_second_count > 0:
            logger.info(f"第一阶段到第二阶段数量: {first_order_to_second_count}")
        if first_order_to_second_ids:
            logger.info(f"第一阶段到第二阶段指定ID: {first_order_to_second_ids}")
        if second_order_to_third_count > 0:
            logger.info(f"第二阶段到第三阶段数量: {second_order_to_third_count}")
        if second_order_to_third_ids:
            logger.info(f"第二阶段到第三阶段指定ID: {second_order_to_third_ids}")
        if third_order_test_ids:
            logger.info(f"第三阶段测试指定ID: {third_order_test_ids}")
        if template_names:
            logger.info(f"模板名称: {template_names}")
        if templates:
            logger.info(f"模板数量: {len(templates)}")
        if operations:
            logger.info(f"操作符: {operations}")
        if time_windows:
            logger.info(f"时间窗口: {time_windows}")

    def _apply_overrides(self, **kwargs):
        """应用命令行参数覆盖配置"""
        # 覆盖数据集
        if kwargs.get('dataset'):
            self.config.data.datasets = [kwargs['dataset']]
            logger.info(f"配置覆盖: 数据集 -> {kwargs['dataset']}")
        
        # 覆盖全局设置
        if kwargs.get('region'):
            self.config.settings.region = kwargs['region']
            self.config.data.search_scope['region'] = kwargs['region']
            logger.info(f"配置覆盖: 地区 -> {kwargs['region']}")
        
        if kwargs.get('universe'):
            self.config.settings.universe = kwargs['universe']
            self.config.data.search_scope['universe'] = kwargs['universe']
            logger.info(f"配置覆盖: 股票池 -> {kwargs['universe']}")
        
        if kwargs.get('delay') is not None:
            self.config.settings.delay = kwargs['delay']
            self.config.data.search_scope['delay'] = kwargs['delay']
            logger.info(f"配置覆盖: 延迟 -> {kwargs['delay']}")
        
        if kwargs.get('instrument_type'):
            self.config.settings.instrument_type = kwargs['instrument_type']
            self.config.data.search_scope['instrumentType'] = kwargs['instrument_type']
            logger.info(f"配置覆盖: 工具类型 -> {kwargs['instrument_type']}")
        
        # 覆盖模板名称（存储到context.metadata）
        if kwargs.get('template_names'):
            self.context.metadata['template_names'] = kwargs['template_names']
            logger.info(f"配置覆盖: 模板名称 -> {kwargs['template_names']}")
        
        # 覆盖模板表达式（存储到context.metadata）
        if kwargs.get('templates'):
            self.context.metadata['templates'] = kwargs['templates']
            logger.info(f"配置覆盖: 模板数量 -> {len(kwargs['templates'])}")
        
        # 覆盖操作符
        if kwargs.get('operations'):
            self.config.stages.first_order.operations = kwargs['operations']
            logger.info(f"配置覆盖: 操作符 -> {kwargs['operations']}")
        
        # 覆盖时间窗口
        if kwargs.get('time_windows'):
            self.config.stages.first_order.time_windows = kwargs['time_windows']
            logger.info(f"配置覆盖: 时间窗口 -> {kwargs['time_windows']}")

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

            # 如果从 filter 阶段开始，先从数据库加载回测结果并跳过该阶段的执行
            skip_filter_stage = None
            if start_stage and 'filter' in start_stage:
                self._load_backtest_results_from_db(start_stage)
                # 跳过筛选阶段，直接进入下一阶段
                if 'first_order_filter' in stage_order:
                    skip_filter_stage = 'first_order_filter'
                    stage_order = [s for s in stage_order if s != 'first_order_filter']
                    logger.info(f"跳过 {skip_filter_stage}，从 {stage_order[0] if stage_order else '无'} 继续执行")

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

    def _load_backtest_results_from_db(self, start_stage: str):
        """从数据库加载回测结果到上下文"""
        try:
            from worldquant_alpha.database import get_session, PipelineAlpha
            
            session = get_session()
            
            # 根据起始阶段确定加载哪个阶层的回测结果
            if 'third' in start_stage:
                order, results_attr, filter_attr = 3, 'third_order_results', 'filtered_third_order'
            elif 'second' in start_stage:
                order, results_attr, filter_attr = 2, 'second_order_results', 'filtered_second_order'
            else:
                order, results_attr, filter_attr = 1, 'first_order_results', 'filtered_first_order'
            
            # 从数据库加载已完成的回测结果
            completed = session.query(PipelineAlpha).filter(
                PipelineAlpha.backtest_status == 'completed',
                PipelineAlpha.order == order
            ).all()
            
            logger.info(f"从数据库加载 {len(completed)} 个 {order} 阶已完成回测的Alpha")
            
            # 转换为结果格式
            results = []
            for a in completed:
                results.append({
                    'id': a.id,
                    'alpha_id': a.alpha_id,
                    'expression': a.alpha_expression,
                    'sharpe': a.sharpe,
                    'fitness': a.fitness,
                    'turnover': a.turnover,
                    'self_corr': a.self_corr
                })
            
            # 设置到上下文
            setattr(self.context, results_attr, results)
            logger.info(f"已加载 {len(results)} 个回测结果到 context.{results_attr}")
            
            # 如果是 first_order_filter，直接应用宽松筛选并设置到 filtered_first_order
            if filter_attr == 'filtered_first_order':
                sharpe_th = getattr(self.context.config.stages.first_order_filter, 'sharpe_threshold', 0.5)
                fitness_th = getattr(self.context.config.stages.first_order_filter, 'fitness_threshold', 0.3)
                
                # 使用更宽松的条件
                filtered = [r for r in results if r.get('sharpe') and abs(r.get('sharpe', 0)) >= sharpe_th * 0.5]
                logger.info(f"应用宽松筛选 (|sharpe| >= {sharpe_th * 0.5:.2f}): {len(filtered)}/{len(results)} 个通过")
                
                setattr(self.context, 'filtered_first_order', filtered)
                logger.info(f"已设置 {len(filtered)} 个一阶Alpha到 filtered_first_order")
            
        except Exception as e:
            logger.warning(f"从数据库加载回测结果失败: {e}")

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
