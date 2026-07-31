基于提供的运算符和分析师数据集`analyst10`，以下是几个系统化的Alpha模板设计。每个模板均遵循"数据清洗→特征工程→横截面处理→时序优化"的标准化流程，并预留可调的参数槽位。

---

### **模板1：智能预期分歧度（Smart Estimate Divergence）**

**经济逻辑**：当顶级分析师的"智能预期"与市场共识出现显著偏离时，往往预示着非公开信息或深度研究结论尚未充分反映到股价中。

```python
# 数据清洗层
smart_est = winsorize(ts_backfill(<智能预期字段>, 63), std=4)
consensus = winsorize(ts_backfill(<共识预期字段>, 63), std=4)

# 特征计算层
divergence = (smart_est - consensus) / consensus  # 相对分歧度
divergence = group_zscore(divergence, <分组字段>)  # 行业/板块内标准化

# 横截面处理层
alpha = rank(divergence)  # 全市场排序

# 可选优化层
alpha = ts_decay_linear(alpha, <衰减天数>)  # 降低换手率
```

**可调槽位**：
- `<智能预期字段>`：如`anl10_netfy1_smart_ests_v0`（净利润FY1智能预期）
- `<共识预期字段>`：如`anl10_netfy1_consensus`
- `<分组字段>`：`sector`/`industry`/`subindustry`
- `<衰减天数>`：建议20-60天

---

### **模板2：创新性修正动量（Innovation Revision Momentum）**

**经济逻辑**：创新性修正（非羊群式调整）更能反映分析师的真实观点变化。捕捉这类修正的加速度可提前发现基本面拐点。

```python
# 清洗与动量计算
innov_score = winsorize(ts_backfill(<创新分数字段>, 63), std=4)
momentum = ts_delta(innov_score, <动量窗口>)  # 创新分数的变化率

# 横截面增强
momentum = group_zscore(momentum, <分组字段>)  # 剔除行业共性
alpha = rank(momentum)

# 信号强化（可选）
alpha = if_else(group_count(<分组字段>) >= <最小样本数>, alpha, NaN)  # 剔除覆盖不足的股票
```

**可调槽位**：
- `<创新分数字段>`：如`anl10_netinnovation_score_fy1`
- `<动量窗口>`：5-21天
- `<分组字段>`：`industry`
- `<最小样本数>`：5-10个分析师

---

### **模板3：预期惊喜复合强度（Predicted Surprise Composite）**

**经济逻辑**：预测惊喜本身的方向性需结合修正的广度（参与分析师数量）验证。单向大广度修正能过滤虚假信号。

```python
# 多信号清洗
pred_surp = winsorize(ts_backfill(<预测惊喜字段>, 63), std=4)
innov_up = winsorize(ts_backfill(<创新上调数字段>, 63), std=4)
innov_down = winsorize(ts_backfill(<创新下调数字段>, 63), std=4)

# 广度验证
breadth = innov_up - innov_down  # 净创新修正方向
composite = pred_surp * sign(breadth)  # 惊喜方向与修正广度一致

# 标准化
composite = group_zscore(composite, <分组字段>)
alpha = rank(composite)
```

**可调槽位**：
- `<预测惊喜字段>`：如`anl10_netfy1_pred_surps_v0`
- `<创新上调/下调数字段>`：`anl10_netinnovate_increase_fy1`/`decrease`
- `<分组字段>`：`sector`

---

### **模板4：修正时效性加权（Revision Freshness Weighting）**

**经济逻辑**：分析师修正的时效性决定信息价值。越近期的修正应赋予越高权重， stale数据应被惩罚。

```python
# 构建时效权重
est_age = winsorize(ts_backfill(<估计天数字段>, 63), std=4)
freshness = 1 / (1 + est_age / <半衰期>)  # 指数衰减权重

# 加权修正值
revise_val = winsorize(ts_backfill(<修正值字段>, 63), std=4)
weighted_signal = revise_val * freshness

# 横截面处理
weighted_signal = group_zscore(weighted_signal, <分组字段>)
alpha = rank(weighted_signal)
```

**可调槽位**：
- `<估计天数字段>`：`anl10_netpast_det_estage`
- `<修正值字段>`：`anl10_netrevise_value_fy1`
- `<半衰期>`：30-90天
- `<分组字段>`：`industry`

---

### **模板5：修正幅度-广度协同（Revision Magnitude-Breadth Synthesis）**

**经济逻辑**：大幅修正若缺乏广度支持可能是噪音；小幅但大广度修正则反映共识迁移。两者乘积可捕捉"质量×数量"效应。

```python
# 幅度成分（标准化）
revise_val = winsorize(ts_backfill(<修正值字段>, 63), std=4)
magnitude = ts_zscore(revise_val, <时序窗口>)  # 时序标准化

# 广度成分（净创新修正家数）
breadth = ts_backfill(<创新上调字段>, 63) - ts_backfill(<创新下调字段>, 63)
breadth = winsorize(breadth, std=4)
breadth = ts_zscore(breadth, <时序窗口>)

# 协同信号
combined = magnitude * breadth  # 幅度与广度的交互
combined = group_zscore(combined, <分组字段>)
alpha = rank(combined)
```

**可调槽位**：
- `<修正值字段>`：`anl10_netrevise_value_fy1`
- `<创新上/下调字段>`：`anl10_netinnovate_increase/decrease_fy1`
- `<时序窗口>`：21-63天
- `<分组字段>`：`sector`

---

### **模板6：相对估值修正强度（Revision-to-Price Sensitivity）**

**经济逻辑**：将修正幅度相对于股价标准化，可识别"低价股高修正"与"高价股低修正"的非对称机会。

```python
# 修正-价格比清洗
revise_ratio = winsorize(ts_backfill(<修正比率字段>, 63), std=4)

# 时序动量
ratio_mom = ts_delta(revise_ratio, <动量窗口>)
ratio_mom = group_zscore(ratio_mom, <分组字段>)

# 流动性过滤（可选）
liquidity_filter = ts_mean(<成交量字段>, 21) > <流动性阈值>
alpha = trade_when(ratio_mom, rank(ratio_mom), NaN, liquidity_filter)
```

**可调槽位**：
- `<修正比率字段>`：`anl10_netrevise_ratio_to_close_fy1`
- `<动量窗口>`：5-10天
- `<分组字段>`：`industry`
- `<成交量字段>`：需外部数据如`volume`
- `<流动性阈值>`：全市场中位数

---

### **通用优化建议**

1. **中性化处理**：所有模板均可追加`group_neutralize(alpha, sector)`或`vector_neut(alpha, <风险因子>)`剔除风格暴露
2. **换手率控制**：使用`ts_target_tvr_hump(alpha, <目标换手率>, 0.5, 1.5)`自动优化平滑参数
3. **覆盖度过滤**：通过`group_count`确保每组有效样本≥5-8个
4. **多期合成**：对不同FY1/FY2、Q1/Q2的同一逻辑信号使用`add`或`ts_mean`合成

这些模板可直接在因子研究平台中实例化，通过网格搜索优化槽位参数，形成多样化的Alpha信号簇。