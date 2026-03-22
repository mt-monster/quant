# Pipeline 命令使用指南

## 概述

Pipeline 是一个三阶 Alpha 生成系统，支持从数据字段生成 Alpha 表达式，经过多阶段筛选和优化，最终产出高质量的 Alpha。

## 基本用法

```bash
python -m worldquant_alpha.pipeline.cli <command> [options]
```

---

## 1. run 命令 - 运行 Pipeline

### 基础参数

| 参数 | 缩写 | 说明 | 示例 |
|------|------|------|------|
| `--config` | `-c` | 配置文件路径 | `-c third_order_default.yaml` |
| `--state-file` | - | 状态文件路径 | `--state-file .pipeline_state.json` |
| `--force` | - | 强制重新运行已完成的阶段 | `--force` |

### 阶段控制

| 参数 | 说明 | 示例 |
|------|------|------|
| `--from-stage` | 从指定阶段开始 | `--from-stage first_order` |
| `--to-stage` | 执行到指定阶段结束 | `--to-stage second_order_backtest` |

**可用阶段：**

| 阶段 | 说明 |
|------|------|
| `first_order` | 一阶 Alpha 生成 |
| `first_order_backtest` | 一阶回测 |
| `first_order_filter` | 一阶筛选 |
| `second_order` | 二阶 Alpha 生成 |
| `second_order_backtest` | 二阶回测 |
| `second_order_filter` | 二阶筛选 |
| `third_order` | 三阶 Alpha 生成 |
| `third_order_backtest` | 三阶回测 |
| `third_order_filter` | 三阶筛选 |

### 数据集配置

| 参数 | 缩写 | 说明 | 示例 |
|------|------|------|------|
| `--dataset` | `-d` | 数据集 ID | `--dataset analyst14` |
| `--region` | `-r` | 地区 | `--region USA` |
| `--universe` | `-u` | 股票池 | `--universe TOP3000` |
| `--delay` | - | 延迟天数 | `--delay 1` |
| `--instrument-type` | - | 工具类型 | `--instrument-type EQUITY` |

### 模板配置

| 参数 | 说明 | 示例 |
|------|------|------|
| `--template-names` | 模板名称（逗号分隔） | `--template-names "EPS Consensus (analyst14)"` |
| `--operations` | 操作符列表 | `--operations ts_rank,delay` |
| `--time-windows` | 时间窗口 | `--time-windows 5,10,20` |

### Alpha 数量控制

| 参数 | 说明 | 示例 |
|------|------|------|
| `--first-order-limit` | 第一阶段生成 Alpha 数量限制 | `--first-order-limit 100` |
| `--first-order-to-second-count` | 第一阶段到第二阶段的数量 | `--first-order-to-second-count 50` |
| `--first-order-to-second-ids` | 第一阶段到第二阶段的指定 ID | `--first-order-to-second-ids "1,2,3"` |
| `--second-order-to-third-count` | 第二阶段到第三阶段的数量 | `--second-order-to-third-count 20` |
| `--second-order-to-third-ids` | 第二阶段到第三阶段的指定 ID | `--second-order-to-third-ids "10,20"` |

---

## 2. 使用示例

### 示例 1：基础运行（默认配置）

```bash
python -m worldquant_alpha.pipeline.cli run
```

### 示例 2：使用模板生成 Alpha

```bash
python -m worldquant_alpha.pipeline.cli run \
  --dataset analyst14 \
  --region USA \
  --universe TOP3000 \
  --delay 1 \
  --template-names "EPS Consensus (analyst14)"
```

### 示例 3：运行指定阶段

```bash
# 只运行一阶生成
python -m worldquant_alpha.pipeline.cli run --to-stage first_order

# 运行一阶生成 + 回测
python -m worldquant_alpha.pipeline.cli run \
  --from-stage first_order \
  --to-stage first_order_backtest

# 从回测开始（跳过已完成的生成阶段）
python -m worldquant_alpha.pipeline.cli run --from-stage first_order_backtest
```

### 示例 4：使用模板 + 强制重新生成

```bash
python -m worldquant_alpha.pipeline.cli run \
  --dataset analyst14 \
  --template-names "Smart Estimate Divergence (analyst14)" \
  --from-stage first_order \
  --to-stage first_order_backtest \
  --force
```

### 示例 5：指定特定 Alpha ID 进行回测

```bash
python -m worldquant_alpha.pipeline.cli run \
  --first-order-to-second-ids "1,2,3,4,5" \
  --from-stage first_order_backtest
```

### 示例 6：使用自定义状态文件

```bash
python -m worldquant_alpha.pipeline.cli run \
  --state-file .pipeline_analyst14_state.json
```

---

## 3. 其他命令

### status - 查看状态

```bash
python -m worldquant_alpha.pipeline.cli status
python -m worldquant_alpha.pipeline.cli status --state-file .pipeline_state.json
```

### resume - 恢复执行

