# ATLAS 六层方法论参考

> **口诀**：先算术构特征，时序提信息，逻辑做判断，横截面标准化，最后做调整。
> **核心原则**：横截面运算是标准化的最后一步，不是第一步！

---

## 一、六层运算详解（L1→L6，由内到外）

### L1 算术运算（Arithmetic）— 构建原始特征

**目的**：用算术操作从原始字段构建特征。这是信号的起点。

| 算子 | 用途 | 示例 |
|------|------|------|
| `subtract(A, B, filter=true)` | 同维度差异 | ROE - ROA = 杠杆溢价 |
| `divide(A, B)` | 效率/比率 | EBIT / revenue = 经营效率 |
| `abs(x)` | 绝对值 | abs(returns) = 波动幅度 |
| `log(x)` | 对数变换 | log(cap) = 规模因子 |
| `inverse(x)` | 倒数 | inverse(volatility) = 低波动信号 |
| `sign(x)` | 方向提取 | sign(ts_delta(field, 22)) |
| `signed_power(x, e)` | 保号幂变换 | signed_power(signal, 0.5) = 压缩极值 |

**禁止**：`add()` / `multiply()` — 平台明确禁止用于信号混合。

**注意**：`subtract` 和数学运算支持 `filter=true` 参数处理 NaN；`divide` **不支持** `filter` 参数。

---

### L2 时间序列（Time-series）— 提取时序信息

**目的**：在时间维度上提取动量/均值回复/波动率等信号。

| 算子 | 信号类型 | 窗口建议 |
|------|---------|---------|
| `ts_delta(x, d)` | 变化量/动量 | 日更: 5/22/66, 季更: 1/4 |
| `ts_zscore(x, d)` | 时序标准化偏离 | 22/66/126/252 |
| `ts_std_dev(x, d)` | 波动率 | 20/66 |
| `ts_rank(x, d)` | 历史分位 | 66/126/252 |
| `ts_regression(A, B, d)` | 回归斜率/残差 | 66/126 |
| `ts_corr(A, B, d)` | 相关性 | 66/126 |
| `ts_backfill(x, d)` | 缺失填充（预处理） | 66/120/252 |
| `ts_mean(x, d)` | 移动均值 | 22/66 |
| `ts_decay_linear(x, d)` | 线性衰减 | 22/44 |
| `ts_returns(x, d)` | 收益率 | 5/22 |
| `ts_kurtosis(x, d)` | 峰度 | 66/126 |
| `ts_max_diff(x, d)` | 最大差异 | 66/252 |
| `ts_count_nans(x, d)` | 缺失计数 | 66/252 |
| `ts_quantile(x, d)` | 时序分位数 | 252/504/1008 |
| `ts_product(x, d)` | 时序乘积 | 3/5 |
| `ts_av_diff(x, d)` | 均值差异 | 22/66 |
| `ts_ir(x, d)` | 信息比率 | 66/126 |
| `ts_scale(x, d)` | 时序缩放 | 22/66 |
| `ts_sum(x, d)` | 时序求和 | 22/66 |
| `ts_arg_min(x, d)` | 最小值位置 | 66/252 |
| `ts_arg_max(x, d)` | 最大值位置 | 66/252 |

**窗口选择规则**:
| 数据更新频率 | 推荐窗口 |
|---|---|
| 日更（新闻/情绪/价量） | 5 / 22 / 66 / 126 / 252 |
| 周/月更（分析师修正） | 4 / 13 / 26 / 52 |
| 季/年更（财报/CFROI） | 1 / 4 / 8（短窗口，更新慢） |

---

### L3 逻辑运算（Logic）— 条件判断/过滤

**目的**：基于可观测的经济状态做条件过滤，只在信号有效时交易。

| 算子 | 用途 | 模式 |
|------|------|------|
| `if_else(cond, true_val, false_val)` | 条件分支 | `if_else(A > 0, signal, 0)` |
| `trade_when(signal, condition)` | 条件交易 | `trade_when(ts_delta(B,22)>0, rank(A))` |
| `days_from_last_change(x)` | 事件窗口 | `if_else(days_from_last_change(A)<10, signal, 0)` |

**注意**：条件必须基于经济逻辑（如动量确认、事件触发），不要用随意条件过拟合。

---

### L4 横截面运算（Cross-sectional）— 全市场标准化

**目的**：将信号从绝对值转为全市场相对排名/分位。

| 算子 | 特点 | 何时用 |
|------|------|-------|
| `rank(x)` | 百分位排名，最鲁棒 | 默认首选 |
| `zscore(x)` | Z-score，保留分布信息 | 需要线性排序时 |
| `winsorize(x, std=4)` | 去极值 | 极端值干扰时，通常在 zscore 前 |
| `quantile(x, driver="gaussian")` | 分位数变换 | 需要正态化时 |

**关键规则**：
- rank/zscore 放在外层，不要放在内层
- **禁止** `rank(rank(x))`、`zscore(rank(x))` 等重复标准化
- 一个表达式最多做一次横截面标准化

---

### L5 分组运算（Group/Sector）— 行业/板块调整

**目的**：在行业/板块内做相对比较，去除行业共同因素。

