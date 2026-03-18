# 三阶Alpha生成Pipeline - 技术架构文档

## 1. 系统概述

### 1.1 设计目标

三阶Alpha生成Pipeline是一个专业的量化因子生成与回测系统，基于WorldQuant BRAIN平台API设计，旨在：

- **自动化**：从原始数据字段到可提交Alpha的全流程自动化
- **可配置**：通过YAML配置灵活调整生成策略
- **可扩展**：支持新阶段、新操作符的插件式扩展
- **可靠性**：断点续传、错误重试、状态持久化
- **高效性**：并发回测、智能剪枝、资源优化

### 1.2 核心概念

| 概念 | 说明 |
|------|------|
| **一阶Alpha** | 基于时间序列操作的单因子表达式 (ts_ops) |
| **二阶Alpha** | 基于分组操作的因子 (group_ops) |
| **三阶Alpha** | 基于事件触发的交易信号 (trade_when) |
| **剪枝(Prune)** | 按字段去重，保留Top N的筛选策略 |
| **Neutralization** | 中性化处理 (SUBINDUSTRY/INDUSTRY/MARKET) |

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Pipeline CLI                              │
│  (third-order run/resume/status/validate/reset/list-configs)    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      PipelineEngine                              │
│  - 阶段编排 (Stage Orchestration)                                │
│  - 状态管理 (State Management)                                   │
│  - 配置加载 (Config Loading)                                     │
│  - 客户端初始化 (Client Initialization)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐  ┌────────▼────────┐  ┌──────▼───────┐
│   Stages     │  │  Core Components │  │    Config    │
│  (阶段执行器) │  │   (核心组件)      │  │   (配置系统)  │
└───────┬──────┘  └────────┬────────┘  └──────┬───────┘
        │                   │                   │
   ┌────┴────┐         ┌────┴────┐        ┌────┴────┐
   │         │         │         │        │         │
┌──▼──┐   ┌──▼──┐   ┌──▼──┐   ┌──▼──┐  ┌──▼──┐  ┌──▼──┐
│First │   │Second│   │Alpha │   │Back-│  │YAML │  │Schema│
│Order │   │Order │   │Factory│  │test │  │Loader│  │Valid.│
└──┬───┘   └──┬───┘   └──┬───┘   └──┬──┘  └──┬───┘  └──┬───┘
   │          │          │          │        │         │
┌──▼──┐   ┌──▼──┐   ┌──▼──┐   ┌──▼──┐  ┌──▼──┐  ┌──▼──┐
│Third│   │Filter│   │Pruner│   │State│  │Defau.│  │Custom│
│Order│   │      │   │      │   │     │  │lt    │  │      │
└─────┘   └─────┘   └─────┘   └─────┘  └─────┘  └─────┘
```

### 2.2 模块职责

| 模块 | 职责 | 核心类 |
|------|------|--------|
| **pipeline/engine.py** | 管道引擎，协调各阶段执行 | `PipelineEngine` |
| **pipeline/stages/** | 各阶段执行器实现 | `StageExecutor` 及子类 |
| **pipeline/core/** | 核心功能组件 | `AlphaFactory`, `BacktestManager`, `Pruner`, `State` |
| **pipeline/config/** | 配置加载与验证 | `ConfigLoader`, `PipelineConfig` |
| **pipeline/cli.py** | 命令行接口 | Click命令组 |

## 3. 核心组件设计

### 3.1 PipelineEngine (管道引擎)

```python
class PipelineEngine:
    """三阶Alpha生成Pipeline引擎"""

    # 阶段定义映射
    STAGE_DEFINITIONS = {
        "first_order": (FirstOrderExecutor, {}),
        "first_order_backtest": (BacktestStage, {...}),
        "first_order_filter": (FilterExecutor, {...}),
        # ... 更多阶段
    }

    # 默认执行顺序
    DEFAULT_STAGE_ORDER = [
        "first_order",
        "first_order_backtest",
        "first_order_filter",
        "second_order",
        # ... 完整流程
    ]