```bash
python -m worldquant_alpha.pipeline.cli resume
```

### reset - 重置状态

```bash
python -m worldquant_alpha.pipeline.cli reset
```

### validate - 验证配置

```bash
python -m worldquant_alpha.pipeline.cli validate --config third_order_default.yaml
```

### list-configs - 列出配置

```bash
python -m worldquant_alpha.pipeline.cli list-configs
```

---

## 4. 模板管理命令

### 模板命令组

```bash
python -m worldquant_alpha.pipeline.cli template <subcommand>
```

### template list - 列出模板

```bash
# 列出所有模板
python -m worldquant_alpha.pipeline.cli template list

# 只显示启用的模板
python -m worldquant_alpha.pipeline.cli template list --enabled-only

# 按标签筛选
python -m worldquant_alpha.pipeline.cli template list --tag analyst14
```

### template show - 显示模板详情

```bash
python -m worldquant_alpha.pipeline.cli template show "EPS Consensus (analyst14)"
```

### template add - 添加模板

```bash
python -m worldquant_alpha.pipeline.cli template add \
  --name "My Template" \
  --template "rank(<field>)" \
  --components '{"<field>": ["field1", "field2"]}' \
  --description "My custom template" \
  --tags "custom,mine" \
  --dataset analyst14
```

### template delete - 删除模板

```bash
python -m worldquant_alpha.pipeline.cli template delete "Template Name"
```

### template enable/disable - 启用/禁用模板

```bash
python -m worldquant_alpha.pipeline.cli template enable "Template Name"
python -m worldquant_alpha.pipeline.cli template disable "Template Name"
```

### template update - 更新模板

```bash
python -m worldquant_alpha.pipeline.cli template update \
  --name "Existing Template" \
  --template "rank(group_zscore(<field>, subindustry))" \
  --components '{"<field>": ["anl14_new_field"]}'
```

### template stats - 模板统计

```bash
python -m worldquant_alpha.pipeline.cli template stats
```

---

## 5. 完整工作流示例

### 完整的三阶 Pipeline

```bash
# 1. 生成一阶 Alpha 并回测
python -m worldquant_alpha.pipeline.cli run \
  --dataset analyst14 \
  --region USA \
  --universe TOP3000 \
  --delay 1 \
  --template-names "EPS Consensus (analyst14)" \
  --first-order-to-second-count 50 \
  --from-stage first_order \
  --to-stage first_order_backtest \
  --state-file .pipeline_state.json

# 2. 生成二阶 Alpha 并回测
python -m worldquant_alpha.pipeline.cli run \
  --from-stage second_order \
  --to-stage second_order_backtest \
  --second-order-to-third-count 20 \
  --state-file .pipeline_state.json

# 3. 生成三阶 Alpha 并回测
python -m worldquant_alpha.pipeline.cli run \
  --from-stage third_order \
  --to-stage third_order_backtest \
  --state-file .pipeline_state.json
```

### 快速模板测试

```bash
# 1. 只生成 Alpha（不回测）
python -m worldquant_alpha.pipeline.cli run \
  --dataset analyst14 \
  --template-names "EPS Consensus (analyst14)" \
  --to-stage first_order \
  --state-file .test_state.json

# 2. 回测已生成的 Alpha
python -m worldquant_alpha.pipeline.cli run \
  --from-stage first_order_backtest \
  --state-file .test_state.json
```

---

## 6. 常见问题

### Q: 如何跳过已完成的阶段？

使用 `--from-stage` 参数指定起始阶段：

```bash
python -m worldquant_alpha.pipeline.cli run --from-stage second_order
```

### Q: 如何强制重新生成 Alpha？

使用 `--force` 参数：

```bash
python -m worldquant_alpha.pipeline.cli run --force
```

### Q: 如何查看有哪些可用模板？

```bash
python -m worldquant_alpha.pipeline.cli template list
```

### Q: 如何限制生成的 Alpha 数量？

使用 `--first-order-limit` 参数：

```bash
python -m worldquant_alpha.pipeline.cli run --first-order-limit 100
```

### Q: 状态文件是什么？

状态文件记录了 Pipeline 的执行进度，用于断点续传和状态恢复。

---

## 7. 配置文件格式

Pipeline 使用 YAML 配置文件，示例：

```yaml
name: "Third Order Alpha Pipeline"
version: "1.0.0"

settings:
  region: USA
  universe: TOP3000
  delay: 1
  instrumentType: EQUITY

data:
  datasets:
    - analyst14
  preprocessing:
    backfill_days: 120
    winsorize_std: 4.0

stages:
  first_order:
    enabled: true
    operations:
      - ts_rank
      - delay
      - ts_backfill
    time_windows:
      - 5
      - 10
      - 20

backtest:
  mode: concurrent
  max_workers: 4
  batch_size: 10
  settings:
    testPeriod: P1Y0M
    truncation: 0.08
    decay: 0
```
