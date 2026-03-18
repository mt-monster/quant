# 三阶Alpha生成Pipeline

基于 `third_package` 中的三阶生成逻辑，设计的专业级可配置Pipeline。

## 功能特性

- **配置化**: 通过YAML配置即可调整整个流程
- **可扩展**: 新增阶段只需继承 StageExecutor
- **可靠性**: 断点续传确保长时间运行不中断
- **高效性**: 并发回测提高资源利用率
- **可观测**: 详细的日志和进度追踪

## 三阶生成核心逻辑

### 阶段1: 一阶生成 (First Order)
- **输入**: 预处理后的数据字段
- **操作**: 时间序列操作 `ts_ops(field, days)`
- **操作符**: ts_rank, ts_zscore, ts_mean, ts_std_dev等
- **输出**: 一阶Alpha表达式列表
- **示例**: `ts_rank(winsorize(ts_backfill(field, 120), std=4), 5)`

### 阶段2: 二阶生成 (Second Order)
- **输入**: 一阶筛选结果
- **操作**: 分组操作 `group_ops(first_order_expr, group)`
- **操作符**: group_rank, group_neutralize, group_zscore, group_scale
- **输出**: 二阶Alpha表达式列表
- **示例**: `group_neutralize(ts_rank(...), sector)`

### 阶段3: 三阶生成 (Third Order)
- **输入**: 二阶筛选结果
- **操作**: 事件触发 `trade_when(entry_event, alpha_expr, exit_event)`
- **开仓事件**: 成交量突破、价格-成交量相关性、波动率突破等
- **平仓事件**: 收益达到阈值、持有期满等
- **输出**: 三阶Alpha表达式列表
- **示例**: `trade_when(ts_arg_max(volume, 5) == 0, group_ops(...), abs(returns) > 0.1)`

## 安装依赖

```bash
pip install pyyaml
```

## 使用方法

### 1. 使用默认配置运行

```bash
cd worldquant_alpha
python -m main third-order run
```

### 2. 使用指定配置

```bash
python -m main third-order run --config third_order_aggressive.yaml
```

### 3. 从指定阶段开始

```bash
python -m main third-order run --from-stage second_order
```

### 4. 只运行到指定阶段

```bash
python -m main third-order run --to-stage first_order_filter
```

### 5. 恢复上次的运行

```bash
python -m main third-order resume
```

### 6. 查看运行状态

```bash
python -m main third-order status
```

### 7. 验证配置

```bash
python -m main third-order validate --config third_order_conservative.yaml
```

## 配置文件说明

配置文件位于 `configs/` 目录下：

- `third_order_default.yaml` - 默认配置（平衡模式）
- `third_order_aggressive.yaml` - 激进配置（更多Alpha，更低阈值）
- `third_order_conservative.yaml` - 保守配置（更少Alpha，更高阈值）

### 配置结构

```yaml
pipeline:
  name: "三阶Alpha生成Pipeline"
  version: "2.0"

  # 全局设置
  settings:
    region: "USA"
    universe: "TOP3000"
    instrument_type: "EQUITY"
    delay: 1

  # 数据配置
  data:
    datasets: ["fundamental6", "mdl110", "anl14"]
    preprocessing:
      backfill_days: 120
      winsorize_std: 4

  # 阶段配置
  stages:
    first_order:
      enabled: true
      operations: [ts_rank, ts_zscore, ...]
      time_windows: [5, 22, 66, 120, 240]

    first_order_filter:
      sharpe_threshold: 0.7
      fitness_threshold: 0.5
      prune_keep_per_field: 3

    second_order:
      enabled: true
      group_operations: [group_rank, group_neutralize, ...]

    # ... 更多阶段配置

  # 回测配置
  backtest:
    mode: "concurrent"
    max_workers: 4
    batch_size: 10
```

## 架构设计

### 核心组件

```
pipeline/
├── engine.py              # PipelineEngine - 管道引擎
├── stages/
│   ├── base.py            # StageExecutor 基类
│   ├── first_order.py     # 一阶生成阶段
│   ├── second_order.py    # 二阶生成阶段
│   ├── third_order.py     # 三阶生成阶段
│   ├── filter.py          # 筛选阶段
│   └── backtest.py        # 回测阶段
├── core/
│   ├── alpha_factory.py   # Alpha工厂
│   ├── backtest_mgr.py    # 回测管理器
│   ├── pruner.py          # 剪枝器
│   └── state.py           # 状态管理
└── config/
    ├── loader.py          # 配置加载器
    └── schema.py          # 配置Schema
```

### 数据流

```
数据字段预处理
    ↓
一阶生成 (ts_ops)
    ↓
一阶回测 → 筛选/剪枝
    ↓
二阶生成 (group_ops)
    ↓
二阶回测 → 筛选/剪枝
    ↓
三阶生成 (trade_when)
    ↓
三阶回测 → 筛选/剪枝
    ↓
最终结果导出
```

## 断点续传

Pipeline支持断点续传功能：

1. 每个阶段完成后自动保存状态到 `.pipeline_state.json`
2. 支持从任意阶段恢复执行
3. 使用 `--force` 可以强制重新运行已完成的阶段

## 扩展开发

### 添加新的阶段

1. 继承 `StageExecutor` 基类：

```python
from pipeline.stages.base import StageExecutor, StageResult, PipelineContext

class MyCustomStage(StageExecutor):
    def __init__(self):
        super().__init__("my_custom_stage")

    def execute(self, context: PipelineContext) -> StageResult:
        # 实现阶段逻辑
        # ...
        return StageResult(success=True, data=result)
```

2. 在 `PipelineEngine.STAGE_DEFINITIONS` 中注册新阶段

3. 添加到 `DEFAULT_STAGE_ORDER` 列表中

## 注意事项

1. **API限流**: 并发回测可能触发API限流，可以通过调整 `max_workers` 和 `rate_limit_delay` 控制
2. **内存占用**: 大量Alpha可能占用大量内存，建议合理设置 `batch_size`
3. **状态一致性**: 断点续传时，请确保配置文件和状态文件一致

## License

MIT
