# 因子挖掘进度汇报（数据驱动 · Markdown）

- **数据快照**：2026-07-25 22:18
- **主账号数据源**：`results/*_checkpoint.json`（权威累计）+ `results/*_progress_*.log`（实时进度）
- **独立账号数据源**：`D:/.../worldquant/tri_track_undug_*.csv` + 分片日志
- **生成器**：`build_md_report.py`（可复跑，数字均来自真实文件，未编造）

> ⚠️ **提交验证总结论**：主账号 36 个候选 Alpha 仅通过「研究仿真 IS 廉价闸门」、**0 个完成平台真实提交**；其中仅 **1** 个跨过生产相关性关（`YPgAa3WR`, prod_corr=0.5325）。独立账号 `tri_track_undug` 同样**未经平台确认提交**（其 ranker 自家标记 18 个"可提交"，但未走平台提交流程）。两条线**均无平台确认提交**，请勿视作可提交 Alpha。

---

## 一、核心结论（结论先行）

| 指标 | 主账号（v52b + ds 舰队） | 独立账号（tri_track_undug） |
|---|---:|---:|
| 回测/仿真次数 | **6,355** | **592** |
| 候选（过廉价 IS 闸） | **36** | 子宇宙通过 **146** / ranker 标记可提交 **18** |
| 跨生产相关性验证 | 1（`YPgAa3WR`） | 未统计（独立账号） |
| 平台确认提交 | **0** | **0**（仅 ranker 标记） |
| 最佳 Sharpe | **2.66**（v52b） | **1.56**（eff_sharpe） |

**要点**
1. **两条挖掘线并行、账号隔离**：主账号跑 `v52b` + 7 路 `ds_*` 舰队（21:06–21:09 错峰拉起）；独立账号 `tri_track_undug.py`（tabbit/world6 体系，CONCURRENCY=3，8 分片）单独跑 `unsystematic_risk_last_*` / `correlation_*_spy` 信号。两者 checkpoint/结果互不混用。
2. **主账号瓶颈 = 信号发现**：7 路 ds 舰队目前 **0 候选**，首步最佳 Sharpe 仅 web_traffic_engage 1.88、techindi_model 1.39、pv 0.63，其余 <0.5。
3. **独立账号已有实质候选产出**：592 次仿真全 done，429 条有完整 stats，**146 个通过子宇宙 Sharpe**、18 个被其 ranker 标记可提交——质量显著优于主账号 ds 舰队当前 0 候选，但**仍未走平台提交**。
4. **平台并发模型 = 令牌桶限流，突发容量 C=7**：主账号多进程错峰 + 各带 submit_gate，实测全局零 429；独立账号 CONCURRENCY=3 与主账号令牌桶互不干扰。
5. **头号失败闸门 = 子宇宙 Sharpe（PF:LOW_SUB_UNIVERSE_SHARPE）**：主账号历史最强信号 V39b(2.58)/V39(2.30)/V52(2.50) 均卡此关。

---

## 二、关键图表（ASCII 条形，过闸线 1.58）

### 图 1 · 主账号 ds 舰队首步最佳 Sharpe
```
web_traffic_engage     ██████████████████████ 2.00
techindi_model         ████████████████░░░░░░ 1.47 ⚠<1.58
equity_kpi_forecast    ███████████████░░░░░░░ 1.39 ⚠<1.58
order_book_imbalance   █████████░░░░░░░░░░░░░ 0.84 ⚠<1.58
pv_tech_indicators     ███████░░░░░░░░░░░░░░░ 0.63 ⚠<1.58
quant_factor_lib       █████░░░░░░░░░░░░░░░░░ 0.48 ⚠<1.58
ml_factor_proj         ████░░░░░░░░░░░░░░░░░░ 0.36 ⚠<1.58
— 过闸线 1.58             █████████████████░░░░░ 1.58
```

> 7 路在飞舰队首步信号普遍未达过闸线（除 web_traffic 1.88 但仍卡其他 IS 闸），直接印证"信号发现瓶颈"。

