# 六阶段执行手册 — 单数据集双字段 PPAC Alpha

> **前提**：会话开始前确保 wqb-mcp 服务器已运行在 `http://127.0.0.1:8876/mcp`。

---

## Stage 0: 会话初始化

### 0.1 认证

```
→ MCP: authenticate
```

无需传参，工具自动从服务器环境读取凭证。

### 0.2 确定目标

收集用户输入（或自动决策）：
- **数据集名称**（如 `analyst15`、`model219`、`news12`）
- **目标区域**（USA / ASI / EUR / KOR）
- **特殊要求**（如指定字段、指定 neut）

### 0.3 获取区域参数

```
→ MCP: get_platform_setting_options
```

确认可用的 universe / neutralization / delay 组合，按 [reference/regions.md](reference/regions.md) 设置默认参数。

### 0.4 查看已提交 Alpha（避免重复）

```
→ MCP: get_user_alphas(stage="IS", limit=100)
```

记录已用字段和数据集，避免重复提交。

---

## Stage 1: 数据集探索与字段选择

### 1.1 获取数据集信息

```
→ MCP: get_datasets(search="<数据集名称>")
```

确认数据集 ID、描述、覆盖率、更新频率。

### 1.2 获取所有字段

```
→ MCP: get_datafields(dataset_id="<数据集ID>", region="<区域>")
```

### 1.3 字段分类

按经济含义对字段进行分组：

| 分类 | 经济含义 | 示例字段 |
|------|---------|---------|
| **Value** | 估值/定价偏差 | book_value, pe_ratio, ev_ebitda |
| **Growth** | 增长预期/变化 | revenue_growth, eps_growth, delta_* |
| **Quality** | 盈利质量/效率 | roe, roa, margin, accruals |
| **Momentum** | 趋势/动量 | price_change, return_*, momentum |
| **Sentiment** | 市场情绪/预期 | analyst_revision, consensus_change |
| **Flow** | 资金/交易流向 | volume, institutional_flow, buyers |
| **Volatility** | 波动/风险 | std_dev, beta, iv_* |

### 1.4 字段筛选规则

```
[ ] coverage ≥ 0.4（低于 0.4 的字段标记为低优先级）
[ ] 字段类型：MATRIX 优先直接使用；VECTOR 需先 vec_*() 聚合
[ ] 排除常量字段（coverage = 1.0 但无变化）
[ ] 排除已在本区域已提交 Alpha 中使用的字段
```

### 1.5 双字段配对

按**经济互补性**配对字段：

| 配对策略 | 经济逻辑 | 示例 |
|---------|---------|------|
| 量 vs 价 | 量价背离信号 | volume_field / price_field |
| 预期 vs 实际 | 预期偏差信号 | forecast_field / actual_field |
| 短期 vs 长期 | 期限结构信号 | short_term_field / long_term_field |
| 分子 vs 分母 | 效率/比率信号 | numerator_field / denominator_field |
| 水平 vs 变化 | 水平-动量交叉 | level_field / delta_field |
| 主要 vs 次要 | 主次分歧信号 | primary_field / secondary_field |

输出：**字段配对清单**（按优先级排序，标注经济逻辑）。

---

## Stage 2: 双字段批量生成（4/批）

### 2.1 表达式构建原则

遵循 ATLAS 六层运算顺序（详见 [reference/atlas.md](reference/atlas.md)）：

```
L1 算术层（最内层）
  → subtract(A, B, filter=true) / divide(A, B) / abs / log / inverse
L2 时序层
  → ts_zscore / ts_delta / ts_rank / ts_regression / ts_corr / ts_std_dev
L3 逻辑层（可选）
  → if_else / trade_when / days_from_last_change
L4 截面层
  → rank / zscore / winsorize / quantile
L5 分组层（可替代 L4）
  → group_rank / group_zscore / group_neutralize
L6 转换层（最外层）
  → signed_power / reverse / tail / hump
```

### 2.2 VECTOR 字段预处理（强制）

VECTOR 类型字段必须在进入 ATLAS 流程前聚合为 SCALAR：

```python
# 根据字段语义选择 vec 算子
vec_avg(vector_field)      # 中心趋势/共识
vec_sum(vector_field)      # 总量规模
vec_stddev(vector_field)   # 分歧度/不确定性
vec_count(vector_field)    # 覆盖广度/注意力
vec_max(vector_field)      # 极端乐观
vec_min(vector_field)      # 极端悲观

# 聚合后填充缺失
ts_backfill(vec_avg(vector_field), 120)
```

### 2.3 低频字段预处理

