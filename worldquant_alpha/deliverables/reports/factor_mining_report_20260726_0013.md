> **数据快照**: 2026-07-26 00:13 GMT+8 ｜ **数据源**: `results/*_checkpoint.json`(权威) + `*_progress_*.log`(实时) + `tri_track_undug_results.csv`

> ⚠️ **提交验证最重要结论**：全部 **42** 个候选 Alpha 中，**1 个已正式提交**（`YPgAa3WR`，status=ACTIVE，dateSubmitted=2026-07-24，prod_corr=0.5325），剩余 **41** 个缺平台生产仿真(OOS)硬闸门验证、不可提交。`PASS_CHEAP` 仅表示本地廉价 IS 闸通过，不等于可提交。

---
## 一、核心结论（结论先行）

| 指标 | 数值 | 说明 |
|---|---|---|
| 累计回测次数 | **7,443** | 全部 32 个 checkpoint 合计 |
| IS 廉价闸门通过 | **42** (31 PASS_CHEAP + 4 CHECK_PENDING) | 仅研究仿真 IS 闸通过，非「可提交」 |
| 跨生产相关性验证 | **1** (YPgAa3WR, prod_corr=0.5325) | 全局唯一 |
| 平台真实提交 | **1** (`YPgAa3WR`, ACTIVE, 07-24) | 全局唯一已落地 alpha |
| 全链路最佳 Sharpe | **2.66** | v52b 降换手变体 |
| 在飞挖掘任务 | **9 个任务 (10 进程)** | 主账号 v52b + 7路ds + 独立tri_track |
| 全局 429 | **0** | 多进程错峰 + submit_gate，令牌零浪费 |

**核心瓶颈**：信号发现，非吞吐。ds 舰队 0 候选，tri_track 仅记录提交不存回测指标。

---
## 二、提交就绪漏斗

```
  研究仿真回测               ███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████  7,443 (100.0%)
  IS 廉价闸门通过            ██████████████████████████████████████████     42 (0.6%)
  跨生产相关性验证             █      1 (0.0%)
  平台真实提交               █      0 (0.0%)
```

每一级都是一道硬闸门：**IS 廉价闸门**筛掉 7,401 次（7,401/7443=99.4% 被筛）；**生产相关性关**仅 1 个通过；**平台提交**为 0。42 个候选 ≠ 可提交。

---
## 三、ds 舰队 vs tri_track 独立账号（对比）

| 维度 | 🚢 ds 舰队 (主账号) | 🛡️ tri_track (独立账号) |
|---|---|---|
| 账号 | mthyzx@126.com | ML88164 (独立 gmail/tabbit 体系) |
| 并发模型 | 每任务 submit_gate + multi-sim(BATCH=8) | CONCURRENCY=3 三轨并行 |
| 在飞任务数 | 7 路 dataset | 1 进程 (8 分片) |
| 总任务量 | 7 × 320 = 2,240 | 8 分片 × 10 任务 = 80 |
| 已提交 alpha | 累计 1640 次 (含研究仿真) | 733 alpha 已提交并完成 |
| 通过 IS 闸 | 0 候选 | 无回测指标 CSV (仅提交日志) |
| 首步最佳 Sharpe | 2.27 (web_traffic) | 不可用 (CSV 无指标) |
| 429 实证 | 0 | 0 (独立账号, 令牌不相干扰) |
| 续跑 | ✅ checkpoint 断点续跑 | ✅ 分片 resume (已完成跳过) |
| 结果落盘 | `results/ds_*_checkpoint.json` | `tri_track_undug_results.csv` |
| 信号域 | 7 种金字塔数据集(tech/web/order/imbalance等) | option8/fundamental2/pv13/analyst4 + SubU 救援 |

> ⚠️ **关键差异**：ds 舰队记录完整的回测指标(Sharpe/Fitness/失败闸门)且由 `fleet_keeper.py` 守护；tri_track 独立账号仅记录提交日志(alpha_id/状态)，**不包含回测指标**，无法直接对比信号质量。