```

**核心方法：**
- `run(start_stage, end_stage, force)` - 执行Pipeline
- `resume()` - 从断点恢复
- `status()` - 获取执行状态
- `export_results()` - 导出结果

### 3.2 StageExecutor (阶段执行器基类)

```python
class StageExecutor(ABC):
    """阶段执行器抽象基类"""

    @abstractmethod
    def execute(self, context: PipelineContext) -> StageResult:
        """执行阶段逻辑"""
        pass

    def pre_execute(self, context) -> bool:
        """前置检查"""
        return True

    def post_execute(self, context, result) -> StageResult:
        """后置处理"""
        return result
```

**阶段实现类：**

| 类名 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `FirstOrderExecutor` | 一阶Alpha生成 | 预处理字段 | Alpha表达式列表 |
| `SecondOrderExecutor` | 二阶Alpha生成 | 一阶筛选结果 | 分组Alpha列表 |
| `ThirdOrderExecutor` | 三阶Alpha生成 | 二阶筛选结果 | trade_when Alpha列表 |
| `BacktestStage` | 回测执行 | Alpha列表 | 回测结果列表 |
| `FilterExecutor` | 筛选剪枝 | 回测结果 | 筛选后结果 |

### 3.3 AlphaFactory (Alpha工厂)

```python
class AlphaFactory:
    """Alpha表达式工厂"""

    @staticmethod
    def preprocess_fields(fields, backfill_days=120, winsorize_std=4.0)
        # winsorize(ts_backfill(field, 120), std=4)

    @classmethod
    def first_order(fields, ops, time_windows)
        # 生成一阶Alpha: ts_ops(field, days)

    @classmethod
    def second_order(first_order_alphas, group_ops, region)
        # 生成二阶Alpha: group_ops(alpha, group)

    @classmethod
    def third_order(second_order_alphas, region, entry_events, exit_events)
        # 生成三阶Alpha: trade_when(entry, alpha, exit)
```

**生成逻辑：**

```
一阶生成 (N fields × M ops × K windows):
  Input: [field1, field2, ..., fieldN]
  Output: [
    field1,
    ts_rank(field1, 5), ts_rank(field1, 22), ...,
    ts_zscore(field1, 5), ...,
    ...
  ]

二阶生成 (N alphas × M group_ops × K groups):
  Input: [alpha1, alpha2, ..., alphaN]
  Output: [
    group_rank(alpha1, sector),
    group_neutralize(alpha1, industry),
    ...
  ]

三阶生成 (N alphas × M entry_events × K exit_events):
  Input: [alpha1, alpha2, ..., alphaN]
  Output: [
    trade_when(ts_arg_max(volume,5)==0, alpha1, abs(returns)>0.1),
    trade_when(ts_corr(close,volume,20)<0, alpha1, -1),
    ...
  ]
```

### 3.4 BacktestManager (回测管理器)

**并发控制策略：**

```python
class BacktestManager:
    def __init__(self, max_workers=4, batch_size=10, rate_limit_delay=1.0):
        self.max_workers = max_workers  # 最大并发数
        self.batch_size = batch_size    # 批处理大小
        self.rate_limit_delay = rate_limit_delay  # API限流保护

    def run_concurrent(self, alphas, settings, client):
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交并发任务
            future_to_alpha = {
                executor.submit(self._run_single, alpha, settings, client): alpha
                for alpha in alphas
            }
            # 收集结果
            for future in as_completed(future_to_alpha):
                result = future.result()
                ...
```

**速率限制保护：**
- 指数退避重试机制
- 单线程模式支持 (--mode sequential)
- 超时处理 (20分钟超时保护)

### 3.5 Pruner (剪枝器)

**剪枝策略：**

```python
def prune(alpha_records, prefix, keep_per_field):
    """
    1. 按sharpe降序排序
    2. 提取字段前缀 (如 fnd6_value_001)
    3. 每个字段保留Top N (区分正负sharpe)
    4. 返回剪枝后的列表
    """
    sorted_records = sorted(alpha_records, key=lambda x: x["sharpe"], reverse=True)

    for rec in sorted_records:
        field = extract_field_prefix(rec["expression"], prefix)
        if sharpe < 0:
            field = f"-{field}"  # 负向Alpha单独计数

        if count[field] < keep_per_field:
            output.append(rec)
            count[field] += 1
