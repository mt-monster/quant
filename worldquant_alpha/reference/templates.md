# 表达式模板库

> 按 ATLAS 六层架构组织的 Alpha 表达式模板。所有模板均通过 ATLAS 合规检查。
> 使用时将 `field_A` / `field_B` 替换为实际字段名。

---

## 一、7 种交互范式模板

### P1 价差型（SPREAD）— 同维度差异

**经济含义**：两个同维度字段的差异信号（如 ROE-ROA = 杠杆溢价）。

```python
# 基础版：L1→L2→L4
rank(ts_zscore(subtract(field_A, field_B, filter=true), 66))

# 分组版：L1→L2→L5
group_rank(ts_zscore(subtract(field_A, field_B, filter=true), 66), industry)

# 动量版：L1→L2→L4
rank(ts_delta(subtract(field_A, field_B, filter=true), 22))

# 波动版：L1→L2→L5
group_rank(ts_std_dev(subtract(field_A, field_B, filter=true), 66), sector)

# 带转换：L1→L2→L5→L6
signed_power(group_rank(ts_zscore(subtract(field_A, field_B, filter=true), 66), industry), 1.5)
```

---

### P2 比率型（RATIO）— 效率/强度比

**经济含义**：两个字段的效率或强度比（如 EBIT/Revenue = 经营效率）。

```python
# 基础版：L1→L2→L4
rank(ts_zscore(divide(field_A, field_B), 66))

# 分组版：L1→L2→L5
group_rank(ts_zscore(divide(field_A, field_B), 66), industry)

# 历史分位：L1→L2→L4
rank(ts_rank(divide(field_A, field_B), 252))

# 变化率：L1→L2→L4
rank(ts_delta(divide(field_A, field_B), 22))

# 低频数据版（带缺失填充）：L2→L1→L2→L5
group_rank(ts_zscore(divide(ts_backfill(field_A, 252), ts_backfill(field_B, 252)), 66), industry)

# 带转换：L1→L2→L5→L6
signed_power(group_rank(ts_zscore(divide(field_A, field_B), 66), industry), 1.5)
```

---

### P3 条件型（CONDITIONAL）— 状态过滤

**经济含义**：在特定市场状态下才激活信号（如动量确认后才交易）。

```python
# trade_when 版：L2→L3→L5
trade_when(ts_delta(field_B, 22) > 0, group_rank(ts_zscore(field_A, 66), industry))

# if_else 版：L2→L3→L5
if_else(ts_delta(field_B, 22) > 0, group_rank(ts_zscore(field_A, 66), industry), 0)

# 分桶条件：L4→L3→L2→L5
if_else(bucket(rank(field_B), 10) > 7, group_rank(ts_zscore(field_A, 66), industry), 0)

# 事件窗口：L3→L2→L4
if_else(days_from_last_change(field_A) < 10, rank(ts_zscore(field_B, 22)), 0)
```

---

### P4 回归型（REGRESSION）— 残差/斜率

**经济含义**：A 对 B 回归后的残差信号，捕捉无法被 B 解释的 A 的独立变化。

```python
# 基础版：L2→L5
group_rank(ts_regression(field_A, field_B, 66), subindustry)

# 长窗口：L2→L4
zscore(ts_regression(field_A, field_B, 126))

# 低频数据版：L2→L2→L5
group_rank(ts_regression(ts_backfill(field_A, 252), ts_backfill(field_B, 252), 66), industry)

# 带转换：L2→L5→L6
signed_power(group_rank(ts_regression(field_A, field_B, 66), industry), 1.5)
```

---

### P5 相关型（CORRELATION）— 联动变化

**经济含义**：两个字段在时间维度上的联动性变化信号。

```python
# 基础版：L2→L2→L4
rank(ts_corr(ts_delta(field_A, 5), ts_delta(field_B, 5), 66))

# 长窗口：L2→L4
rank(ts_corr(field_A, field_B, 126))

# 衰减版：L2→L2→L2
ts_decay_linear(ts_corr(rank(field_A), rank(field_B), 126), 22)

# 分组版：L2→L5
group_zscore(ts_corr(field_A, field_B, 126), sector)
```

---

### P6 事件型（EVENT）— 事件窗口信号