| 算子 | 用途 | 分组变量 |
|------|------|---------|
| `group_rank(x, group)` | 组内排名 | industry / sector / subindustry |
| `group_zscore(x, group)` | 组内 Z-score | industry / sector / subindustry |
| `group_neutralize(x, group)` | 组内中性化 | industry / sector |
| `group_scale(x, group)` | 组内缩放 | industry / sector |
| `group_mean(x, group)` | 组内均值 | industry / sector |
| `group_sum(x, group)` | 组内求和 | industry / sector |
| `group_std_dev(x, group)` | 组内标准差 | industry / sector |
| `group_count(x, group)` | 组内计数 | industry / sector |
| `bucket(x, n)` | 等频分桶 | — |

**L4 vs L5 选择**：
- 行业效应强的信号 → 用 L5（group_rank / group_zscore）
- 全市场信号 → 用 L4（rank / zscore）
- 可以只用 L5 替代 L4（group_rank 自带标准化效果）

**分组变量选择**：
- `industry`：通用首选，粒度适中
- `subindustry`：更细粒度，可降低 ProdCorr
- `sector`：更粗粒度，信号更平滑
- `bucket(rank(cap), 10)`：市值分组，消除规模效应

---

### L6 转换运算（Transformation）— 最终信号调整

**目的**：对最终信号做微调（压缩/反转/衰减）。

| 算子 | 用途 | 参数建议 |
|------|------|---------|
| `signed_power(x, e)` | 信号非线性压缩（e<1）或放大（e>1） | 0.5 / 1.5 / 3.0 / 6.0 |
| `reverse(x)` / `-x` | 信号方向反转 | — |
| `tail(x, lower, upper)` | 只保留尾部信号 | tail(x, 0.2, 0.8) |
| `hump(x, hump_val)` | TVR 控制，平滑中间区间 | hump(x, 0.35) |
| `pasteurize(x)` | 清理 NaN/Inf | — |

---

## 二、ATLAS 合规检查清单

构建每个表达式前后必须检查：

```
[ ] L1: 特征构建有经济意义（非随意算术拼凑）
[ ] L2: 时间窗口与数据更新频率匹配
[ ] L3: 条件逻辑基于可观测的经济状态（非过拟合）
[ ] L4/L5: 标准化在外层，且只做一次
[ ] L6: 转换操作在最外层
[ ] 无逆序嵌套（如 ts_delta(rank(x)) 是错误的）
[ ] 无重复标准化（如 rank(rank(x)) 是错误的）
[ ] 总操作符数 ≤ 8
[ ] 数据字段 ≤ 3（内置字段不计）
[ ] 无 add() / multiply()
```

---

## 三、逆序嵌套检测

### 错误模式（禁止）
```
ts_delta(rank(x), d)                         # L2 包裹 L4 ❌
ts_zscore(group_rank(x, industry), d)         # L2 包裹 L5 ❌
group_rank(signed_power(x, 2), industry)      # L5 包裹 L6 ❌（L6 应在 L5 之外）
```

### 正确模式
```
rank(ts_delta(x, d))                          # L4 包裹 L2 ✅
group_rank(ts_zscore(x, d), industry)         # L5 包裹 L2 ✅
signed_power(group_rank(x, industry), 1.5)    # L6 包裹 L5 ✅
```

### 特殊允许
```
# rank 作为 L1 层的尺度对齐输入（不是标准化）
subtract(rank(A), rank(B), filter=true)       # 允许 ✅

# 同层嵌套
ts_delta(ts_backfill(x, 252), 22)             # L2 嵌套 L2 ✅
```

---

## 四、双字段预处理对齐（L1 层前置）

### 频率对齐
两字段更新频率不同 → 慢字段用 `ts_backfill(B, 252)` 前向填充。

### 尺度对齐
量纲差异大 → 交互前对两字段做 `rank()` 或 `ts_zscore()` 标准化。

### 覆盖率对齐
`coverage_A × coverage_B < 0.20` → **禁止直接交互**（数据太稀疏）。

### VECTOR 字段对齐
两个 VECTOR 字段交互 → 先各自 `vec_*()` + `ts_backfill()` 聚合为 SCALAR。

---

## 五、VECTOR 字段预处理（强制）

VECTOR 字段必须先聚合为 SCALAR 再进入 ATLAS 流程：

| Vec 算子 | 信号语义 | 适用经济溢价 |
|---------|---------|------------|
| `vec_avg` | 中心趋势/共识 | Sentiment / Value / Quality |
| `vec_sum` | 总量规模 | Flow / Liquidity / Event |
| `vec_stddev` | 分歧度/不确定性 | Volatility / Sentiment |
| `vec_count` | 覆盖广度/注意力 | Liquidity / Event |
| `vec_max` | 极端乐观 | Momentum / Sentiment |
| `vec_min` | 极端悲观 | Reversal / Value |
| `vec_range` | 区间宽度 | Volatility |

**使用规则**：
1. 根据字段语义选择对应 vec 算子
2. 首批至少 3 种不同 vec 算子（禁止全部使用 vec_avg）
3. 聚合后必须 `ts_backfill(vec_*(field), 120+)` 填充缺失
4. 完成后按正常 ATLAS L1→L6 流程继续

---

## 六、Decay 选择指南

| 字段更新频率 | 推荐 decay | 原理 |
|---|---|---|
| 日更（新闻/情绪/价量） | 2–4 | 信号高频，需平滑 |
| 周/月更（分析师修正） | 0–2 | 信号已低频，额外衰减稀释信号 |
| 季/年更（cfroi/accruals/BV） | **0** | 信号极低频，加 decay 反而削弱 |
| 模型输出（model219 等） | 30–60 | 模型信号需高衰减平滑 |
| 事件驱动（news12 等） | 25–35 | 事件信号需中高衰减 |
