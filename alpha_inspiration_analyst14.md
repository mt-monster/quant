基于提供的算子和分析师数据，以下是几个可复用的Alpha模板，每个模板都包含经济逻辑、参数槽位和调优选项：

---

### **模板1：盈利惊喜（Earnings Surprise）**
**经济逻辑**：实际盈利超预期（beat）的股票往往有正向超额收益，而miss的股票则表现不佳。用分析师分歧度标准化可以捕捉惊喜的显著性。

**模板公式**：
```
alpha = rank(
          group_zscore(
            winsorize(
              ts_backfill(
                (anl14_actvalue_eps_fp0 - anl14_mean_eps_fp1) / 
                (anl14_stddev_eps_fp1 + 1e-6), 
              <backfill_days>), 
            <winsorize_std>),
          <group_field>)
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议63或126
- `<winsorize_std>`: 标准差倍数，建议4或5
- `<group_field>`: 分组字段，如`industry`或`sector`

**可选调优**：
- 可加入`ts_decay_linear(..., <decay_days>)`降低换手率
- 可替换分子为`anl14_actvalue_eps_fy0 - anl14_mean_eps_fy1`使用年度数据
- 可替换分母为`anl14_mean_eps_fp1`使用相对惊喜

---

### **模板2：分析师修正动量（Estimate Revision Momentum）**
**经济逻辑**：分析师一致预期的上修反映基本面改善，短期修正比长期修正更有效。

**模板公式**：
```
alpha = rank(
          group_zscore(
            ts_delta(
              ts_backfill(anl14_mean_eps_fp1, <backfill_days>), 
            <delta_days>),
          <group_field>)
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议63
- `<delta_days>`: 修正窗口，建议21或63（1个月或3个月）
- `<group_field>`: 分组字段，如`industry`

**可选调优**：
- 可计算`ts_delta(..., <delta_days>) / ts_delay(..., <delta_days>)`得到百分比修正
- 可加入`ts_std_dev`过滤高波动修正
- 可组合多个指标如EPS、Revenue、EBITDA：`add(revision_eps, revision_revenue, revision_ebitda)`

---

### **模板3：分析师分歧度（Analyst Dispersion）**
**经济逻辑**：高分歧度反映高不确定性，通常对应低未来收益；低分歧度股票风险更小。

**模板公式**：
```
alpha = reverse(
          rank(
            group_zscore(
              ts_backfill(anl14_stddev_eps_fp1, <backfill_days>),
            <group_field>)
          )
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议126
- `<group_field>`: 分组字段，如`industry`或`sector`

**可选调优**：
- 可标准化为`anl14_stddev_eps_fp1 / (anl14_mean_eps_fp1 + 1e-6)`得到变异系数
- 可加入`group_count`过滤覆盖度低的股票
- 可组合多个指标分歧度：`add(dispersion_eps, dispersion_revenue, dispersion_ebitda)`

---

### **模板4：预期期限结构斜率（Term Structure Slope）**
**经济逻辑**：远期预期相对近期预期上升，反映分析师认为公司增长将加速；反之则增长放缓。

**模板公式**：
```
alpha = rank(
          group_zscore(
            ts_backfill(
              (anl14_mean_eps_fy1 - anl14_mean_eps_fp1) / 
              (abs(anl14_mean_eps_fp1) + 1e-6), 
            <backfill_days>),
          <group_field>)
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议63
- `<group_field>`: 分组字段，如`industry`

**可选调优**：
- 可比较不同期限组合：fp1 vs fp2, fy1 vs fy2
- 可加入`ts_delta`捕捉斜率变化动量
- 可限制分母最小值避免异常值：`max(abs(anl14_mean_eps_fp1), 0.01)`

---

### **模板5：分析师覆盖度变化（Coverage Change）**
**经济逻辑**：覆盖分析师数量增加表明市场关注度提升，通常伴随信息效率改善和流动性增强。

**模板公式**：
```
alpha = rank(
          group_zscore(
            ts_delta(
              ts_backfill(anl14_numofests_eps_fp1, <backfill_days>), 
            <delta_days>),
          <group_field>)
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议63
- `<delta_days>`: 变化窗口，建议63或126
- `<group_field>`: 分组字段，如`industry`

**可选调优**：
- 可计算相对变化：`ts_delta(...) / ts_delay(..., <delta_days>)`
- 可过滤最低覆盖度：`trade_when(anl14_numofests_eps_fp1 > <min_coverage>, ...)`
- 可组合`numofests`与`stddev`捕捉"覆盖增加+分歧减少"信号

---

### **模板6：推荐情绪（Recommendation Sentiment）**
**经济逻辑**：买入推荐比例高的股票反映分析师乐观情绪，但需注意过度一致的风险。

**模板公式**：
```
alpha = rank(
          group_zscore(
            ts_backfill(
              (anl14_buy - anl14_sell) / 
              (anl14_buy + anl14_hold + anl14_sell + 1e-6), 
            <backfill_days>),
          <group_field>)
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议63
- `<group_field>`: 分组字段，如`industry`

**可选调优**：
- 可加入`anl14_meanrating`直接利用评级均值
- 可计算情绪变化：`ts_delta(...)`
- 可结合`anl14_outperform / anl14_underperform`得到更细粒度情绪

---

### **模板7：目标价隐含回报（Price Target Implied Return）**
**经济逻辑**：目标价相对于当前价的空间反映分析师看好的程度，但需分组比较避免市值偏差。

**模板公式**：
```
alpha = rank(
          group_zscore(
            ts_backfill(anl14_ptg_mean, <backfill_days>),
          <group_field>)
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议63
- `<group_field>`: 分组字段，如`industry`或`sector`

**可选调优**：
- 可计算目标价标准差：`anl14_ptg_stddev`衡量分歧
- 可计算`anl14_ptg_mean / anl14_ptg_median - 1`识别异常值
- 可加入`ts_delta`捕捉目标价调整动量

---

### **模板8：盈利质量差异（Earnings Quality Spread）**
**经济逻辑**：调整后EPS与报告EPS差异大可能反映低质量盈利（如一次性收益），市场会给予折价。

**模板公式**：
```
alpha = rank(
          group_zscore(
            winsorize(
              ts_backfill(
                (anl14_mean_eps_fp1 - anl14_mean_epsrep_fp1) / 
                (anl14_mean_eps_fp1 + 1e-6), 
              <backfill_days>),
            <winsorize_std>),
          <group_field>)
        )
```

**参数槽位**：
- `<backfill_days>`: 回填天数，建议63
- `<winsorize_std>`: 标准差倍数，建议5
- `<group_field>`: 分组字段，如`industry`

**可选调优**：
- 可加入`abs()`取绝对值，无论正负都视为低质量
- 可计算`ts_delta`捕捉质量变化趋势
- 可组合多个质量指标：EPS、Net Profit、EBITDA

---

### **通用调优框架**
所有模板均可添加以下后处理：

1. **换手率控制**：
   ```
   alpha = ts_decay_linear(alpha, <decay_days>)  # decay_days建议21-63
   # 或
   alpha = hump(alpha, <hump_days>, <hump_threshold>)
   ```

2. **风险中性化**：
   ```
   alpha = vector_neut(alpha, <risk_factor>)  # 如市值、估值、波动率因子
   ```

3. **覆盖度过滤**：
   ```
   alpha = trade_when(anl14_numofests_eps_fp1 >= <min_analysts>, alpha)
   ```

4. **波动率调整**：
   ```
   alpha = alpha / ts_backfill(ts_std_dev(returns, <vol_window>), <backfill_days>)
   ```

这些模板可系统性地搜索参数组合，构建多样化的Alpha策略组合。