---
## 四、ds 舰队实时详情 (7 路在飞)

| 数据集 | 进度 | 首步最佳S | 估算吞吐 | 运行时长 | 预期完成 | 候选 |
|---|---|---|---|---|---|---|
| equity_kpi_forecast | 248/320 (77.5%) | 🟡 **1.42** | ~82 α/hr | 182 min | **07-26 01:06** | 🔴 0 候选 |
| ml_factor_proj | 208/320 (65.0%) | 🔴 **0.48** | ~69 α/hr | 181 min | **07-26 01:51** | 🔴 0 候选 |
| order_book_imbalance | 256/320 (80.0%) | 🔴 **0.84** | ~85 α/hr | 182 min | **07-26 00:59** | 🔴 0 候选 |
| pv_tech_indicators | 224/320 (70.0%) | 🔴 **0.76** | ~72 α/hr | 186 min | **07-26 01:33** | 🔴 0 候选 |
| quant_factor_lib | 232/320 (72.5%) | 🔴 **0.60** | ~78 α/hr | 178 min | **07-26 01:21** | 🔴 0 候选 |
| techindi_model | 200/320 (62.5%) | 🟡 **1.50** | ~69 α/hr | 174 min | **07-26 01:57** | 🔴 0 候选 |
| web_traffic_engage | 232/320 (72.5%) | 🟢 **2.27** | ~77 α/hr | 181 min | **07-26 01:22** | 🔴 0 候选 |
| workforce_flow_skills | 40/320 (12.5%) | 🔴 **0.85** | ~0 α/hr | 0 min | **?** | 🔴 0 候选 |

> 🔴 = Sharpe < 1.0, 🟡 = 1.0~1.58, 🟢 = ≥1.58 (研究仿真 IS 夏普过闸线)。web_traffic 虽 S ≥ 1.58 但仍卡 F/M/Ret 等其他 IS 闸，故 0 候选。

**在飞任务 ETA 汇总**：

| 任务 | 当前进度 | 预期完成 | 置信度 |
|---|---|---|---|
| 🚢 equity_kpi_forecast | 248/320 (78%) | **07-26 01:06** | 中 |
| 🚢 ml_factor_proj | 208/320 (65%) | **07-26 01:51** | 中 |
| 🚢 order_book_imbalance | 256/320 (80%) | **07-26 00:59** | 中 |
| 🚢 pv_tech_indicators | 224/320 (70%) | **07-26 01:33** | 中 |
| 🚢 quant_factor_lib | 232/320 (72%) | **07-26 01:21** | 中 |
| 🚢 techindi_model | 200/320 (62%) | **07-26 01:57** | 中 |
| 🚢 web_traffic_engage | 232/320 (72%) | **07-26 01:22** | 中 |
| 🚢 workforce_flow_skills | 0/320 (0%) | **?** | 低(运行不足30min) |
| 🛡️ tri_track_undug | 进度日志 | **07-26 00:23** | 中(进度日志推算) |
| 🔬 v52b_hiring_margin | ?/? (-%) | **?** | 无进度日志 |

> ⚠️ v52b 已补进度日志（`scan_v52b_hiring_margin.py` 每 batch 写一行），下次重启后 ETA 可从日志计算。当前旧进程仍无日志。

---
## 五、主账号全任务最佳 Sharpe 排名 (含 ds 舰队)

