# 全局挖矿经验（自总结）

> 来源：`tabbit_Alpha模板总结.md`、`tabbit_算子含义及用法说明.md`、`reference/{atlas,templates,regions}.md`、`workflow.md`，以及本轮 USA fundamental/PPA 实战。

---

## 1. 选场优先级（比表达式更重要）

1. **先抢低竞争新数据集**：Data 页看 `alphaCount≈0` / 新上线字段；同一表达式只有第一批提交者拿满分。
2. **金字塔倍率**：如 `earnings_sent_matrix` 在 ILLIQUID 上 multiplier≈1.3，优先于已饱和 fundamental。
3. **Universe 降竞争**：USA 上 `ILLIQUID_MINVOL1M` 常比 `TOP3000` 好挖（tabbit 验证）。
4. **区域默认**：USA/TOP3000/D1；EUR/TOPCS1600；ASI 强制 `max_trade=ON`。

## 2. 表达式骨架（ATLAS L1→L6）

| 层 | 作用 | 常用 |
|---|---|---|
| L1 | 构特征 | `subtract(...,filter=true)` / `divide`；禁 add/multiply 混信号 |
| L2 | 时序 | `ts_backfill`→`ts_zscore/ts_rank/ts_av_diff/ts_quantile/ts_scale/ts_arg_max` |
| L4/L5 | 截面 | `rank` 或 `group_rank(..., industry)` 二选一，勿双重标准化 |
| L6 | 整形 | `signed_power(x, p)`：p&lt;1 抬 Fitness，p&gt;1 抬尖峰 |

**低频事件（earnings/情绪）核心模板（tabbit）**：

```text
ts_op(ts_backfill(field, days1), days2)
# days1 ∈ {10, 252}；days2 = 252
# ts_op ∈ {ts_zscore, ts_av_diff, ts_quantile, ts_scale, ts_arg_max, ts_rank}
# 变体：ts_mean 替代 ts_backfill；或嵌套 ts_op(ts_op(...), days2)
```

**双字段 PPA 优先范式**：P1 价差 / P4 回归 / P5 相关（负相关记得翻转）。

## 3. 设置扫描经验（USA D1）

| 设置 | 经验 |
|---|---|
| FAST | 常抬全期 Sharpe，Fitness 易过；本轮 fnd93 卡在 S≈1.55 |
| STATISTICAL | 易过 Sharpe/2Y，Fitness 偏低；用 **低 signed_power(0.15–0.3)** 可同时过 S+F |
| decay | 事件/低频用 0–2；日更可 2–4 |
| truncation | 默认 0.08；微调 0.05–0.12 影响有限 |
| pasteurization/nan | 默认 ON |

**硬闸门**：ProdCorr 必须出且 &lt;0.7；SelfCorr&lt;0.7；PPA 打 `PowerPoolSelected`。

## 4. 平台快速回测（高吞吐、避 429）

| 做法 | 原因 |
|---|---|
| **每次 `create_multi_simulation` 填满 8 条** | 一次占用 1 个仿真槽，吞吐最大 |
| **串行多批 multi，禁止并行多个 `create_simulation`** | 并行易 401/429/MCP 断连 |
| **批间冷却 30–90s**（遇 429 则 120s+） | 限流来自请求突发，不是 8 槽本身 |
| **先本地拼好表达式再提交** | 减少无效往返 |
| **坏算子隔离**：`hump/tail` 参数错会 CANCEL 整批 | 每批只放已验证语法 |
| **同结构只扫关键轴** | 字段×算子×days1×neut，勿全网格 |

目标节奏：约每 8–12 分钟消化 8 条 → 约 40–60 条/小时（单槽）。

## 5. 失败切换规则（workflow）

- 连续多批 max Sharpe≪门槛 → 换字段对或换数据集  
- 单字段事件模板：优先未验证字段（如 `likelihood_of_neutral_tone`）+ 已验证字段对照  
- PPA 与 RA 路径分开记 tracking，勿混宇宙/中性化默认值  

## 6. ProdCorr 降相关杠杆（earnings 饱和模板）

裸 `ts_zscore(ts_backfill(...))` IS 很强（S>2.5）但 ProdCorr 常 0.8–0.95。有效组合：

1. **外层 `group_rank(..., industry)`** + **STATISTICAL** 中性化 → 本轮把 ProdCorr 从 ~0.88 压到 **0.67–0.70**
2. 翻转负向字段可抬 Sharpe，但未必降 ProdCorr（仍常 >0.77）
3. `signed_power` / 双字段 subtract 主要改 IS 形态，对 ProdCorr 帮助有限

提交闸门：先 `check_correlation` 确认数值，再提交；MCP `submit_alpha` 若序列化失败，用 `POST /alphas/{id}/submit` + 轮询 GET。

## 7. 本仓库已验证锚点

- **fnd93**（TOP3000）：`signed_power(group_rank(ts_zscore(subtract(ts_backfill(max,150),ts_backfill(min,150),filter=true),630),industry),0.15)` + **STATISTICAL** → `O0xagXjd` S=1.67/F=1.0，ProdCorr≈0.64（已提交 OS/ACTIVE）
- **earnings_sent_matrix**（ILLIQUID）：已提交 `vRvg7NzA` = `group_rank(ts_zscore(overall_sentiment_score),industry)` STAT，ProdCorr≈0.675
- 次日候选：换 **ts_rank/ts_quantile + method1 翻转**（勿再用同结构 zscore）；`bld3p6Al` 本地 SelfCorr≈0.62；`ZYKLGVex` S=2.91
- **tabbit 锚点字段**：USA `sentiment_weighting_method1`（翻转）/ `overall_sentiment_score`  



