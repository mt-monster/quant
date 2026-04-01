"""
Pipeline配置Schema定义

使用dataclasses定义配置结构，提供类型安全和验证。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class BacktestMode(str, Enum):
    """回测模式"""
    CONCURRENT = "concurrent"
    SEQUENTIAL = "sequential"


@dataclass
class GlobalSettings:
    """全局设置"""
    region: str = "USA"
    universe: str = "TOP3000"
    instrument_type: str = "EQUITY"
    delay: int = 1


@dataclass
class DataPreprocessingConfig:
    """数据预处理配置"""
    backfill_days: int = 120
    winsorize_std: float = 4.0


@dataclass
class DataConfig:
    """数据配置"""
    datasets: List[str] = field(default_factory=lambda: ["fundamental6"])
    preprocessing: DataPreprocessingConfig = field(default_factory=DataPreprocessingConfig)
    search_scope: Dict[str, Any] = field(default_factory=lambda: {
        "instrumentType": "EQUITY",
        "region": "USA",
        "delay": 1,
        "universe": "TOP3000"
    })


@dataclass
class FirstOrderConfig:
    """一阶生成配置"""
    enabled: bool = True
    operations: List[str] = field(default_factory=lambda: [
        "ts_rank", "ts_zscore", "ts_mean", "ts_std_dev", "ts_delta",
        "ts_sum", "ts_delay", "ts_arg_min", "ts_arg_max", "ts_scale"
    ])
    # 操作优先级权重 (越高越优先生成)
    operation_weights: Dict[str, float] = field(default_factory=lambda: {
        "ts_rank": 1.0,      # 低换手，高fitness
        "ts_arg_max": 0.9,   # 低换手
        "ts_arg_min": 0.9,   # 低换手
        "ts_std_dev": 0.8,   # 中等换手
        "ts_scale": 0.7,     # 中等换手
        "ts_mean": 0.6,      # 中等换手
        "ts_sum": 0.5,       # 中等换手
        "ts_zscore": 0.4,    # 高换手
        "ts_delta": 0.3,     # 高换手
        "ts_delay": 0.2      # 高换手
    })
    time_windows: List[int] = field(default_factory=lambda: [5, 22, 66, 120, 240])
    decay_range: List[int] = field(default_factory=lambda: [0, 6, 12])


@dataclass
class FilterConfig:
    """筛选配置"""
    sharpe_threshold: float = 0.7
    fitness_threshold: float = 0.5
    # 仅用于“进下一阶种子池”的宽松阈值，不影响最终 candidate 标准
    seed_sharpe_threshold: Optional[float] = None
    seed_fitness_threshold: Optional[float] = None
    prune_keep_per_field: int = 3
    # 多维度评分筛选
    use_multi_dimension_score: bool = True
    keep_top_n: int = 100
    seed_keep_top_n: int = 0
    score_weights: Dict[str, float] = field(default_factory=lambda: {
        "sharpe": 0.25,
        "fitness": 0.45,
        "turnover": 0.20,
        "self_corr": 0.10
    })
    # 换手率硬过滤
    max_turnover: float = 0.5
    seed_max_turnover: Optional[float] = None


@dataclass
class SecondOrderConfig:
    """二阶生成配置"""
    enabled: bool = True
    group_operations: List[str] = field(default_factory=lambda: [
        "group_rank", "group_neutralize", "group_zscore", "group_scale"
    ])
    regions: List[str] = field(default_factory=lambda: ["USA"])


@dataclass
class ThirdOrderConfig:
    """三阶生成配置"""
    enabled: bool = True
    entry_events: Dict[str, bool] = field(default_factory=lambda: {
        "volume_breakout": True,
        "price_volume_divergence": True,
        "volatility_breakout": True,
    })
    exit_events: Dict[str, Any] = field(default_factory=lambda: {
        "profit_target": 0.1,
        "stop_loss": -0.05,
        "holding_period": -1  # -1 means no limit
    })


@dataclass
class BacktestSettingsConfig:
    """回测设置配置"""
    truncation: float = 0.08
    pasteurization: str = "ON"
    test_period: str = "P0Y"
    decay: int = 0
    neutralization: str = "SUBINDUSTRY"


@dataclass
class BacktestConfig:
    """回测配置"""
    mode: BacktestMode = BacktestMode.CONCURRENT
    max_workers: int = 4
    batch_size: int = 10
    neutrals: List[str] = field(default_factory=lambda: ["SUBINDUSTRY", "INDUSTRY", "MARKET"])
    settings: BacktestSettingsConfig = field(default_factory=BacktestSettingsConfig)


@dataclass
class OutputConfig:
    """输出配置"""
    save_intermediate: bool = True
    export_csv: bool = True
    email_notification: bool = False


@dataclass
class StagesConfig:
    """阶段配置集合"""
    first_order: FirstOrderConfig = field(default_factory=FirstOrderConfig)
    first_order_filter: FilterConfig = field(default_factory=lambda: FilterConfig(
        sharpe_threshold=0.5,
        fitness_threshold=0.05,
        seed_sharpe_threshold=0.3,
        seed_fitness_threshold=0.02,
        prune_keep_per_field=3,
        use_multi_dimension_score=True,
        keep_top_n=100,
        seed_keep_top_n=500,
        max_turnover=0.5,
        seed_max_turnover=0.6,
        score_weights={"sharpe": 0.25, "fitness": 0.45, "turnover": 0.20, "self_corr": 0.10}
    ))
    second_order: SecondOrderConfig = field(default_factory=SecondOrderConfig)
    second_order_filter: FilterConfig = field(default_factory=lambda: FilterConfig(
        sharpe_threshold=0.7,
        fitness_threshold=0.08,
        prune_keep_per_field=2,
        use_multi_dimension_score=True,
        keep_top_n=50,
        max_turnover=0.4,
        score_weights={"sharpe": 0.25, "fitness": 0.45, "turnover": 0.20, "self_corr": 0.10}
    ))
    third_order: ThirdOrderConfig = field(default_factory=ThirdOrderConfig)
    third_order_filter: FilterConfig = field(default_factory=lambda: FilterConfig(
        sharpe_threshold=1.0,
        fitness_threshold=0.10,
        prune_keep_per_field=1,
        use_multi_dimension_score=True,
        keep_top_n=30,
        max_turnover=0.3,
        score_weights={"sharpe": 0.30, "fitness": 0.45, "turnover": 0.15, "self_corr": 0.10}
    ))


@dataclass
class PipelineConfig:
    """Pipeline完整配置"""
    name: str = "三阶Alpha生成Pipeline"
    version: str = "2.0"
    settings: GlobalSettings = field(default_factory=GlobalSettings)
    data: DataConfig = field(default_factory=DataConfig)
    stages: StagesConfig = field(default_factory=StagesConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        """从字典创建配置"""
        # 处理全局设置
        settings_data = data.get("settings", {})
        settings = GlobalSettings(**settings_data)

        # 处理数据配置
        data_config_data = data.get("data", {})
        preprocessing_data = data_config_data.get("preprocessing", {})
        preprocessing = DataPreprocessingConfig(**preprocessing_data)
        data_config = DataConfig(
            datasets=data_config_data.get("datasets", ["fundamental6"]),
            preprocessing=preprocessing,
            search_scope=data_config_data.get("search_scope", {
                "instrumentType": "EQUITY",
                "region": "USA",
                "delay": 1,
                "universe": "TOP3000"
            })
        )

        # 处理阶段配置
        stages_data = data.get("stages", {})

        # 一阶配置
        first_order_data = stages_data.get("first_order", {})
        first_order = FirstOrderConfig(**first_order_data)

        # 一阶筛选配置
        first_filter_data = stages_data.get("first_order_filter", {})
        first_order_filter = FilterConfig(**first_filter_data)

        # 二阶配置
        second_order_data = stages_data.get("second_order", {})
        second_order = SecondOrderConfig(**second_order_data)

        # 二阶筛选配置
        second_filter_data = stages_data.get("second_order_filter", {})
        second_order_filter = FilterConfig(**second_filter_data)

        # 三阶配置
        third_order_data = stages_data.get("third_order", {})
        third_order = ThirdOrderConfig(**third_order_data)

        # 三阶筛选配置
        third_filter_data = stages_data.get("third_order_filter", {})
        third_order_filter = FilterConfig(**third_filter_data)

        stages = StagesConfig(
            first_order=first_order,
            first_order_filter=first_order_filter,
            second_order=second_order,
            second_order_filter=second_order_filter,
            third_order=third_order,
            third_order_filter=third_order_filter
        )

        # 处理回测配置
        backtest_data = data.get("backtest", {})
        settings_data = backtest_data.get("settings", {})
        backtest_settings = BacktestSettingsConfig(**settings_data)
        backtest = BacktestConfig(
            mode=BacktestMode(backtest_data.get("mode", "concurrent")),
            max_workers=backtest_data.get("max_workers", 4),
            batch_size=backtest_data.get("batch_size", 10),
            neutrals=backtest_data.get("neutrals", ["SUBINDUSTRY", "INDUSTRY", "MARKET"]),
            settings=backtest_settings
        )

        # 处理输出配置
        output_data = data.get("output", {})
        output = OutputConfig(**output_data)

        return cls(
            name=data.get("name", "三阶Alpha生成Pipeline"),
            version=data.get("version", "2.0"),
            settings=settings,
            data=data_config,
            stages=stages,
            backtest=backtest,
            output=output
        )