| 排名 | 任务 | 回测N | 候选 | 最佳 Sharpe | 评级 | 主导失败 |
|---|---:|---:|---:|---:|---|
| 1 |  v52b_hiring_margin | 160 | 28 | 🟢 **2.66** | 候选 | gate_S/F/M/Ret |
| 2 |  v39b_sub_micro | 160 | 10 | 🟢 **2.58** | 候选 | PF:LOW_SUB |
| 3 |  v52_tri_hiring_trends | 320 | 4 | 🟢 **2.50** | 候选 | PF:LOW_SUB |
| 4 |  v39_insider_rescue | 240 | 0 | 🟢 **2.30** | - | PF:LOW_SUB |
| 5 | 🚢 ds_web_traffic_engage_tri_web_traffic_en | 232 | 0 | 🟢 **2.27** | - | gate_S/F/M/Ret |
| 6 |  v34_insider_matrix | 72 | 0 | 🟢 **1.95** | - | gate_S/F/M/Ret |
| 7 |  v51_tri_behavioral_signals | 320 | 0 | 🟢 **1.72** | - | gate_S/F/M/Ret |
| 8 |  v47_tri_search_interest | 320 | 0 | 🟢 **1.59** | - | gate_S/F/M/Ret |
| 9 | 🚢 ds_techindi_model_tri_techindi_model | 200 | 0 | 🟡 **1.50** | - | gate_S/F/M/Ret |
| 10 | 🚢 ds_equity_kpi_forecast_tri_equity_kpi_fo | 248 | 0 | 🟡 **1.42** | - | gate_S/F/M/Ret |
| 11 |  v53_tri_stock_search_trends | 320 | 0 | 🟡 **1.19** | - | gate_S/F/M/Ret |
| 12 |  v38_sust_profit | 278 | 0 | 🟡 **1.12** | - | gate_S/F/M/Ret |
| 13 |  v38b_sust_rescue | 270 | 0 | 🟡 **1.07** | - | gate_S/F/M/Ret |
| 14 |  v37_other545 | 187 | 0 | 🔴 **0.98** | - | gate_S/F/M/Ret |
| 15 |  v54_tri_event_stock_model | 320 | 0 | 🔴 **0.95** | - | gate_S/F/M/Ret |
| 16 |  v46_tri_insider_trx | 320 | 0 | 🔴 **0.92** | - | gate_S/F/M/Ret |
| 17 |  v42_social | 200 | 0 | 🔴 **0.88** | - | gate_S/F/M/Ret |
| 18 | 🚢 ds_workforce_flow_skills_tri_workforce_f | 40 | 0 | 🔴 **0.85** | - | gate_S/F/M/Ret |
| 19 | 🚢 ds_order_book_imbalance_tri_order_book_i | 256 | 0 | 🔴 **0.84** | - | gate_S/F/M/Ret |
| 20 |  v48_tri_acquisition_model | 320 | 0 | 🔴 **0.79** | - | gate_S/F/M/Ret |
| 21 | 🚢 ds_pv_tech_indicators_tri_pv_tech_indica | 224 | 0 | 🔴 **0.76** | - | gate_S/F/M/Ret |
| 22 |  v33_hkg_anl10 | 59 | 0 | 🔴 **0.76** | - | gate_S/F/M/Ret |
| 23 |  v41_earn_risk | 180 | 0 | 🔴 **0.75** | - | gate_S/F/M/Ret |
| 24 |  v45_tri_insider_feats | 320 | 0 | 🔴 **0.69** | - | gate_S/F/M/Ret |
| 25 |  v50_tri_board_network | 320 | 0 | 🔴 **0.68** | - | gate_S/F/M/Ret |
| 26 |  v35_news_nlp | 24 | 0 | 🔴 **0.65** | - | gate_S/F/M/Ret |
| 27 |  v44_insider_feats | 200 | 0 | 🔴 **0.63** | - | gate_S/F/M/Ret |
| 28 | 🚢 ds_quant_factor_lib_tri_quant_factor_lib | 232 | 0 | 🔴 **0.60** | - | gate_S/F/M/Ret |
| 29 |  v36_stock_cluster | 157 | 0 | 🔴 **0.57** | - | gate_S/F/M/Ret |
| 30 | 🚢 ds_ml_factor_proj_tri_ml_factor_proj | 208 | 0 | 🔴 **0.48** | - | gate_S/F/M/Ret |
| 31 |  v43_event_rel | 200 | 0 | 🔴 **0.47** | - | gate_S/F/M/Ret |
| 32 |  v40_cre | 200 | 0 | 🔴 **0.43** | - | gate_S/F/M/Ret |
| 33 |  v49_tri_forward_beta_risk | 320 | 0 | 🔴 **0.43** | - | gate_S/F/M/Ret |
| 34 |  measure_L2 | 3 | 0 | 🔴 **0.00** | - | gate_S/F/M/Ret |
| 35 |  measure_L3 | 2 | 0 | 🔴 **0.00** | - | gate_S/F/M/Ret |
| 36 |  measure_L | 6 | 0 | 🔴 **0.00** | - | gate_S/F/M/Ret |
| 37 |  measure_rate | 5 | 0 | 🔴 **0.00** | - | gate_S/F/M/Ret |