季度/年度更新频率的字段需要缺失填充：

```python
ts_backfill(field, 252)    # 年度数据用 252
ts_backfill(field, 66)     # 季度数据用 66
```

### 2.4 批次构建规则

每批 **4 条表达式**，必须满足：

```
[ ] ≥ 3 条双字段交互（同数据集内两个不同字段）
[ ] ≤ 1 条单字段基线（用于信号对照）
[ ] ≥ 2 种不同交互范式（如 P1+P2、P2+P5 等）
[ ] ≥ 3 种不同 TRANSFORM 算子（不能全部用 rank）
[ ] 每条表达式操作符 ≤ 8，字段 ≤ 3
[ ] 不含 add() / multiply()
[ ] ATLAS 层次合规（无逆序嵌套）
```

### 2.5 Smoke Test 协议

新字段或新操作符签名 → 必须先单条 `create_simulation` 验证：

```
→ MCP: create_simulation(
    expression="rank(ts_zscore(field_A, 66))",
    region="<区域>",
    universe="<Universe>",
    delay=1,
    decay=4,
    neutralization="MARKET",
    truncation=0.08
  )
```

通过后（无语法错误），才可加入 `create_multi_simulation` 批量回测。

### 2.6 批量回测

```
→ MCP: create_multi_simulation(
    expressions=[expr1, expr2, expr3, expr4],
    region="<区域>",
    universe="<Universe>",
    delay=1,
    decay=4,
    neutralization="MARKET",
    truncation=0.08
  )
```

### 2.7 范式轮转策略

每 2 批（8 条）至少覆盖 3 种不同交互范式。推荐轮转顺序：

```
Batch 1-2:  P1_SPREAD + P2_RATIO（基础扫描）
Batch 3-4:  P4_REGRESSION + P5_CORRELATION（关系探索）
Batch 5-6:  P7_DIVERGENCE + P3_CONDITIONAL（高级结构）
Batch 7-8:  P6_EVENT + 最佳范式复用（事件驱动 + 利用）
```

### 2.8 第一轮示例批次

假设字段 `field_A`（Growth 类）和 `field_B`（Quality 类）：

**Batch 1（P1+P2 基础扫描）**：
```
1. rank(ts_zscore(subtract(field_A, field_B, filter=true), 66))           # P1 Spread
2. group_rank(ts_zscore(divide(field_A, field_B), 66), industry)          # P2 Ratio
3. zscore(ts_delta(subtract(field_A, field_B, filter=true), 22))          # P1 变体
4. rank(ts_rank(divide(field_A, field_B), 126))                           # P2 变体
```

**Batch 2（P4+P5 关系探索）**：
```
1. group_rank(ts_regression(field_A, field_B, 66), subindustry)           # P4 Regression
2. rank(ts_corr(ts_delta(field_A, 5), ts_delta(field_B, 5), 66))         # P5 Correlation
3. zscore(ts_regression(field_A, field_B, 126))                           # P4 长窗口
4. group_zscore(ts_corr(field_A, field_B, 126), sector)                   # P5 分组
```

---

## Stage 3: 评估闸门

### 3.1 单批评估决策

```
|Sharpe| ≥ 0.9   → 🟢 进入 Stage 4 做模板增强
0.7 ≤ |Sharpe| < 0.9  → 🟡 记录为候选，继续探索其他字段对
0.4 ≤ |Sharpe| < 0.7  → 🟠 尝试不同交互范式，再给 2 批机会
|Sharpe| < 0.4   → 🔴 切换字段对（当前配对无信号）
```

### 3.2 推进门槛

- 累计 ≥ **10 个** Sharpe≥0.7 & Fitness≥0.5 的组合 → 进入 Stage 4
- 累计满 **50 批**（200 条）仍未达 10 个 → 标记 PROBABLE_FAIL，报告后切换数据集

### 3.3 快速失败规则

- 连续 **8 批**（32 条）最高 Sharpe < 0.7 → 立即标记 PROBABLE_FAIL
- 连续 **4 批** 出现相同方向的 Sharpe（全正或全负）且均 < 0.4 → 数据集信号弱，切换

### 3.4 每批输出格式