**经济含义**：在字段值发生变化的事件窗口内，激活另一个字段的信号。

```python
# 基础版：L3→L2→L4
if_else(days_from_last_change(field_A) < 10, rank(ts_zscore(field_B, 22)), 0)

# 分组版：L3→L2→L5
if_else(days_from_last_change(field_A) < 10, group_rank(ts_zscore(field_B, 66), industry), 0)

# 变化值版：L2→L3→L4
if_else(last_diff_value(field_A) > 0, rank(ts_delta(field_B, 22)), 0)
```

---

### P7 分歧型（DIVERGENCE）— 均值回复

**经济含义**：两个字段在标准化后的分歧信号，赌它们会回归均值。

```python
# 基础版：L2→L1→L4
rank(subtract(ts_zscore(field_A, 66), ts_zscore(field_B, 66)))

# 分组版：L2→L1→L5
group_zscore(subtract(ts_zscore(field_A, 66), ts_zscore(field_B, 66)), sector)

# 长窗口版：L2→L1→L4
rank(subtract(ts_zscore(ts_backfill(field_A, 252), 66), ts_zscore(ts_backfill(field_B, 252), 66)))

# 分位版（用 ts_rank 代替 ts_zscore）：L2→L1→L5
group_rank(subtract(ts_rank(field_A, 252), ts_rank(field_B, 252)), industry)
```

---

## 二、单字段模板（基线对照用，每批最多 1 条）

```python
# 时序动量
rank(ts_delta(ts_backfill(field_A, 252), 22))

# 时序标准化
group_rank(ts_zscore(field_A, 66), industry)

# 历史分位
rank(ts_rank(field_A, 252))

# 时序波动
group_rank(ts_std_dev(field_A, 66), industry)

# 峰度
group_rank(ts_kurtosis(field_A, 126), sector)
```

---

## 三、增强型模板（Stage 4 使用）

### 3.1 加速度型（L2→L2→L4）
```python
# 动量加速
rank(subtract(ts_delta(field_A, 22), ts_delta(field_A, 66), filter=true))

# 二阶变化
rank(ts_delta(ts_delta(field_A, 22), 66))
```

### 3.2 Cap 加权型（解决 SubU 问题）
```python
# 用 inverse(cap) 的幂次调整信号强度
signed_power(group_rank(ts_zscore(divide(field_A, field_B), 66), industry), 1.5)

# Cap 幂次缩放（适用于模型数据解决 SubU 问题）
group_rank(ts_zscore(divide(divide(field_A, field_B), signed_power(inverse(cap), 3)), 15), industry)
```

### 3.3 分桶交互型
```python
# 按 B 分桶后在桶内排名 A
group_rank(ts_zscore(field_A, 66), densify(bucket(rank(field_B), range='0.1, 1, 0.1')))
```

### 3.4 双层中性化
```python
# 先行业中性化，再市值中性化
group_neutralize(group_neutralize(ts_zscore(divide(field_A, field_B), 66), sector), bucket(rank(cap), 10))
```

---

## 四、窗口选择速查

| 窗口 | 天数 | 含义 | 适用场景 |
|------|------|------|---------|
| 5 | 1周 | 超短期 | 日更高频数据的短期动量 |
| 22 | 1月 | 短期 | 月度信号、短期均值回复 |
| 44 | 2月 | 中短期 | 事件驱动数据 |
| 66 | 3月 | 中期 | 最通用，季度信号 |
| 126 | 6月 | 中长期 | 半年度信号、相关性计算 |
| 252 | 1年 | 长期 | 年度信号、长期趋势 |
| 504 | 2年 | 超长期 | 稳健分位计算 |

---

## 五、范式选择决策树

```
字段关系？
├─ 同维度/同单位 → P1_SPREAD（subtract）
├─ 分子/分母关系 → P2_RATIO（divide）
├─ 因果/解释关系 → P4_REGRESSION（ts_regression）
├─ 联动/共振关系 → P5_CORRELATION（ts_corr）
├─ 应该回归均值 → P7_DIVERGENCE（subtract + ts_zscore）
├─ 一个是条件一个是信号 → P3_CONDITIONAL（trade_when/if_else）
└─ 一个有事件触发 → P6_EVENT（days_from_last_change）
```