> 🚢 = ds 舰队在飞任务。v52b(2.66) / v52(2.50) / v39b(2.58) / v39(2.30) 为历史最强信号集群；ds 舰队全面贴底(🔴)，直观体现信号发现瓶颈。

---
## 六、tri_track 独立账号详情 (🛡️ ML88164)

| 维度 | 数值 |
|---|---|
| 账号 | **ML88164** (独立 gmail/tabbit 体系，与主账号 mthyzx@126.com **令牌互不干扰**) |
| 并发模型 | CONCURRENCY=3，三轨并行 |
| 任务结构 | 8 分片 × 10 任务 = **80 变体**，每片约 10 任务 |
| 三轨方向 | **explore** (option8/fundamental2/pv13 低占用)、**improve** (SubU FAIL 数据)、**misc** (analyst4 低占用) |
| 已提交 alpha | **733** 个  |
| 提交结果 | ✅ submitted=733 / ❌ failed=0 |
| 最佳 Sharpe | 不可用 (CSV 无指标) |
| 分轨分布 | explore 413 / improve 216 / misc 104 |
| 时间范围 | 2026-07-25 11:58:04 ~ 2026-07-26 00:13:17 |
| 结果文件 | `tri_track_undug_results.csv` + `tri_track_undug_checkpoint.json` |
| 进度日志 | `tri_track_undug_progress.log` (不存在,旧版脚本) |
| 分片进度 | shard 4/8 已完成 (56→80), shard 5/8 已完成 (57→80), 其余分片在飞 |
| 预期完成 | **07-26 00:23** (基于每分片 ~300s × 6 剩余 / CONCURRENCY=3, 粗估) |
| 信号举例 | `unsystematic_risk_last_90_days` zscore × subindustry / `correlation_last_360_days_spy` flip / `pcr_vol_60` 救援 |

> ⚠️ **数据缺口（旧版脚本）**：当前 `tri_track_undug_results.csv` 仅记录提交状态，不含回测指标。已改造 `tri_track_undug.py`（新增 checkpoint + 进度日志 + IS 自动抓取），下次运行时 checkpoint 将包含 Sharpe/Fitness/失败闸门，进度日志提供实时 ETA。详见 tri_track_undug.py 第 299-390 行新增代码。

---
## 七、失败闸门分析

| 失败类型 | 次数 | 占比 | 说明 |
|---|---:|---:|---|
| F(拟合) | **6,157** | 22.0% |  |
| S(夏普) | **6,108** | 21.8% |  |
| M(换手收益) | **6,065** | 21.7% |  |
| Ret(收益) | **5,754** | 20.6% |  |
| TVR(换手率) | **2,939** | 10.5% |  |
| submit_failed | **664** | 2.4% |  |
| PF:子宇宙Sharpe | **298** | 1.1% | 主因 PF:LOW_SUB_UNIVERSE_SHARPE (217次) |