```markdown
## Batch N 结果 (数据集: xxx, 区域: xxx)

| # | Expression | Sharpe | Fitness | TVR | Margin | Returns | DD | 决策 |
|---|-----------|--------|---------|-----|--------|---------|-----|------|
| 1 | rank(ts_zscore(divide(A,B),66)) | 1.42 | 0.95 | 14% | 12bp | 6.8% | 4.2% | → Stage 4 |
| 2 | group_rank(ts_delta(subtract(A,B,filter=true),22),ind) | 0.87 | 0.68 | 18% | 8bp | 5.1% | 6.3% | 🟡 候选 |
| 3 | zscore(ts_regression(A,B,66)) | 0.41 | 0.35 | 22% | 6bp | 3.2% | 5.8% | 🔴 切换 |
| 4 | rank(ts_rank(A,126)) | 0.73 | 0.55 | 11% | 9bp | 4.5% | 3.1% | 🟠 再探 |

**累计进度**: 候选 7/10 | 已回测 48/200 | 最佳 Sharpe: 1.42
```

---

## Stage 4: 模板增强与参数优化

### 4.1 模板增强方向

对 Stage 3 筛出的候选（Sharpe ≥ 0.7），应用以下增强：

#### 4.1.1 分组操作增强
```python
# 从 rank() → group_rank()
group_rank(ts_zscore(divide(A, B), 66), industry)        # 行业内排名
group_rank(ts_zscore(divide(A, B), 66), subindustry)     # 子行业内排名
group_rank(ts_zscore(divide(A, B), 66), sector)          # 板块内排名
```

#### 4.1.2 非线性变换
```python
# signed_power 压缩/放大
signed_power(group_rank(ts_zscore(divide(A, B), 66), industry), 0.5)  # 压缩极值
signed_power(group_rank(ts_zscore(divide(A, B), 66), industry), 1.5)  # 轻度放大
signed_power(group_rank(ts_zscore(divide(A, B), 66), industry), 3.0)  # 强放大
```

#### 4.1.3 条件过滤叠加
```python
# 在最佳表达式上叠加条件过滤
trade_when(ts_delta(B, 22) > 0, group_rank(ts_zscore(divide(A, B), 66), industry))
if_else(ts_delta(B, 22) > 0, group_rank(ts_zscore(divide(A, B), 66), industry), 0)
```

#### 4.1.4 窗口变体
```python
# 测试不同时序窗口
group_rank(ts_zscore(divide(A, B), 22), industry)   # 短窗口（1个月）
group_rank(ts_zscore(divide(A, B), 66), industry)   # 中窗口（3个月）
group_rank(ts_zscore(divide(A, B), 126), industry)  # 长窗口（6个月）
group_rank(ts_zscore(divide(A, B), 252), industry)  # 超长窗口（1年）
```

### 4.2 参数优化（仅对 Sharpe ≥ 0.9 的候选）

#### 4.2.1 Decay 遍历
按字段更新频率选择遍历范围：

| 更新频率 | 遍历范围 | 推荐值 |
|---------|---------|--------|
| 日更 | {0, 2, 4, 6, 10} | 2–4 |
| 周/月更 | {0, 1, 2, 4} | 0–2 |
| 季/年更 | {0, 1} | 0 |

```
→ MCP: create_multi_simulation(
    expressions=[同一表达式 × 4],
    decay=[0, 2, 4, 6],  # 一批搞定
    ...其他参数不变
  )
```

#### 4.2.2 Neutralization 遍历

```
→ MCP: create_multi_simulation，每次换一种 neut:
  - MARKET（基线）
  - SLOW
  - FAST
  - SLOW_AND_FAST（如有）
```

### 4.3 论坛模板搜索

```
→ MCP: search_forum_posts(keyword="<数据集名称>")
→ MCP: get_documentations(category="Alpha Examples")
```

从论坛获取该数据集的已验证模板，提取有效结构应用到当前字段对。

### 4.4 硬闸门校验

达到以下全部标准才进入 Stage 5：

```
[ ] Sharpe > 1.3
[ ] Fitness > 0.75
[ ] Margin > 10bp（USA > 5bp）
[ ] TVR: 5%–20%
[ ] Returns > 5% & > Drawdown
[ ] 最近年 Sharpe ≥ 1.0
[ ] 近两年每年 Sharpe ≥ 0.8
[ ] 最近年 Fitness ≥ 0.4
```

---

## Stage 5: 去重与稳健性验证

### 5.1 相关性检查

```
→ MCP: check_correlation(alpha_id="<Alpha ID>")
```

| 指标 | 通过标准 | 可修复 | 硬淘汰 |
|------|---------|--------|-------|
| ProdCorr | < 0.70 ✅ | 0.70–0.85 🟡 | ≥ 0.85 🔴 |
| SelfCorr | < 0.50 ✅ | — | ≥ 0.50 🔴 |

### 5.2 ProdCorr 修复策略（0.70–0.85 区间）

按优先级依次尝试：