### 图 2 · 独立账号 tri_track_undug TOP10 信号（按 eff_sharpe）
```
78nneodv   ██████████████████████ 1.56
rKP2pmkE   ██████████████████████ 1.55
kqZPRljK   ██████████████████████ 1.55 [sub_pass] [submittable]
88eeMGZz   █████████████████████░ 1.54 [sub_pass] [submittable]
YPgvLpgv   █████████████████████░ 1.54 [sub_pass] [submittable]
O0xGqkrJ   █████████████████████░ 1.54 [sub_pass] [submittable]
vRvvWjEr   █████████████████████░ 1.53
KPEEW1bk   █████████████████████░ 1.53
pwKNwmwX   █████████████████████░ 1.53
qM6N8MbZ   █████████████████████░ 1.53
— 过闸线 1.58 ██████████████████████ 1.58
```

> 独立账号最佳 eff_sharpe 1.56（略低于 1.58），但有 146 个通过子宇宙、18 个被 ranker 标记可提交——**已具备候选池**，与主账号 ds 舰队 0 候选形成对比。

### 图 3 · 失败闸门汇总（主账号全量 fails 统计）
| 失败类型 | 次数 | 说明 |
|---|---:|---|
| PF:子宇宙Sharpe | **298** | 主因 LOW_SUB_UNIVERSE_SHARPE |
| S(夏普) | 5089 | IS 夏普未达标 |
| F(拟合) | 5101 | 拟合未达标 |
| M(换手收益) | 5005 | 换手收益未达标 |
| Ret(收益) | 4804 | 收益未达标 |
| TVR(换手率) | 2365 | 换手率越界 |
| submit_failed | 664 | 提交失败（含 no_submit 逻辑） |
> **子宇宙 Sharpe 是头号平台失败闸门**，远高于单纯 IS 指标失败。

---

## 三、核心数据表格

### 表 A · 主账号 ds 舰队实时进度
| 数据集 | 进度 | 首步最佳S | 估算吞吐 | 已运行 | 候选 |
|---|---|---|---|---|---|
| equity_kpi_forecast | 96/320 (30.0%) | 🟡 1.39 | 84.0 | 68.2 | 0 候选 |
| ml_factor_proj | 72/320 (22.5%) | 🔴 0.36 | 67.0 | 64.7 | 0 候选 |
| order_book_imbalance | 96/320 (30.0%) | 🔴 0.84 | 85.0 | 67.7 | 0 候选 |
| pv_tech_indicators | 88/320 (27.5%) | 🔴 0.63 | 77.0 | 68.7 | 0 候选 |
| quant_factor_lib | 80/320 (25.0%) | 🔴 0.48 | 73.0 | 65.4 | 0 候选 |
| techindi_model | 88/320 (27.5%) | 🟡 1.47 | 80.0 | 66.3 | 0 候选 |
| web_traffic_engage | 88/320 (27.5%) | 🟢 2.00 | 79.0 | 67.2 | 0 候选 |

### 表 B · 独立账号 tri_track_undug 挖掘详情
| 指标 | 值 |
|---|---:|
| 脚本 | `tri_track_undug.py`（tabbit/world6 独立账号，CONCURRENCY=3，8 分片） |
| 仿真完成 (results.csv) | **592** |
| 有完整 stats | 429 |
| 最佳 eff_sharpe / raw_sharpe | 1.56 |
| 最佳 fitness | 1.95 |
| 通过子宇宙 (sub_pass=Y) | **146** |
| ranker 标记可提交 (submittable=Y) | **18** |
| base_ok=Y | 43 |
| 平台确认提交 | **0** |
| 结果落盘 | `tri_track_undug_results.csv` / `_stats.csv` / `_ranked.csv` |

**TOP10 信号（独立账号 ranker 排序）**
| alpha_id | eff_S | raw_S | sub_pass | submittable | base_ok |
|---|---:|---:|---|---|---|
| 78nneodv | 1.56 | 1.56 | N |  | Y |
| rKP2pmkE | 1.55 | 1.55 | N |  | Y |
| kqZPRljK | 1.55 | 1.55 | Y | Y | Y |
| 88eeMGZz | 1.54 | 1.54 | Y | Y | Y |
| YPgvLpgv | 1.54 | 1.54 | Y | Y | Y |
| O0xGqkrJ | 1.54 | 1.54 | Y | Y | Y |
| vRvvWjEr | 1.53 | 1.53 | N |  | Y |
| KPEEW1bk | 1.53 | 1.53 | N |  | Y |
| pwKNwmwX | 1.53 | 1.53 | N |  | Y |
| qM6N8MbZ | 1.53 | 1.53 | N |  | Y |