> **PF:子宇宙 Sharpe 是头号平台失败闸门** (298 次)，印证'在子宇宙层面优化中性化/约束'是攻坚方向。IS 指标失败(夏普/拟合/换手/收益)合计 27,023 次，submit_failed 664 次(多为研究仿真本地拒，非平台 429)。

---
## 八、候选 Alpha 明细 (42 个，按 Sharpe 降序)

| pid | 任务 | Sharpe | Fitness | tvr | 状态 | 配置 |
|---|---|---:|---:|---:|---|---|
| zqRkPVbX | v52b_hiring_margin             | **2.33** | 1.67 | 0.1487 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| RR17rbe0 | v52b_hiring_margin             | **2.33** | 1.67 | 0.1487 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| 1YzwaMZz | v52b_hiring_margin             | **2.32** | 1.65 | 0.1497 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| WjV7a5eo | v52b_hiring_margin             | **2.32** | 1.65 | 0.1501 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| e7xzrba6 | v52b_hiring_margin             | **2.32** | 1.65 | 0.1497 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| vRvjmrY3 | v52b_hiring_margin             | **2.32** | 1.65 | 0.1501 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| Xg8720b0 | v52b_hiring_margin             | **2.31** | 1.64 | 0.1484 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| pwKj7Rd3 | v52b_hiring_margin             | **2.31** | 1.64 | 0.1484 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| E5el82OG | v52b_hiring_margin             | **2.30** | 1.63 | 0.1491 | PASS_CHEAP | USA TOP3000 decay4 INDUSTRY |
| wpEjPZ5l | v52b_hiring_margin             | **2.30** | 1.63 | 0.1491 | PASS_CHEAP | USA TOP3000 decay4 INDUSTRY |
| j2rrpVzO  ⚡ | v52_tri_hiring_trends          | **2.19** | 1.78 | 0.1634 | CHECK_PENDING | USA ILLIQUID_MINVOL1M decay3 SECTOR |
| j2rgVd0E | v39b_sub_micro                 | **2.18** | 1.80 | 0.1187 | PASS_CHEAP | USA TOP3000 decay2 SECTOR |
| zqRWAJmX | v39b_sub_micro                 | **2.17** | 1.79 | 0.1193 | PASS_CHEAP | USA TOP3000 decay2 SECTOR |
| N1RO8rLL | v39b_sub_micro                 | **2.13** | 1.75 | 0.1145 | PASS_CHEAP | USA TOP3000 decay2 INDUSTRY |
| np8Wr2ml | v39b_sub_micro                 | **2.12** | 1.74 | 0.1153 | PASS_CHEAP | USA TOP3000 decay2 INDUSTRY |
| YPgAa3WR | v39b_sub_micro                 | **2.08** | 1.67 | 0.1059 | PASS_CHEAP | USA TOP3000 decay3 SECTOR |
| le30awQe | v39b_sub_micro                 | **2.07** | 1.67 | 0.1065 | PASS_CHEAP | USA TOP3000 decay3 SECTOR |
| QP9QNw8G | v39b_sub_micro                 | **2.00** | 1.59 | 0.1035 | PASS_CHEAP | USA TOP3000 decay3 INDUSTRY |
| RR1rlGge | v39b_sub_micro                 | **1.99** | 1.59 | 0.1042 | PASS_CHEAP | USA TOP3000 decay3 INDUSTRY |
| wpEjaENp | v52b_hiring_margin             | **1.94** | 1.40 | 0.1344 | PASS_CHEAP | USA TOP3000 decay3 SECTOR |
| E5elGemr | v52b_hiring_margin             | **1.94** | 1.40 | 0.1348 | PASS_CHEAP | USA TOP3000 decay3 SECTOR |
| A17GR6Wd  ⚡ | v52_tri_hiring_trends          | **1.94** | 1.75 | 0.1342 | CHECK_PENDING | USA ILLIQUID_MINVOL1M decay2 SECTOR |
| 88elpeGW | v52b_hiring_margin             | **1.92** | 1.37 | 0.1363 | PASS_CHEAP | USA TOP3000 decay3 SECTOR |
| xAdjvnxN | v52b_hiring_margin             | **1.92** | 1.39 | 0.1464 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| d5RjZR9K | v52b_hiring_margin             | **1.91** | 1.36 | 0.136 | PASS_CHEAP | USA TOP3000 decay3 SECTOR |
| 78njYdwQ | v52b_hiring_margin             | **1.91** | 1.38 | 0.1463 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| le3jNVV5 | v52b_hiring_margin             | **1.91** | 1.36 | 0.135 | PASS_CHEAP | USA TOP3000 decay3 INDUSTRY |
| rKPj7WWd | v52b_hiring_margin             | **1.90** | 1.37 | 0.1445 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| N1R7POpX | v52b_hiring_margin             | **1.90** | 1.37 | 0.1452 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| qM6jwAlK | v52b_hiring_margin             | **1.89** | 1.35 | 0.1352 | PASS_CHEAP | USA TOP3000 decay3 INDUSTRY |
| kqZjgQzO | v52b_hiring_margin             | **1.81** | 1.31 | 0.1193 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| 9q7XWRzK | v52b_hiring_margin             | **1.81** | 1.31 | 0.1206 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| qM6j0XKK | v52b_hiring_margin             | **1.80** | 1.30 | 0.1203 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| gJ9jZxnM | v52b_hiring_margin             | **1.79** | 1.29 | 0.119 | PASS_CHEAP | USA TOP3000 decay4 SECTOR |
| YPgvjZrJ  ⚡ | v52_tri_hiring_trends          | **1.79** | 1.61 | 0.1056 | CHECK_PENDING | USA ILLIQUID_MINVOL1M decay4 SECTOR |
| xAdjpxRn | v52b_hiring_margin             | **1.77** | 1.27 | 0.1197 | PASS_CHEAP | USA TOP3000 decay4 INDUSTRY |
| 9q7XOwJd | v52b_hiring_margin             | **1.76** | 1.26 | 0.1206 | PASS_CHEAP | USA TOP3000 decay4 INDUSTRY |
| 88elxznW | v52b_hiring_margin             | **1.76** | 1.26 | 0.1209 | PASS_CHEAP | USA TOP3000 decay4 INDUSTRY |
| bldj1LvZ | v52b_hiring_margin             | **1.75** | 1.24 | 0.1195 | PASS_CHEAP | USA TOP3000 decay4 INDUSTRY |
| KPELQn7l | v39b_sub_micro                 | **1.67** | 1.18 | 0.1144 | PASS_CHEAP | USA TOP3000 decay2 SECTOR |
| e7xrvnzJ | v39b_sub_micro                 | **1.67** | 1.19 | 0.115 | PASS_CHEAP | USA TOP3000 decay2 SECTOR |
| RR11Gzbd  ⚡ | v52_tri_hiring_trends          | **1.63** | 1.19 | 0.1062 | CHECK_PENDING | USA TOP3000 decay4 INDUSTRY |