1. **换分组变量**：industry → subindustry → sector
2. **加 signed_power**：signed_power(expr, 1.5) 可降 ProdCorr ~0.01–0.05
3. **换 TRANSFORM 算子**：ts_zscore → ts_rank → ts_quantile
4. **加条件门控**：trade_when 过滤低信号区间
5. **换 neut**：FAST vs SLOW 可显著改变 ProdCorr 分布

每次修复后重新回测 → `check_correlation`。最多 2 轮修复。

### 5.3 提交预检

```
→ MCP: get_submission_check(alpha_id="<Alpha ID>")
```

确认所有检查项 PASS 或 WARNING（WARNING 一般不阻止提交）。

### 5.4 年度一致性检查

从回测结果中提取年度 Sharpe：

```
[ ] 最近一年 Sharpe ≥ 1.0
[ ] 近两年每年 Sharpe ≥ 0.8
[ ] 最近一年 Fitness ≥ 0.4
[ ] 信号衰减: last-year Sharpe ≥ 全期 Sharpe × 30%
```

---

## Stage 6: 提交与文档化

### 6.1 提交

```
→ MCP: submit_alpha(alpha_id="<Alpha ID>")
```

### 6.2 设置属性

```
→ MCP: set_alpha_properties(
    alpha_id="<Alpha ID>",
    name="<DatasetName>_<FieldA>_<FieldB>_<Region>_<Neut>",
    tags="PowerPoolSelected",
    description="Idea: <一句话描述信号逻辑>\nRationale for data used: <数据集和字段选择理由>\nRationale for operators used: <操作符选择理由>"
  )
```

**规则**：
- name 不能带空格（用下划线连接）
- description 用英文，≤ 100 词
- tags 固定为 `PowerPoolSelected`

### 6.3 记录提交

在 `tracking/` 下创建会话记录：

```markdown
## 提交记录

| 项目 | 值 |
|------|---|
| Alpha ID | xxxxxxxx |
| Expression | ... |
| Dataset | ... |
| Fields | field_A, field_B |
| Region | USA |
| Universe | TOP3000 |
| Delay | D1 |
| Neutralization | FAST |
| Decay | 6 |
| Truncation | 0.08 |
| Sharpe | 1.82 |
| Fitness | 1.15 |
| TVR | 12.3% |
| Margin | 18bp |
| Returns | 7.2% |
| Drawdown | 5.1% |
| ProdCorr | 0.62 |
| SelfCorr | 0.38 |
```

### 6.4 经验沉淀

提交成功后记录以下发现：
- 哪些字段对有信号、哪些无信号
- 最佳交互范式和操作符组合
- decay/neut/window 的最优参数
- ProdCorr 修复是否有效

---

## 附录 A: 完整会话执行模板

```
[用户输入] 请挖掘 analyst15 数据集，区域 ASI

[Agent 执行]
1. authenticate → 获取 token
2. get_platform_setting_options → 确认 ASI: MINVOL1M/D1/max_trade=ON
3. get_datasets(search="analyst15") → 获取数据集 ID
4. get_datafields(dataset_id=..., region="ASI") → 获取所有字段
5. 字段分类 + 配对 → 生成 15-20 对字段组合
6. Stage 2 循环:
   a. 构建 4 条表达式（ATLAS 合规，双字段交互）
   b. create_multi_simulation → 回测
   c. Stage 3 评估 → 决策
7. Stage 4:
   a. 对候选做模板增强
   b. 参数优化（decay/neut 遍历）
8. Stage 5:
   a. check_correlation → ProdCorr/SelfCorr
   b. 修复（如需）
9. Stage 6:
   a. submit_alpha
   b. set_alpha_properties
   c. 记录
```

---

## 附录 B: 常见问题与解决方案

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| Sharpe 全批 < 0.5 | 字段无信号 | 切换字段对或数据集 |
| TVR > 40% | 表达式过于敏感 | 加 decay / 换 ts_rank(长窗口) / 加 hump |
| TVR < 5% | 信号过于稳定 | 减小窗口 / 减小 decay / 用 ts_delta 代替 ts_rank |
| Margin < 5bp | 信号方向一致性弱 | 换 neut / 加 group_rank / 换字段对 |
| ProdCorr > 0.70 | 与已有 Alpha 相关 | 换 TRANSFORM / 加 signed_power / 换分组 |
| Fitness < 0.5 | 信号不稳定 | 加长窗口 / 换 ts_quantile / 加 decay |
| Returns < Drawdown | 风险收益比差 | 加条件过滤 / 换字段对 |
| 语法错误 | 参数/括号不匹配 | 检查 get_operators 确认签名 |
