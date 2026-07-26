# 三维层级钻取（账号 → 模板 → 日期）

> 生成时间：2026-07-27 02:16 GMT+8
> 从 79 个因子模板 / 17,051 回测记录中提取

## 一、层级结构概览

```
🚢 主账号 mthyzx
├── 📦 v系列独立模板 (25 个)
│   ├── v52b_hiring_margin                  S⚡2.66  N= 160 🔥28候选
│   ├── v39b_sub_micro                      S⚡2.58  N= 160 🔥10候选
│   ├── v52_tri_hiring_trends               S⚡2.50  N= 320 🔥4候选
│   ├── v39_insider_rescue                  S⚡2.30  N= 240
│   ├── v34_insider_matrix                  S⚡1.95  N=  72
│   ├── v51_tri_behavioral_signals          S⚡1.72  N= 320
│   └── ... +19 个
│
├── 🌐 ds 舰队 (44 个数据集)
│   ├── ds_dl_riskfree_returns_tri_dl_riskfree_returns     S⚡2.33  N=320
│   ├── ds_web_traffic_engage_tri_web_traffic_engage       S⚡2.27  N=320
│   ├── ds_model313_tri_model313                           S⚡2.00  N=40
│   ├── ds_earningscall_sentiment_tri_earningscall_sentime S⚡1.67  N=320
│   ├── ds_workforce_flow_skills_tri_workforce_flow_skills S⚡1.63  N=320
│   └── ... +39 个数据集
│
├── 🔧 rescue 救援 (6 个)
│   ├── rescue_r3_web_lift                                 S⚡2.11
│   ├── rescue_auto_model313_lift                          S⚡1.57
│   ├── rescue_tvr_r2_web                                  S⚡1.40
│   └── ... +3 个
│
└── 🛡️ 独立账号 ML88164
    ├── tri_track_undug  (三轨挖掘)
    └── continuous_undug  (连续未挖数据集调度)
```

> **统计**：79 模板、44 个 ds 数据集、6 个救援、25 个独立变体序列。

## 二、Top 模板详览（按 Sharpe 降序，前 12）

仅展开最佳 Sharpe ≥ 1.0 的 Top 模板。完整 79 模板的全量数字见第五、第八节明细文件。

### 🔥 v52b_hiring_margin

> 信号字段：`aggregate_open_positions_count` · 配置：TOP3000 d2 SEC · 回测日期：2026-07-25

| 指标 | 数值 |
|---|---|
| 回测量 | **160** |
| 最佳 Sharpe | **2.66** |
| PASS_CHEAP | **28** |

**回测日期明细：**

| 日期 | 回测N | PASS_CHEAP | 最佳S |
|---|---:|---:|---:|
| 2026-07-25 | 160 | 28 | 2.66 |


### 🔥 v39b_sub_micro

> 信号字段：`eur_aggregated_value_2` · 配置：TOP2000 d4 SEC · 回测日期：2026-07-24

| 指标 | 数值 |
|---|---|
| 回测量 | **160** |
| 最佳 Sharpe | **2.58** |
| PASS_CHEAP | **10** |

**回测日期明细：**

| 日期 | 回测N | PASS_CHEAP | 最佳S |
|---|---:|---:|---:|
| 2026-07-24 | 160 | 10 | 2.58 |


### 🔥 v52_tri_hiring_trends

> 信号字段：`aggregate_open_positions_count` · 配置：TOP3000 d3 SEC · 回测日期：2026-07-25

| 指标 | 数值 |
|---|---|
| 回测量 | **320** |
| 最佳 Sharpe | **2.50** |
| PASS_CHEAP | **4** |

**回测日期明细：**

| 日期 | 回测N | PASS_CHEAP | 最佳S |
|---|---:|---:|---:|
| 2026-07-25 | 320 | 4 | 2.50 |


###  ds_dl_riskfree_returns_tri_dl_riskfree_returns

> 信号字段：`predicted_return_10day_horizon` · 配置：TOP3000 d2 SEC · 回测日期：2026-07-26

| 指标 | 数值 |
|---|---|
| 回测量 | **320** |
| 最佳 Sharpe | **2.33** |
| PASS_CHEAP | **0** |


###  v39_insider_rescue

> 信号字段：`eur_aggregated_value_1` · 配置：TOP3000 d4 SEC · 回测日期：2026-07-24

| 指标 | 数值 |
|---|---|
| 回测量 | **240** |
| 最佳 Sharpe | **2.30** |
| PASS_CHEAP | **0** |


###  ds_web_traffic_engage_tri_web_traffic_engage

> 信号字段：`total_avg_pages_per_session_to` · 配置：TOP2000 d2 SEC · 回测日期：2026-07-26

| 指标 | 数值 |
|---|---|
| 回测量 | **320** |
| 最佳 Sharpe | **2.27** |
| PASS_CHEAP | **0** |


### 🔥 rescue_r3_web_lift

> 信号字段：`desktop_pageview_count_today` · 配置：TOP2000 d3 SUB · 回测日期：2026-07-26

| 指标 | 数值 |
|---|---|
| 回测量 | **96** |
| 最佳 Sharpe | **2.11** |
| PASS_CHEAP | **5** |

**回测日期明细：**

| 日期 | 回测N | PASS_CHEAP | 最佳S |
|---|---:|---:|---:|
| 2026-07-26 | 96 | 5 | 2.11 |


###  ds_model313_tri_model313

> 信号字段：`mdl313_atlas_unit_name` · 配置：TOP3000 d1 SEC · 回测日期：2026-07-27

| 指标 | 数值 |
|---|---|
| 回测量 | **40** |
| 最佳 Sharpe | **2.00** |
| PASS_CHEAP | **0** |


###  v34_insider_matrix

> 信号字段：`?` · 配置：? d? ? · 回测日期：2026-07-23

| 指标 | 数值 |
|---|---|
| 回测量 | **72** |
| 最佳 Sharpe | **1.95** |
| PASS_CHEAP | **0** |


###  v51_tri_behavioral_signals

> 信号字段：`salience_weighted_return_score` · 配置：TOP3000 d1 SEC · 回测日期：2026-07-25

| 指标 | 数值 |
|---|---|
| 回测量 | **320** |
| 最佳 Sharpe | **1.72** |
| PASS_CHEAP | **0** |


###  ds_earningscall_sentiment_tri_earningscall_sentiment

> 信号字段：`count_negative_assetutilizatio` · 配置：TOP3000 d4 SEC · 回测日期：2026-07-26

| 指标 | 数值 |
|---|---|
| 回测量 | **320** |
| 最佳 Sharpe | **1.67** |
| PASS_CHEAP | **0** |


###  ds_workforce_flow_skills_tri_workforce_flow_skills

> 信号字段：`employee_headcount` · 配置：TOP3000 d4 SUB · 回测日期：2026-07-26

| 指标 | 数值 |
|---|---|
| 回测量 | **320** |
| 最佳 Sharpe | **1.63** |
| PASS_CHEAP | **0** |


---
*完整 79 模板的全量数据见 [Sharpe 排名明细](detail_sharpe_ranking.md) 和 [候选 Alpha 列表](detail_candidates.md)。*