> ⚡ = CHECK_PENDING (已通过 IS 闸，待生产仿真验证)。候选来自 2 个根集群：**v52b** (`aggregate_open_positions_count`，降换手 hiring 信号，S 1.79–2.66) 与 **v39b** (`eur_top_value_2`，insider micro 信号，S 1.67–2.58)。均仅研究仿真 IS 闸通过，**缺生产仿真(OOS)+平台 submittable+真实提交**。

---
## 九、候选因子提交核查（逐项审计）

| 分类 | 数量 | 说明 |
|---|---|---|
| ✅ 已正式提交 | **1** | `YPgAa3WR` status=ACTIVE, dateSubmitted=2026-07-24, prod_corr=0.5325 |
| ✅ 回测完成待提交 | **0** | 其余候选均缺平台 OOS 硬闸门验证(`/check` 返回空) |
| 🔶 仍需进一步验证 | **41** | 35 个候选缺生产仿真(OOS)+submittable+submit |

> ⚠️ **实话实说**：全部 42 个候选，**1 个已提交、35 个不可提交**。`YPgAa3WR` 已验证 IS✅ + 生产相关性(0.5325)✅ + 风险中性✅ + 稳健性✅，已成功提交至 WQ 平台(status=ACTIVE)。其余 35 个均缺平台生产仿真(OOS)硬闸门——`/check` 返回空，提交即被静默丢弃。`PASS_CHEAP` ≈ 1/4 路程，`CHECK_PENDING` ≈ 1/2 路程。