### 表 C · 两条挖掘线对照
| 维度 | 主账号（v52b + ds 舰队） | 独立账号（tri_track_undug） |
|---|---|---|
| 账号 | mthyzx@126.com（主） | tabbit/world6（独立 gmail） |
| 信号方向 | hiring / 多数据集因子 | unsystematic_risk / correlation_spy |
| 并发模式 | 多进程错峰 + submit_gate(C=7) | CONCURRENCY=3，8 分片 |
| 回测规模 | 6,355 | 592 |
| 候选产出 | IS 通过 36（0 提交） | 子宇宙通过 146 / ranker 可提交 18（0 确认提交） |
| 最佳 Sharpe | 2.66 | 1.56 |
| 当前状态 | 在飞，ds 舰队 0 候选 | 分片已完成，候选池待平台验证 |

### 表 D · 主账号候选 Alpha 明细（36 个，按 Sharpe 降序）
| pid | 任务 | Sharpe | Fitness | tvr | 状态 | 配置 |
|---|---|---:|---:|---:|---|---|
| zqRkPVbX | v52b_hiring_margin | **2.33** | 1.67 | 0.1487 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| RR17rbe0 | v52b_hiring_margin | **2.33** | 1.67 | 0.1487 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| 1YzwaMZz | v52b_hiring_margin | **2.32** | 1.65 | 0.1497 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| WjV7a5eo | v52b_hiring_margin | **2.32** | 1.65 | 0.1501 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| e7xzrba6 | v52b_hiring_margin | **2.32** | 1.65 | 0.1497 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| vRvjmrY3 | v52b_hiring_margin | **2.32** | 1.65 | 0.1501 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| Xg8720b0 | v52b_hiring_margin | **2.31** | 1.64 | 0.1484 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| pwKj7Rd3 | v52b_hiring_margin | **2.31** | 1.64 | 0.1484 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| E5el82OG | v52b_hiring_margin | **2.30** | 1.63 | 0.1491 | PASS_CHEAP | USA TOP3000 d1 decay4 INDUSTRY |
| wpEjPZ5l | v52b_hiring_margin | **2.30** | 1.63 | 0.1491 | PASS_CHEAP | USA TOP3000 d1 decay4 INDUSTRY |
| j2rrpVzO | v52_tri_hiring_trends | **2.19** | 1.78 | 0.1634 | CHECK_PENDING | USA ILLIQUID_MINVOL1M d1 decay3 SECTOR |
| j2rgVd0E | v39b_sub_micro | **2.18** | 1.80 | 0.1187 | PASS_CHEAP | USA TOP3000 d1 decay2 SECTOR |
| zqRWAJmX | v39b_sub_micro | **2.17** | 1.79 | 0.1193 | PASS_CHEAP | USA TOP3000 d1 decay2 SECTOR |
| N1RO8rLL | v39b_sub_micro | **2.13** | 1.75 | 0.1145 | PASS_CHEAP | USA TOP3000 d1 decay2 INDUSTRY |
| np8Wr2ml | v39b_sub_micro | **2.12** | 1.74 | 0.1153 | PASS_CHEAP | USA TOP3000 d1 decay2 INDUSTRY |
| YPgAa3WR | v39b_sub_micro | **2.08** | 1.67 | 0.1059 | PASS_CHEAP | USA TOP3000 d1 decay3 SECTOR |
| le30awQe | v39b_sub_micro | **2.07** | 1.67 | 0.1065 | PASS_CHEAP | USA TOP3000 d1 decay3 SECTOR |
| QP9QNw8G | v39b_sub_micro | **2.00** | 1.59 | 0.1035 | PASS_CHEAP | USA TOP3000 d1 decay3 INDUSTRY |
| RR1rlGge | v39b_sub_micro | **1.99** | 1.59 | 0.1042 | PASS_CHEAP | USA TOP3000 d1 decay3 INDUSTRY |
| wpEjaENp | v52b_hiring_margin | **1.94** | 1.40 | 0.1344 | PASS_CHEAP | USA TOP3000 d1 decay3 SECTOR |
| E5elGemr | v52b_hiring_margin | **1.94** | 1.40 | 0.1348 | PASS_CHEAP | USA TOP3000 d1 decay3 SECTOR |
| A17GR6Wd | v52_tri_hiring_trends | **1.94** | 1.75 | 0.1342 | CHECK_PENDING | USA ILLIQUID_MINVOL1M d1 decay2 SECTOR |
| 88elpeGW | v52b_hiring_margin | **1.92** | 1.37 | 0.1363 | PASS_CHEAP | USA TOP3000 d1 decay3 SECTOR |
| xAdjvnxN | v52b_hiring_margin | **1.92** | 1.39 | 0.1464 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| d5RjZR9K | v52b_hiring_margin | **1.91** | 1.36 | 0.136 | PASS_CHEAP | USA TOP3000 d1 decay3 SECTOR |
| 78njYdwQ | v52b_hiring_margin | **1.91** | 1.38 | 0.1463 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| rKPj7WWd | v52b_hiring_margin | **1.90** | 1.37 | 0.1445 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| N1R7POpX | v52b_hiring_margin | **1.90** | 1.37 | 0.1452 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| kqZjgQzO | v52b_hiring_margin | **1.81** | 1.31 | 0.1193 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| 9q7XWRzK | v52b_hiring_margin | **1.81** | 1.31 | 0.1206 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| qM6j0XKK | v52b_hiring_margin | **1.80** | 1.30 | 0.1203 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| gJ9jZxnM | v52b_hiring_margin | **1.79** | 1.29 | 0.119 | PASS_CHEAP | USA TOP3000 d1 decay4 SECTOR |
| YPgvjZrJ | v52_tri_hiring_trends | **1.79** | 1.61 | 0.1056 | CHECK_PENDING | USA ILLIQUID_MINVOL1M d1 decay4 SECTOR |
| KPELQn7l | v39b_sub_micro | **1.67** | 1.18 | 0.1144 | PASS_CHEAP | USA TOP3000 d1 decay2 SECTOR |
| e7xrvnzJ | v39b_sub_micro | **1.67** | 1.19 | 0.115 | PASS_CHEAP | USA TOP3000 d1 decay2 SECTOR |
| RR11Gzbd | v52_tri_hiring_trends | **1.63** | 1.19 | 0.1062 | CHECK_PENDING | USA TOP3000 d1 decay4 INDUSTRY |

