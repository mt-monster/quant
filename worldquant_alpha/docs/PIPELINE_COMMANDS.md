# Pipeline 命令使用文档

## 概述

本项目提供了一套完整的 Alpha 生成 Pipeline 命令行工具，支持三阶段 Alpha 生成、回测、筛选等功能。

## 命令入口

### 方式一：使用 pipeline.cli 模块

```bash
python -m worldquant_alpha.pipeline.cli <command>
```

### 方式二：使用 main 模块

```bash
python -m worldquant_alpha.main third-order <command>
```

---

## 1. run - 运行 Pipeline

运行完整的三阶 Alpha 生成 Pipeline。

### 基本语法

```bash
python -m worldquant_alpha.pipeline.cli run [OPTIONS]
```

### 参数说明

| 参数 | 简写 | 类型 | 说明 | 示例 |
|------|------|------|------|------|
| `--config` | `-c` | TEXT | 配置文件名或路径 | `third_order_default.yaml` |
| `--from-stage` | - | TEXT | 从指定阶段开始 | `first_order` |
| `--to-stage` | - | TEXT | 执行到指定阶段结束 | `filter_first` |
| `--force` | - | FLAG | 强制重新运行已完成的阶段 | - |
| `--state-file` | - | TEXT | 状态文件路径 | `.pipeline_state.json` |

### 阶段控制参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `--first-order-limit` | INTEGER | 第一阶段生成 Alpha 数量限制，0 表示不限制 |
| `--first-order-to-second-count` | INTEGER | 第一阶段到第二阶段的数量，0 表示不限制 |
| `--first-order-to-second-ids` | TEXT | 第一阶段到第二阶段的指定 Alpha ID（逗号分隔） |
| `--second-order-to-third-count` | INTEGER | 第二阶段到第三阶段的数量，0 表示不限制 |
| `--second-order-to-third-ids` | TEXT | 第二阶段到第三阶段的指定 Alpha ID（逗号分隔） |
| `--third-order-test-ids` | TEXT | 第三阶段测试的指定 Alpha ID（逗号分隔） |

### 数据配置参数

| 参数 | 简写 | 类型 | 说明 | 示例 |
|------|------|------|------|------|
| `--dataset` | `-d` | TEXT | 数据集 ID | `analyst10`, `fundamental6` |
| `--region` | `-r` | TEXT | 地区 | `USA`, `EUR`, `CHN` |
| `--universe` | `-u` | TEXT | 股票池 | `TOP3000`, `TOP2500`, `TOPCS1600` |
| `--delay` | - | INTEGER | 延迟天数（1 或 0） | `1` |
| `--instrument-type` | - | TEXT | 工具类型 | `EQUITY`, `FUTURES` |

### 模板配置参数

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `--template-names` | TEXT | 模板名称（逗号分隔） | `"行业中性化残差动量,分析师预期修正陡度"` |
| `--operations` | TEXT | 操作符列表（逗号分隔） | `"ts_rank,ts_zscore,ts_delta"` |
| `--time-windows` | TEXT | 时间窗口（逗号分隔） | `"5,22,66,120"` |

### 使用示例

```bash
# 基础用法
python -m worldquant_alpha.pipeline.cli run

# 使用指定数据集和地区
python -m worldquant_alpha.pipeline.cli run --dataset analyst10 --region EUR --universe TOPCS1600

# 指定模板
python -m worldquant_alpha.pipeline.cli run --dataset analyst10 --template-names "行业中性化残差动量,分析师预期修正陡度"

# 指定操作符和时间窗口
python -m worldquant_alpha.pipeline.cli run --dataset analyst10 --operations "ts_rank,ts_zscore,ts_delta" --time-windows "5,22,66"

# 限制第一阶段生成 300 个 Alpha
python -m worldquant_alpha.pipeline.cli run --first-order-limit 300

# 第一阶段生成后取 200 个进入第二阶段
python -m worldquant_alpha.pipeline.cli run --first-order-limit 300 --first-order-to-second-count 200

# 指定特定 ID 进入下一阶段
python -m worldquant_alpha.pipeline.cli run --first-order-to-second-ids "1,2,3,4,5"

# 完整示例
python -m worldquant_alpha.pipeline.cli run \
  --dataset analyst10 \
  --region EUR \
  --universe TOPCS1600 \
  --delay 1 \
  --first-order-limit 500 \
  --first-order-to-second-count 200 \
  --second-order-to-third-count 100
```

---

## 2. template - Alpha 模板管理

管理 Alpha 模板的子命令组。

### 基本语法

```bash
python -m worldquant_alpha.pipeline.cli template <subcommand>
```

### 子命令列表

| 命令 | 说明 |
|------|------|
| `list` | 列出所有模板 |
| `add` | 添加新模板 |
| `show` | 显示模板详情 |
| `delete` | 删除模板 |
| `enable` | 启用模板 |
| `disable` | 禁用模板 |
| `export` | 导出模板为 Python 代码 |
| `stats` | 显示模板统计信息 |

---

### 2.1 template list - 列出所有模板

```bash
python -m worldquant_alpha.pipeline.cli template list [OPTIONS]
```