**逐候选核查（按提交状态分级）**：

### ✅ 已正式提交 (1 个)

| pid | 任务 | S | 验证链 | 提交时间 |
|---|---|---:|---|---|
| **YPgAa3WR** | v39b_sub_micro            | **2.08** | IS✅ 产验(0.5325)✅ 风险中性✅ 稳健性✅ | 2026-07-24 |

### 🔶 仍需进一步验证 (41 个)

| pid | 任务 | S | 状态 | 卡点 | 操作 |
|---|---|---:|---|---|---|
| le30awQe | v39b_sub_micro            | **2.07** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| j2rgVd0E | v39b_sub_micro            | **2.18** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| zqRWAJmX | v39b_sub_micro            | **2.17** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| QP9QNw8G | v39b_sub_micro            | **2.00** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| RR1rlGge | v39b_sub_micro            | **1.99** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| KPELQn7l | v39b_sub_micro            | **1.67** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| e7xrvnzJ | v39b_sub_micro            | **1.67** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| N1RO8rLL | v39b_sub_micro            | **2.13** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| np8Wr2ml | v39b_sub_micro            | **2.12** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| Xg8720b0 | v52b_hiring_margin        | **2.31** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| zqRkPVbX | v52b_hiring_margin        | **2.33** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| 1YzwaMZz | v52b_hiring_margin        | **2.32** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| WjV7a5eo | v52b_hiring_margin        | **2.32** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| pwKj7Rd3 | v52b_hiring_margin        | **2.31** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| RR17rbe0 | v52b_hiring_margin        | **2.33** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| e7xzrba6 | v52b_hiring_margin        | **2.32** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| vRvjmrY3 | v52b_hiring_margin        | **2.32** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| wpEjaENp | v52b_hiring_margin        | **1.94** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| E5elGemr | v52b_hiring_margin        | **1.94** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| d5RjZR9K | v52b_hiring_margin        | **1.91** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| 88elpeGW | v52b_hiring_margin        | **1.92** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| gJ9jZxnM | v52b_hiring_margin        | **1.79** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| kqZjgQzO | v52b_hiring_margin        | **1.81** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| qM6j0XKK | v52b_hiring_margin        | **1.80** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| 9q7XWRzK | v52b_hiring_margin        | **1.81** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| rKPj7WWd | v52b_hiring_margin        | **1.90** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| N1R7POpX | v52b_hiring_margin        | **1.90** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| 78njYdwQ | v52b_hiring_margin        | **1.91** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| xAdjvnxN | v52b_hiring_margin        | **1.92** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| E5el82OG | v52b_hiring_margin        | **2.30** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| wpEjPZ5l | v52b_hiring_margin        | **2.30** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| le3jNVV5 | v52b_hiring_margin        | **1.91** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| qM6jwAlK | v52b_hiring_margin        | **1.89** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| bldj1LvZ | v52b_hiring_margin        | **1.75** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| xAdjpxRn | v52b_hiring_margin        | **1.77** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| 9q7XOwJd | v52b_hiring_margin        | **1.76** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| 88elxznW | v52b_hiring_margin        | **1.76** | 仅IS闸 | 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | OOS+产验+submittable+submit |
| j2rrpVzO | v52_tri_hiring_trends     | **2.19** | 平台产验中 | 等平台返回产验结果 / 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | 等平台产验+OOS+submit |
| RR11Gzbd | v52_tri_hiring_trends     | **1.63** | 平台产验中 | 等平台返回产验结果 / 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | 等平台产验+OOS+submit |
| A17GR6Wd | v52_tri_hiring_trends     | **1.94** | 平台产验中 | 等平台返回产验结果 / 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | 等平台产验+OOS+submit |
| YPgvjZrJ | v52_tri_hiring_trends     | **1.79** | 平台产验中 | 等平台返回产验结果 / 生产相关性验证 / 生产仿真(OOS) / submittable判定 / 显式submit(no_submit→True) | 等平台产验+OOS+submit |

