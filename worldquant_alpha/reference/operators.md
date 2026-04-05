# 操作符速查手册

> 平台验证通过的操作符完整清单。操作符签名可通过 `MCP: get_operators` 实时查询。

---

## 一、按 ATLAS 层次分类

### L1 算术操作符

| 操作符 | 签名 | 说明 |
|--------|------|------|
| `subtract` | `subtract(x, y, filter=true)` | 减法，filter=true 处理 NaN |
| `divide` | `divide(x, y)` | 除法，**不支持 filter** |
| `abs` | `abs(x)` | 绝对值 |
| `log` | `log(x)` | 自然对数 |
| `inverse` | `inverse(x)` | 倒数 1/x |
| `sign` | `sign(x)` | 符号函数 |
| `signed_power` | `signed_power(x, e)` | 保号幂 sign(x)*|x|^e |
| `power` | `power(x, e)` | x^e |
| `sqrt` | `sqrt(x)` | 平方根 |
| `reverse` | `reverse(x)` | 反转 -x |
| `normalize` | `normalize(x)` | 归一化 |
| `scale` | `scale(x)` | 缩放 |

### L2 时序操作符

| 操作符 | 签名 | 说明 |
|--------|------|------|
| `ts_delta` | `ts_delta(x, d)` | d 日变化量 |
| `ts_zscore` | `ts_zscore(x, d)` | d 日 Z-score |
| `ts_rank` | `ts_rank(x, d)` | d 日历史分位 |
| `ts_std_dev` | `ts_std_dev(x, d)` | d 日标准差 |
| `ts_mean` | `ts_mean(x, d)` | d 日均值 |
| `ts_sum` | `ts_sum(x, d)` | d 日求和 |
| `ts_regression` | `ts_regression(y, x, d)` | d 日回归 |
| `ts_corr` | `ts_corr(x, y, d)` | d 日相关系数 |
| `ts_backfill` | `ts_backfill(x, d)` | 向前填充 d 日 |
| `ts_decay_linear` | `ts_decay_linear(x, d)` | 线性衰减 d 日 |
| `ts_returns` | `ts_returns(x, d)` | d 日收益率 |
| `ts_kurtosis` | `ts_kurtosis(x, d)` | d 日峰度 |
| `ts_max_diff` | `ts_max_diff(x, d)` | d 日最大差异 |
| `ts_count_nans` | `ts_count_nans(x, d)` | d 日 NaN 计数 |
| `ts_quantile` | `ts_quantile(x, d)` | d 日分位数 |
| `ts_product` | `ts_product(x, d)` | d 日乘积 |
| `ts_av_diff` | `ts_av_diff(x, d)` | d 日均值差 |
| `ts_ir` | `ts_ir(x, d)` | d 日信息比率 |
| `ts_scale` | `ts_scale(x, d)` | d 日时序缩放 |
| `ts_arg_min` | `ts_arg_min(x, d)` | d 日最小值位置 |
| `ts_arg_max` | `ts_arg_max(x, d)` | d 日最大值位置 |
| `ts_delay` | `ts_delay(x, d)` | 延迟 d 日 |

### L3 逻辑操作符

| 操作符 | 签名 | 说明 |
|--------|------|------|
| `if_else` | `if_else(cond, true_val, false_val)` | 条件分支 |
| `trade_when` | `trade_when(signal, condition)` | 条件交易 |
| `days_from_last_change` | `days_from_last_change(x)` | 距最近变化天数 |
| `last_diff_value` | `last_diff_value(x)` | 最近变化值 |

### L4 截面操作符

| 操作符 | 签名 | 说明 |
|--------|------|------|
| `rank` | `rank(x)` | 截面百分位排名 |
| `zscore` | `zscore(x)` | 截面 Z-score |
| `winsorize` | `winsorize(x, std=4)` | 截面去极值 |
| `quantile` | `quantile(x, driver="gaussian")` | 截面分位数变换 |

### L5 分组操作符

| 操作符 | 签名 | 说明 |
|--------|------|------|
| `group_rank` | `group_rank(x, group)` | 组内排名 |
| `group_zscore` | `group_zscore(x, group)` | 组内 Z-score |
| `group_neutralize` | `group_neutralize(x, group)` | 组内中性化 |
| `group_scale` | `group_scale(x, group)` | 组内缩放 |
| `group_mean` | `group_mean(x, group)` | 组内均值 |
| `group_sum` | `group_sum(x, group)` | 组内求和 |
| `group_std_dev` | `group_std_dev(x, group)` | 组内标准差 |
| `group_count` | `group_count(x, group)` | 组内计数 |
| `bucket` | `bucket(x, n)` | n 等频分桶 |
| `densify` | `densify(x)` | 密集化 |
| `vector_neut` | `vector_neut(x, y)` | 向量中性化 |

### L6 转换操作符

| 操作符 | 签名 | 说明 |
|--------|------|------|
| `signed_power` | `signed_power(x, e)` | 保号幂变换 |
| `tail` | `tail(x, lower, upper)` | 尾部截取 |
| `hump` | `hump(x, hump_val)` | 驼峰平滑 |
| `pasteurize` | `pasteurize(x)` | 清理 NaN/Inf |

### VECTOR 聚合操作符

| 操作符 | 签名 | 说明 |
|--------|------|------|
| `vec_avg` | `vec_avg(x)` | 向量均值 |
| `vec_sum` | `vec_sum(x)` | 向量求和 |
| `vec_stddev` | `vec_stddev(x)` | 向量标准差 |
| `vec_count` | `vec_count(x)` | 向量计数 |
| `vec_max` | `vec_max(x)` | 向量最大值 |
| `vec_min` | `vec_min(x)` | 向量最小值 |
| `vec_range` | `vec_range(x)` | 向量范围 |

---

## 二、内置字段（不计入 3 字段上限）

```
returns / close / vwap / cap
sector / industry / subindustry / market / exchange
```

---

## 三、禁用操作符

| 操作符 | 原因 | 替代方案 |
|--------|------|---------|
| `add(x, y)` | 平台禁止信号混合 | `subtract(x, reverse(y), filter=true)` 或分别处理 |
| `multiply(x, y)` | 平台禁止信号混合 | `divide(x, inverse(y))` 或 `signed_power` |

---

## 四、平台不支持的操作符

以下操作符虽然在部分文档中提及，但平台实际不支持：

```
sigmoid, ts_entropy, ts_co_skewness, ts_co_kurtosis,
ts_skewness, ts_moment, cross_sectional_regression
```

---

## 五、分组变量速查

| 变量 | 粒度 | 使用场景 |
|------|------|---------|
| `market` | 最粗 | 全市场分组 |
| `sector` | 粗 | GICS 11 个板块 |
| `industry` | 中（推荐默认） | GICS ~70 个行业 |
| `subindustry` | 细 | GICS ~160 个子行业 |
| `bucket(rank(cap), 10)` | 市值 | 消除规模效应 |
| `densify(bucket(rank(field), range='0.1,1,0.1'))` | 自定义分桶 | 按字段值分组 |