```

### 3.6 PipelineState (状态管理)

**状态持久化：**

```json
{
  "pipeline_id": "20260318_121253",
  "created_at": "2026-03-18T12:12:53.177443",
  "current_stage": "first_order",
  "stages": {
    "first_order": {
      "name": "first_order",
      "status": "completed",
      "started_at": "2026-03-18T12:13:29.903468",
      "completed_at": "2026-03-18T12:13:49.623703",
      "input_count": 0,
      "output_count": 0,
      "metadata": {
        "input_fields": 574,
        "output_alphas": 29274
      }
    }
  }
}
```

## 4. 数据流设计

### 4.1 Pipeline数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                         数据流 (Data Flow)                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Data Fields                                                        │
│     │                                                               │
│     ▼                                                               │
│  ┌──────────────┐                                                   │
│  │ Preprocess   │  winsorize(ts_backfill(field, 120), std=4)        │
│  └──────┬───────┘                                                   │
│         │ 574 fields                                                │
│         ▼                                                           │
│  ┌──────────────┐                                                   │
│  │ First Order  │  ts_ops(field, days)                              │
│  └──────┬───────┘                                                   │
│         │ 29,274 alphas                                             │
│         ▼                                                           │
│  ┌──────────────┐  ┌─────────────┐                                  │
│  │  Backtest    │──│   Filter    │  sharpe >= 0.7, fitness >= 0.5  │
│  └──────────────┘  └──────┬──────┘                                  │
│                           │ ~2,000 alphas                           │
│                           ▼                                         │
│  ┌──────────────┐                                                   │
│  │ Second Order │  group_ops(alpha, group)                          │
│  └──────┬───────┘                                                   │
│         │ ~100,000 alphas                                           │
│         ▼                                                           │
│  ┌──────────────┐  ┌─────────────┐                                  │
│  │  Backtest    │──│   Filter    │  sharpe >= 1.0, fitness >= 0.7  │
│  └──────────────┘  └──────┬──────┘                                  │
│                           │ ~500 alphas                             │
│                           ▼                                         │
│  ┌──────────────┐                                                   │
│  │ Third Order  │  trade_when(entry, alpha, exit)                   │
│  └──────┬───────┘                                                   │
│         │ ~50,000 alphas                                            │
│         ▼                                                           │
│  ┌──────────────┐  ┌─────────────┐                                  │
│  │  Backtest    │──│   Filter    │  sharpe >= 1.25, fitness >= 1.0 │
│  └──────────────┘  └──────┬──────┘                                  │
│                           │ ~100 alphas                             │
│                           ▼                                         │
│                    ┌─────────────┐                                  │
│                    │   Export    │  CSV/JSON                        │
│                    └─────────────┘                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 PipelineContext (上下文)

```python
@dataclass
class PipelineContext:
    config: PipelineConfig           # 配置对象
    client: WorldQuantClient         # API客户端
    state: PipelineState             # 状态对象

    # 阶段数据
    datafields: List[str]                    # 原始字段
    first_order_alphas: List[str]            # 一阶Alpha
    filtered_first_order: List[Dict]         # 一阶筛选结果
    second_order_alphas: List[str]           # 二阶Alpha
    filtered_second_order: List[Dict]        # 二阶筛选结果
    third_order_alphas: List[str]            # 三阶Alpha
    filtered_third_order: List[Dict]         # 三阶筛选结果

    metadata: Dict[str, Any]         # 全局元数据
```

## 5. 配置系统

### 5.1 配置Schema

```yaml
pipeline:
  name: "三阶Alpha生成Pipeline"
  version: "2.0"

  settings:        # 全局设置
    region: "USA"
    universe: "TOP3000"
    instrument_type: "EQUITY"
    delay: 1

  data:            # 数据配置
    datasets: ["fundamental6", "mdl110"]
    preprocessing:
      backfill_days: 120
      winsorize_std: 4

  stages:          # 阶段配置
    first_order:
      enabled: true
      operations: [ts_rank, ts_zscore, ...]
      time_windows: [5, 22, 66, 120, 240]

    first_order_filter:
      sharpe_threshold: 0.7
      fitness_threshold: 0.5
      prune_keep_per_field: 3

    # ... 更多阶段

  backtest:        # 回测配置
    mode: "concurrent"  # concurrent | sequential
    max_workers: 4
    batch_size: 10