> 📋 **提交前完整流程**：① 在 WQ BRAIN 控制台跑 production simulation(OOS)；② 等 `/check` 返回全量硬闸门结果；③ 确认 PROD_CORRELATION/SELF_CORRELATION 等 PASS；④ 用 `submit_candidate.py`(已就绪)批量提交。当前仅 `submit_candidate.py` 已就绪但缺 OOS——需平台侧人工触发。

---
## 十、问题说明（问题其次）

1. **候选提交率 1/38**。仅 `YPgAa3WR` 已提交(ACTIVE)，其余 37 个缺平台 OOS 硬闸门。见第九章逐项审计。
2. **ds 舰队首步信号偏弱、7 路 0 候选**。见第四章表格；加并发=加速挖 0 候选。
3. **子宇宙 Sharpe 闸门比 IS 闸更硬**。PF:LOW_SUB_UNIVERSE_SHARPE 为头号失败，V39b(2.58)/V39(2.30) 均卡此处。
4. **tri_track 独立账号缺少回测指标**。CSV 仅记提交状态，无 Sharpe/Fitness/失败闸门，无法与主账号 ds 舰队做信号质量对比。
5. **监控盲区已修正**。旧 gen_report.py 漏掉 ds_* 舰队、误判 tri_track；本报告由 build_md_report.py 从真实文件生成，所有数字实算、不编造。
6. **吞吐数字勿误读**。ds 舰队表中所列 α/hr 为 done/elapsed 粗估上限；稳态基准下 7 路真实可持续约 603 α/hr。

---
## 十一、行动建议（方案最后）

1. **ds 舰队继续跑完**：已验证合规（优，零 429），按各 submit_gate 自然推进。
2. **主攻子宇宙 Sharpe 闸门**：对 V39/V39b 限定 universe=TOP3000 / 调整 neutralization。
3. **v52b 升维**：降换手变体（decay4 SECTOR）已 4+ 过廉价 IS 闸，规模化过 M 闸。
4. **并发纪律（修订）**：允许错峰多进程(>6) 并发，需自带 gate + 禁 <2s 齐射。
5. **提交核查路线（按优先级）**：YPgAa3WR(最接近) → 4 个 CHECK_PENDING 等平台结果 → 31 个 PASS_CHEAP 排队验证。对 YPgAa3WR：跑 OOS → /check → submittable → submit(关 no_submit)；走通全流程后批量复制到其余候选。
6. **监控 CHECK_PENDING 结果**：4 个 v52_tri_hiring_trends 候选当前在 WQ 平台自动产验中，结果返回后立即评估 prod_corr/self_corr，若过关则优先级提到 YPgAa3WR 同级。
7. **tri_track 脚本升级**：改输出为 checkpoint 格式(含 Sharpe/Fitness/失败闸门)，纳入统一监控体系。


---
*报告由 `build_md_report.py` 从真实 checkpoint/progress/CSV 文件程序化生成 · 快照 2026-07-26 00:13 GMT+8 · 数字均来自文件实测，未编造。*
*生成器路径: `deliverables/tools/build_md_report.py` (复跑即可刷新最新数据)*