**选项：**
- `--enabled-only`: 只显示启用的模板
- `--tag`: 按标签筛选

**示例：**

```bash
# 列出所有模板
python -m worldquant_alpha.pipeline.cli template list

# 只显示启用的模板
python -m worldquant_alpha.pipeline.cli template list --enabled-only

# 按标签筛选
python -m worldquant_alpha.pipeline.cli template list --tag analyst10
```

---

### 2.2 template add - 添加新模板

```bash
python -m worldquant_alpha.pipeline.cli template add [OPTIONS]
```

**选项：**
- `--name`, `-n`: 模板名称（必需）
- `--template`, `-t`: 模板表达式（必需，使用 `<component>` 作为占位符）
- `--components`, `-c`: 组件 JSON 字符串（必需）
- `--description`, `-d`: 模板描述
- `--tags`: 标签（逗号分隔）
- `--dataset`: 数据集 ID（默认: `analyst10`）

**示例：**

```bash
# 通过 Python 添加（推荐，因为 JSON 转义更简单）
python -c "from worldquant_alpha.template_manager import AlphaTemplateConfig, TemplateManager; \
m = TemplateManager(); \
t = AlphaTemplateConfig(name='我的模板', template='ts_rank(<field>, <window>)', \
components={'<field>': ['close', 'vwap'], '<window>': [5, 10, 22]}, \
description='简单时间序列排名Alpha', tags=['simple', 'ts_rank']); \
print(m.add_template(t))"
```

---

### 2.3 template show - 显示模板详情

```bash
python -m worldquant_alpha.pipeline.cli template show <name>
```

**参数：**
- `name`: 模板名称

**示例：**

```bash
python -m worldquant_alpha.pipeline.cli template show "Smart Estimate Divergence"
```

---

### 2.4 template delete - 删除模板

```bash
python -m worldquant_alpha.pipeline.cli template delete <name>
```

**参数：**
- `name`: 模板名称

**示例：**

```bash
python -m worldquant_alpha.pipeline.cli template delete "我的模板"
```

---

### 2.5 template enable - 启用模板

```bash
python -m worldquant_alpha.pipeline.cli template enable <name>
```

**参数：**
- `name`: 模板名称

**示例：**

```bash
python -m worldquant_alpha.pipeline.cli template enable "我的模板"
```

---

### 2.6 template disable - 禁用模板

```bash
python -m worldquant_alpha.pipeline.cli template disable <name>
```

**参数：**
- `name`: 模板名称

**示例：**

```bash
python -m worldquant_alpha.pipeline.cli template disable "我的模板"
```

---

### 2.7 template export - 导出模板

```bash
python -m worldquant_alpha.pipeline.cli template export <name>
```

**参数：**
- `name`: 模板名称

**示例：**

```bash
python -m worldquant_alpha.pipeline.cli template export "Smart Estimate Divergence"
```

---

### 2.8 template stats - 显示统计信息

```bash
python -m worldquant_alpha.pipeline.cli template stats
```

**示例：**

```bash
python -m worldquant_alpha.pipeline.cli template stats
```

---

## 3. 其他命令

### 3.1 status - 查看 Pipeline 状态

```bash
python -m worldquant_alpha.pipeline.cli status [--state-file TEXT]
```

### 3.2 resume - 恢复 Pipeline 执行

```bash
python -m worldquant_alpha.pipeline.cli resume [--state-file TEXT]
```

### 3.3 reset - 重置 Pipeline 状态

```bash
python -m worldquant_alpha.pipeline.cli reset [--state-file TEXT]
```

### 3.4 validate - 验证配置文件

```bash
python -m worldquant_alpha.pipeline.cli validate --config <config_path>
```

### 3.5 list-configs - 列出可用配置

```bash
python -m worldquant_alpha.pipeline.cli list-configs
```

---

## 模板配置示例

### 模板 JSON 结构

```json
{
  "模板名称": {
    "name": "模板名称",
    "template": "ts_rank(<field>, <window>)",
    "components": {
      "<field>": ["close", "vwap"],
      "<window>": [5, 10, 22]
    },
    "description": "描述",
    "tags": ["simple", "ts_rank"],
    "enabled": true,
    "dataset": "analyst10"
  }
}
```

### 模板文件位置

模板文件存储在：`worldquant_alpha/templates/user_templates.json`

---

## 常用 Pipeline 阶段

| 阶段名称 | 说明 |
|----------|------|
| `first_order` | 一阶 Alpha 生成 |
| `backtest_first` | 一阶 Alpha 回测 |
| `filter_first` | 一阶 Alpha 筛选 |
| `second_order` | 二阶 Alpha 生成 |
| `backtest_second` | 二阶 Alpha 回测 |
| `filter_second` | 二阶 Alpha 筛选 |
| `third_order` | 三阶 Alpha 生成 |
| `backtest_third` | 三阶 Alpha 回测 |

---

## 配置文件位置

默认配置文件位于：`worldquant_alpha/configs/third_order_default.yaml`

状态文件（用于断点续传）：`.pipeline_state.json`