```

### 5.2 预设配置

| 配置文件 | 策略 | Sharpe阈值 | 特点 |
|----------|------|------------|------|
| `third_order_default.yaml` | 平衡 | 0.7/1.0/1.25 | 标准配置 |
| `third_order_aggressive.yaml` | 激进 | 0.5/0.7/1.0 | 更多Alpha，探索性强 |
| `third_order_conservative.yaml` | 保守 | 1.0/1.25/1.5 | 高质量，稳健策略 |

## 6. 扩展性设计

### 6.1 添加新阶段

```python
# 1. 创建执行器
class MyCustomStage(StageExecutor):
    def __init__(self):
        super().__init__("my_custom_stage")

    def execute(self, context: PipelineContext) -> StageResult:
        # 实现逻辑
        return StageResult(success=True, data=result)

# 2. 注册到PipelineEngine
STAGE_DEFINITIONS = {
    "my_custom_stage": (MyCustomStage, {}),
    # ... 其他阶段
}

# 3. 添加到执行顺序
DEFAULT_STAGE_ORDER = [
    "first_order",
    "my_custom_stage",  # 新阶段
    # ...
]
```

### 6.2 添加新操作符

```python
class AlphaFactory:
    CUSTOM_OPS = {
        "my_custom_op": lambda field, days: f"my_custom_op({field}, {days})"
    }

    @classmethod
    def first_order(cls, fields, ops, time_windows):
        for op in ops:
            if op in cls.CUSTOM_OPS:
                # 使用自定义操作符
                alphas.append(cls.CUSTOM_OPS[op](field, window))
```

### 6.3 自定义分组

```python
def _get_groups_for_region(cls, region: str) -> List[str]:
    custom_groups = {
        "MY_REGION": ["custom_group1", "custom_group2"]
    }

    if region in custom_groups:
        groups.extend(custom_groups[region])
```

## 7. 使用指南

### 7.1 基本使用

```bash
# 运行完整Pipeline
python -m main third-order run

# 使用特定配置
python -m main third-order run --config third_order_aggressive.yaml

# 从指定阶段开始
python -m main third-order run --from-stage second_order

# 只运行到指定阶段
python -m main third-order run --to-stage first_order_filter

# 强制重新运行
python -m main third-order run --from-stage first_order --force
```

### 7.2 断点续传

```bash
# 查看状态
python -m main third-order status

# 恢复执行
python -m main third-order resume

# 重置状态
python -m main third-order reset
```

### 7.3 配置验证

```bash
# 验证配置
python -m main third-order validate --config my_config.yaml

# 列出可用配置
python -m main third-order list-configs
```

## 8. 性能优化

### 8.1 并发控制

| 参数 | 说明 | 建议值 |
|------|------|--------|
| `max_workers` | 并发线程数 | 4-6 |
| `batch_size` | 批处理大小 | 10-20 |
| `rate_limit_delay` | 限流延迟 | 1.0-2.0秒 |

### 8.2 内存优化

- 使用生成器处理大量Alpha
- 及时清理中间结果
- 控制剪枝阈值减少数据量

### 8.3 API限流保护

- 指数退避重试
- 429错误自动等待
- 单线程模式备选

## 9. 错误处理

### 9.1 常见错误

| 错误类型 | 原因 | 解决方案 |
|----------|------|----------|
| `ImportError` | 相对导入问题 | 使用绝对导入 |
| `APIError` | API限流或认证失败 | 检查凭据，降低并发 |
| `TimeoutError` | 回测超时 | 调整超时参数或重试 |
| `ValidationError` | 配置验证失败 | 检查YAML格式 |

### 9.2 日志级别

```python
logging.basicConfig(
    level=logging.INFO,  # DEBUG/INFO/WARNING/ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## 10. 总结

三阶Alpha生成Pipeline提供了一个专业、可配置、可扩展的Alpha因子生成框架：

1. **架构清晰**：模块化设计，职责分离
2. **配置灵活**：YAML配置支持多种策略
3. **可靠稳定**：断点续传、错误重试
4. **高效并发**：多线程回测、智能剪枝
5. **易于扩展**：插件式设计，方便添加新功能

---

**文档版本**: 1.0
**最后更新**: 2026-03-18
**作者**: Claude Code
