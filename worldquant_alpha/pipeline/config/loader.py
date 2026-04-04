"""
配置加载器

支持从YAML文件加载配置，并提供默认配置。
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .schema import PipelineConfig

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器"""

    # 默认配置文件名
    DEFAULT_CONFIG_NAME = "third_order_default.yaml"

    def __init__(self, config_dir: str = None):
        """
        初始化配置加载器

        参数:
        - config_dir: 配置文件目录，默认为configs/目录
        """
        if config_dir is None:
            # 获取项目根目录下的configs目录
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            config_dir = project_root / "configs"

        self.config_dir = Path(config_dir)
        logger.debug(f"配置目录: {self.config_dir}")

    def load(self, config_name: str = None) -> PipelineConfig:
        """
        加载配置文件

        参数:
        - config_name: 配置文件名或路径，如果为None则使用默认配置

        返回:
        - PipelineConfig对象
        """
        if config_name is None:
            config_path = self.config_dir / self.DEFAULT_CONFIG_NAME
        elif os.path.isabs(config_name):
            config_path = Path(config_name)
        else:
            config_path = self.config_dir / config_name
            # 如果文件不存在，尝试添加 .yaml 后缀
            if not config_path.exists() and not config_path.suffix:
                config_path_yaml = config_path.with_suffix('.yaml')
                if config_path_yaml.exists():
                    config_path = config_path_yaml

        if not config_path.exists():
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return PipelineConfig()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            logger.info(f"成功加载配置文件: {config_path}")

            # 处理pipeline嵌套结构
            if "pipeline" in data:
                data = data["pipeline"]

            return PipelineConfig.from_dict(data)

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def load_from_dict(self, data: Dict[str, Any]) -> PipelineConfig:
        """
        从字典加载配置

        参数:
        - data: 配置字典

        返回:
        - PipelineConfig对象
        """
        # 处理pipeline嵌套结构
        if "pipeline" in data:
            data = data["pipeline"]

        return PipelineConfig.from_dict(data)

    def save(self, config: PipelineConfig, config_name: str) -> bool:
        """
        保存配置到文件

        参数:
        - config: PipelineConfig对象
        - config_name: 配置文件名

        返回:
        - 是否保存成功
        """
        try:
            config_path = self.config_dir / config_name
            data = self._config_to_dict(config)

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump({"pipeline": data}, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"配置已保存到: {config_path}")
            return True

        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False

    def _config_to_dict(self, config: PipelineConfig) -> Dict[str, Any]:
        """将配置对象转换为字典"""
        return {
            "name": config.name,
            "version": config.version,
            "settings": {
                "region": config.settings.region,
                "universe": config.settings.universe,
                "instrument_type": config.settings.instrument_type,
                "delay": config.settings.delay,
            },
            "data": {
                "datasets": config.data.datasets,
                "preprocessing": {
                    "backfill_days": config.data.preprocessing.backfill_days,
                    "winsorize_std": config.data.preprocessing.winsorize_std,
                }
            },
            "stages": {
                "first_order": {
                    "enabled": config.stages.first_order.enabled,
                    "operations": config.stages.first_order.operations,
                    "time_windows": config.stages.first_order.time_windows,
                    "decay_range": config.stages.first_order.decay_range,
                },
                "first_order_filter": {
                    "sharpe_threshold": config.stages.first_order_filter.sharpe_threshold,
                    "fitness_threshold": config.stages.first_order_filter.fitness_threshold,
                    "seed_sharpe_threshold": config.stages.first_order_filter.seed_sharpe_threshold,
                    "seed_fitness_threshold": config.stages.first_order_filter.seed_fitness_threshold,
                    "prune_keep_per_field": config.stages.first_order_filter.prune_keep_per_field,
                    "seed_keep_top_n": config.stages.first_order_filter.seed_keep_top_n,
                    "max_turnover": config.stages.first_order_filter.max_turnover,
                    "seed_max_turnover": config.stages.first_order_filter.seed_max_turnover,
                },
                "second_order": {
                    "enabled": config.stages.second_order.enabled,
                    "group_operations": config.stages.second_order.group_operations,
                    "regions": config.stages.second_order.regions,
                },
                "second_order_filter": {
                    "sharpe_threshold": config.stages.second_order_filter.sharpe_threshold,
                    "fitness_threshold": config.stages.second_order_filter.fitness_threshold,
                    "prune_keep_per_field": config.stages.second_order_filter.prune_keep_per_field,
                    "max_turnover": config.stages.second_order_filter.max_turnover,
                },
                "third_order": {
                    "enabled": config.stages.third_order.enabled,
                    "entry_events": config.stages.third_order.entry_events,
                    "exit_events": config.stages.third_order.exit_events,
                },
                "third_order_filter": {
                    "sharpe_threshold": config.stages.third_order_filter.sharpe_threshold,
                    "fitness_threshold": config.stages.third_order_filter.fitness_threshold,
                    "prune_keep_per_field": config.stages.third_order_filter.prune_keep_per_field,
                    "max_turnover": config.stages.third_order_filter.max_turnover,
                },
            },
            "backtest": {
                "mode": config.backtest.mode.value,
                "max_workers": config.backtest.max_workers,
                "batch_size": config.backtest.batch_size,
                "neutrals": config.backtest.neutrals,
                "settings": {
                    "truncation": config.backtest.settings.truncation,
                    "pasteurization": config.backtest.settings.pasteurization,
                    "test_period": config.backtest.settings.test_period,
                    "decay": config.backtest.settings.decay,
                    "neutralization": getattr(config.backtest.settings, 'neutralization', None),
                    "theme_field": getattr(config.backtest.settings, 'theme_field', 'theme')
                }
            },
            "output": {
                "save_intermediate": config.output.save_intermediate,
                "export_csv": config.output.export_csv,
                "email_notification": config.output.email_notification,
            }
        }

    def list_configs(self) -> list:
        """
        列出所有可用的配置文件

        返回:
        - 配置文件名列表
        """
        if not self.config_dir.exists():
            return []

        return [f.name for f in self.config_dir.glob("*.yaml")]