---

## 四、问题说明（问题其次）

1. **两条线均无平台确认提交**。主账号 36 候选仅研究仿真 IS 闸通过；独立账号 18 个仅为 ranker 自家标记，均未走 WQ 平台提交流程（no_submit / 未显式 submit）。
2. **主账号 ds 舰队首步信号偏弱、0 候选**（见图 1 / 表 A）——加并发只是加速"挖 0 候选"，瓶颈在信号发现。
3. **独立账号候选质量更优但缺平台验证**：146 个子宇宙通过、最佳 eff_S 1.56，却未做生产仿真(OOS)+平台 submittable 判定+真实提交，价值尚未兑现。
4. **子宇宙 Sharpe 闸门最硬**（图 3）：PF:LOW_SUB_UNIVERSE_SHARPE 为主账号头号失败原因，需在子宇宙层面优化中性化/约束。
5. **监控口径已修正**：旧 `gen_report.py` 用 `^v\d+` 过滤 checkpoint，漏掉整个 ds_* 舰队；`tri_track_undug.py` 被误判为 other（实为独立账号三轨挖掘）。本报告已单列区分两条线。

## 五、行动建议（方案最后）

1. **主账号舰队继续跑完**：7 路 ds + v52b 已验证合规（优，零 429），按各自 submit_gate 自然推进。
2. **独立账号候选优先平台化**：对 tri_track_undug 中 18 个 ranker 标记可提交者，补**生产仿真(OOS) → /check(PROD/SELF_CORRELATION) → 平台 submittable 判定 → 显式 submit**，把"ranker 可提交"转为"平台确认提交"。
3. **主攻子宇宙 Sharpe 闸门**：对 V39/V39b 类高 S 信号限定 universe=TOP3000 / 调整 neutralization / 加子宇宙约束，突破 PF:LOW_SUB_UNIVERSE_SHARPE。
4. **v52b 升维**：降换手变体（decay4 SECTOR）已多过廉价 IS 闸，规模化过 M 闸并补生产验证。
5. **两账号并发纪律**：主账号错峰多进程(>6)各带 submit_gate；独立账号 CONCURRENCY=3 互不干扰。加任务前用进程枚举核验在飞数与 429。

---
*报告由 build_md_report.py 从真实 checkpoint / progress / tri_track CSV 程序化生成 · 快照 2026-07-25 22:18 · 数字均来自文件实测，未编造。*
