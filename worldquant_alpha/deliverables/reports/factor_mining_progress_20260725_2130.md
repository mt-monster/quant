# WorldQuant Brain PPA 因子挖掘进度汇报 (LIVE)

- **数据快照时间**: 2026-07-25 21:30:20 GMT+8
- **机器级 Python 进程 (接触 WQ BRAIN)**: 25 个 = 挖掘 10 个进程(**9 个挖掘任务**: scan 1 进程 + 三轨挖掘 9 进程, 其中 `tri_track_undug` 含 1 父 1 子故记 2 进程) + MCP宿主 14 + 舰队守护 1 + watchdog 0 + tracker 0；编辑器/语言服务 8 (idle)。命令行命中 `RR11jN`: 0。
- **发现任务数**: 33 个扫描任务 (在飞 9 / 已完成 24); checkpoint 覆盖 32 个。
- **累计回测次数 (全部 checkpoint 合计)**: 5859 | **研究仿真 IS 闸通过候选**: 26 | **found_alphas (跨生产相关性验证)**: 1 | **全链路最佳 Sharpe**: 2.65
- **在飞聚合并发吞吐**: ≈ 4666 α/hr（**早期乐观值**, 仅含带进度日志的在飞任务; 稳态基准 multi(8)≈86 α/hr/任务, 7 路在飞实际可持续 ≈ **603 α/hr**, 见 `bench_v34_sim_speed_20260723_171444.json`）。
- **平台并发模型**: Token-Bucket 令牌桶, 突发容量 C=7 (定稿见 `probe_concurrency_final_report_20260725_0255.md`)。

<div style="background:#ffe0e0;border:2px solid #d00;color:#900;padding:10px 14px;border-radius:6px;font-weight:bold;line-height:1.6;">⚠️ <b>提交验证最重要结论</b>：本报告全部 26 个候选 Alpha 均仅通过「研究仿真 IS 廉价闸门」、**未经完整提交验证**；其中仅 1 个跨过生产相关性 PROD_CORRELATION（全局唯一 `YPgAa3WR` v39b, prod_corr=0.5325），**0 个**完成平台真实提交 —— <b>0 个满足完整 WQ 提交标准，请勿视作可提交 Alpha</b>。</div>

---

## 0. 执行摘要

1. **在飞回测进程**：9 个挖掘任务在飞(10 个进程) —— `v52b_hiring_margin`(主账号) + 7 路 `scan_tri_job --dataset`(舰队, 由 `fleet_keeper.py` 错峰守护, 目标 8 路) + `tri_track_undug.py`(**独立账号分片挖掘, 见盲区⑤陷阱②, 已改判单列不漏**)。
2. **当前舰队架构已切换**：21:06–21:09 由 `fleet_keeper.py` 拉起 **新 `ds_*` 数据集舰队**(pv_tech_indicators / web_traffic_engage / order_book_imbalance / ml_factor_proj / quant_factor_lib / techindi_model / equity_kpi_forecast)，checkpoint 命名 `ds_<ds>_tri_<ds>_checkpoint.json`；旧 `v47–v54` 舰队(已结束, checkpoint 仍留 `results/`)不再在飞。旧版监控报告(21:13)描述的是旧舰队, 本次为最新状态。
3. **零 429 实证**：在飞 10 个进程；全链路 `submit_failed=0 / 429=0 / poll_timeout=0`(进度日志核验)；各进程自带 submit_gate + multi-sim + 退避, 令牌零浪费。
4. **效率评估(源码+运行时双核验)**：在飞 `scan_tri_job`/`scan_v52b` 均落地 **显式 submit_gate + 批量 multi-sim(BATCH_SIZE=8) + 退避 + no_submit + checkpoint**(评级 优)；`tri_track_undug` 为独立账号、CONCURRENCY=3 三轨挖掘, 同样限速合规。
5. **全局最主要失败闸门 = LOW_SUB_UNIVERSE_SHARPE / 廉价 IS 闸门(S/F/M/Ret)**：最强信号仍卡子宇宙 Sharpe(历史 V39b S=2.58 / V39 S=2.30 / V34 S=1.95 平台侧失败)。
6. **瓶颈 = 信号发现, 非吞吐**：在飞舰队首步 Sharpe 普遍偏低(见 §2/§7), 加并发只是加速'挖 0 候选'。真正杠杆是范式转向(低自相关+行业中性+W189/d3/SECTOR/t1 风格扩展)。
7. **候选 Alpha 评测(提交未验证)**：共 **26** 个 `status=PASS/PASS_CHEAP`(研究仿真 IS 闸通过), 仅 **1** 个跨生产相关性验证；均缺生产仿真(OOS)+平台 submittable+真实提交。详见 §10。

---

## 1. 进程盘点 (Python 进程第一视角, 机器级全量枚举)

> **第一视角 = 机器上全部 python.exe 进程** (Get-CimInstance Win32_Process), 按命令行分类; v 系列 `*_progress_*.log` 只是 scan 脚本本地产物, **不是发现入口**。任何经 MCP 发起的服务端任务(如 `set_RR11jN_`)只能靠此枚举暴露其宿主。

- 机器级 python 进程总数: **34** | 接触 WQ BRAIN: **25** = 挖掘 10(scan 1+三轨 9) + MCP宿主 14 + 舰队守护 1 + watchdog 0 + tracker 0 | 编辑器/语言服务 8 (idle)
- 命令行命中 `RR11jN`: **0** 个

| PID | 类型 | 启动 | 线程 | 任务/说明 |
|---|---|---|---|---|
| 59688 | keeper | 07-25 21:06 | 1 |  舰队守护: 维持 8 路挖掘进程, 错峰补位, 共享 submit_gate |
| 13420 | mcp_server | 07-23 17:40 | 24 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 14548 | mcp_server | 07-23 17:40 | 24 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 23088 | mcp_server | 07-23 17:15 | 24 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 23516 | mcp_server | 07-24 22:54 | 1 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 28060 | mcp_server | 07-23 11:05 | 1 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 31764 | mcp_server | 07-24 22:54 | 24 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 35484 | mcp_server | 07-23 18:11 | 24 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 38288 | mcp_server | 07-23 18:12 | 1 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 38560 | mcp_server | 07-23 18:11 | 1 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 44476 | mcp_server | 07-23 17:40 | 1 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 52532 | mcp_server | 07-23 17:15 | 1 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 53128 | mcp_server | 07-23 18:12 | 24 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 54120 | mcp_server | 07-23 17:40 | 1 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 56616 | mcp_server | 07-23 11:05 | 24 |  WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志) |
| 49712 | other | 07-25 21:30 | 6 |  其他 |
| 26748 | scan_script | 07-25 19:17 | 2 | v52b_hiring_margin 扫描脚本(本地进度日志见 §2) |
| 28836 | tri_miner | 07-25 20:02 | 1 | tri_track_undug 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 36640 | tri_miner | 07-25 21:06 | 2 | ds_pv_tech_indicators_tri_pv_tech_indicators 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 38752 | tri_miner | 07-25 21:08 | 2 | ds_techindi_model_tri_techindi_model 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 40180 | tri_miner | 07-25 21:07 | 2 | ds_web_traffic_engage_tri_web_traffic_engage 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 44912 | tri_miner | 07-25 21:08 | 2 | ds_ml_factor_proj_tri_ml_factor_proj 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 47016 | tri_miner | 07-25 21:09 | 2 | ds_equity_kpi_forecast_tri_equity_kpi_forecast 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 57200 | tri_miner | 07-25 21:07 | 1 | ds_order_book_imbalance_tri_order_book_imbalance 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 58844 | tri_miner | 07-25 21:08 | 2 | ds_quant_factor_lib_tri_quant_factor_lib 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |
| 59684 | tri_miner | 07-25 20:02 | 1 | tri_track_undug 三轨挖掘(本地进度日志 / 或无本地日志的独立账号) |

> **第一视角核验结论**：枚举到 25 个接触 WQ BRAIN 的进程——10 个挖掘(含 **`tri_track_undug.py` 已由 other 改判为 tri_miner/三轨挖掘**, 框架盲区⑤陷阱②, 不再漏报) + 14 个 MCP 宿主 + 舰队守护 1。此前监控以 v 系列日志为发现入口, 会漏掉非 v 命名进程与 MCP 宿主; 现以机器级进程为第一视角。命令行均无 `RR11jN`(命中 0), 印证其为服务端句柄而非本机进程名。

---

## 2. 全链路回测概览 (进程产物 checkpoint + 在飞实时统计)

| 任务 | 状态 | N | PASS/CHEAP | found | 最佳S | 最佳F | 主导失败 | 区域 |
|---|---|---:|---:|---:|---:|---:|---|---|
| ds·equity_kpi_forecast_tri_equity_kpi_forecast | 🟢在飞 | 24 | 0 | 0 | 0.40 | 0.15 | gate_S/F/M/Ret | USA |
| ds·ml_factor_proj_tri_ml_factor_proj | 🟢在飞 | 24 | 0 | 0 | 0.36 | 0.13 | gate_S/F/M/Ret | USA |
| ds·order_book_imbalance_tri_order_book_imbalance | 🟢在飞 | 24 | 0 | 0 | 0.45 | 0.09 | gate_S/F/M/Ret | USA |
| ds·pv_tech_indicators_tri_pv_tech_indicators | 🟢在飞 | 32 | 0 | 0 | 0.63 | 0.18 | gate_S/F/M/Ret | USA |
| ds·quant_factor_lib_tri_quant_factor_lib | 🟢在飞 | 24 | 0 | 0 | 0.21 | 0.04 | gate_S/F/M/Ret | USA |
| ds·techindi_model_tri_techindi_model | 🟢在飞 | 24 | 0 | 0 | 1.39 | 0.57 | gate_S/F/M/Ret | USA |
| ds·web_traffic_engage_tri_web_traffic_engage | 🟢在飞 | 24 | 0 | 0 | 1.88 | 0.73 | gate_S/F/M/Ret | USA |
| v33_hkg_anl10 | ⚪已完成 | 59 | 0 | 0 | 0.76 | 0.34 | gate_S/F/M/Ret | - |
| v34_insider_matrix | ⚪已完成 | 72 | 0 | 0 | 1.95 | 1.36 | platform_FAIL | - |
| v35_news_nlp | ⚪已完成 | 24 | 0 | 0 | 0.65 | 0.25 | gate_S/F/M/Ret | - |
| v36_stock_cluster | ⚪已完成 | 157 | 0 | 0 | 0.57 | 0.22 | gate_S/F/M/Ret | - |
| v37_other545 | ⚪已完成 | 187 | 0 | 0 | 0.98 | 0.53 | gate_S/F/M/Ret | - |
| v38b_sust_rescue | ⚪已完成 | 270 | 0 | 0 | 1.07 | 0.56 | gate_S/F/M/Ret | - |
| v38_sust_profit | ⚪已完成 | 278 | 0 | 0 | 1.12 | 0.73 | gate_S/F/M/Ret | - |
| v39b_sub_micro | ⚪已完成 | 160 | 10 | 1 | 2.58 | 2.06 | PF:LOW_SUB_UNIVERSE_SHARPE | USA |
| v39_insider_rescue | ⚪已完成 | 240 | 0 | 0 | 2.30 | 1.77 | PF:LOW_SUB_UNIVERSE_SHARPE | USA |
| v40_cre | ⚪已完成 | 200 | 0 | 0 | 0.43 | 0.10 | gate_S/F/M/Ret | USA |
| v41_earn_risk | ⚪已完成 | 180 | 0 | 0 | 0.75 | 0.27 | gate_S/F/M/Ret | USA |
| v42_social | ⚪已完成 | 200 | 0 | 0 | 0.88 | 0.39 | gate_S/F/M/Ret | USA |
| v43_event_rel | ⚪已完成 | 200 | 0 | 0 | 0.47 | 0.17 | gate_S/F/M/Ret | USA |
| v44_insider_feats | ⚪已完成 | 200 | 0 | 0 | 0.63 | 0.22 | gate_S/F/M/Ret | USA |
| v45_tri_insider_feats | ⚪已完成 | 320 | 0 | 0 | 0.69 | 0.29 | gate_S/F/M/Ret | USA |
| v46_tri_insider_trx | ⚪已完成 | 320 | 0 | 0 | 0.92 | 0.56 | gate_S/F/M/Ret | USA |
| v47_tri_search_interest | ⚪已完成 | 320 | 0 | 0 | 1.59 | 0.73 | gate_S/F/M/Ret | USA |
| v48_tri_acquisition_model | ⚪已完成 | 320 | 0 | 0 | 0.79 | 0.44 | gate_S/F/M/Ret | USA |
| v49_tri_forward_beta_risk | ⚪已完成 | 320 | 0 | 0 | 0.43 | 0.17 | gate_S/F/M/Ret | USA |
| v50_tri_board_network | ⚪已完成 | 320 | 0 | 0 | 0.68 | 0.25 | gate_S/F/M/Ret | USA |
| v51_tri_behavioral_signals | ⚪已完成 | 320 | 0 | 0 | 1.72 | 0.75 | gate_S/F/M/Ret | USA |
| v52b_hiring_margin | 🟢在飞 | 56 | 16 | 0 | 2.65 | 1.77 | gate_S/F/M/Ret | USA |
| v52_tri_hiring_trends | ⚪已完成 | 320 | 0 | 0 | 2.50 | 1.86 | gate_S/F/M/Ret | USA |
| v53_tri_stock_search_trends | ⚪已完成 | 320 | 0 | 0 | 1.19 | 0.57 | gate_S/F/M/Ret | USA |
| v54_tri_event_stock_model | ⚪已完成 | 320 | 0 | 0 | 0.95 | 0.30 | gate_S/F/M/Ret | USA |
| tri_track(独立账号) | 🟢在飞 | - | - | - | - | - | 进行中(无 checkpoint) | - |

**合计**：5859 次回测, 26 次 IS 闸通过, 1 个 found_alphas。

---

## 3. 重点任务详情

### 3.1 v52b_hiring_margin (在飞, 主账号)
- N=56, PASS/CHEAP=16, found=0, 最佳S=2.65, 主导失败=gate_S/F/M/Ret。
- 降换手(decay4 SECTOR)变体已 4 个过廉价 IS 闸(Sharpe 2.31–2.33, PASS_CHEAP), 证实降换手直击 M 闸门; 但生产相关性关未验, 不满足提交。

### 3.2 新 ds_* 数据集舰队 (在飞, 由 fleet_keeper.py 守护, 目标 8 路)

| 任务(dataset) | PID | 进度 | 首步最佳S | 实测节奏 | α/hr | 429 |
|---|---|---|---|---|---|---|
| ds·equity_kpi_forecast_tri_equity_kpi_forecast | 47016 | 24/320 | 0.40 | 41.3s/步 | 698 | 0 |
| ds·ml_factor_proj_tri_ml_factor_proj | 44912 | 24/320 | 0.36 | 44.6s/步 | 646 | 0 |
| ds·order_book_imbalance_tri_order_book_imbalance | 57200 | 24/320 | 0.45 | 40.1s/步 | 719 | 0 |
| ds·pv_tech_indicators_tri_pv_tech_indicators | 36640 | 32/320 | 0.63 | 38.9s/步 | 740 | 0 |
| ds·quant_factor_lib_tri_quant_factor_lib | 58844 | 24/320 | 0.21 | 43.2s/步 | 667 | 0 |
| ds·techindi_model_tri_techindi_model | 38752 | 24/320 | 1.39 | 42.3s/步 | 681 | 0 |
| ds·web_traffic_engage_tri_web_traffic_engage | 40180 | 24/320 | 1.88 | 55.9s/步 | 515 | 0 |

- 7 路均 `scan_tri_job.py` 派生, 自带 submit_gate + multi-sim(BATCH_SIZE=8) + 退避 + no_submit, 效率 优。
- 启动错峰 21:06–21:09, 与 v52b 共同构成多进程并发, 实测零 429。

### 3.3 tri_track_undug.py (在飞, 独立账号三轨挖掘)

- PID 59684, 28836；位于 `D:\BaiduNetdiskDownload\WQ第二三四节课代码\worldquant\`, **独立 gmail 账号(tabbit/world6 体系)**, 分片挖掘(CONCURRENCY=3, 8 分片, 每片 ~10 变体), 信号域为 `unsystematic_risk_last_*` / `correlation_*_spy`, 结果落 `world6_results.csv`。
- ⚠️ **框架盲区⑤陷阱②**: 其命令行含 `tri_track` 会被初版正则误判为 TRACKER, 实为真实挖掘任务; 本报告已**改判为 tri_miner 单列**, 不漏报。
- 其 checkpoint 不在 E3 `results/`(独立目录); 最新分片状态(读 miner_s4_round.log / shard5_run.log): miner_s4_round.log: 分片('4', '8') 总任务80 已完成跳过56 最近信号 _; shard5_run.log: 分片('5', '8') 总任务80 已完成跳过57 最近信号 _

---

## 4. 方案效率评估 (源码合规 + 运行时核验)

> 最佳实践基准 (5 条): ① 批量 multi-sim ② 令牌桶 submit_gate ③ 429 退避 ④ 禁齐射 ⑤ 断点续跑 checkpoint。本维度 = 源码标志位扫描 **且** 运行时核验(进程存活/节奏/429)。

| 任务 | 进程 | 批量 | gate | 退避 | 续跑 | 评级 | 运行时落地 |
|---|---|---|---|---|---|---|---|
| ds·equity_kpi_forecast_tri_equity_kpi_forecast | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) 继承 scan_tri_job 模板 |
| ds·ml_factor_proj_tri_ml_factor_proj | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) 继承 scan_tri_job 模板 |
| ds·order_book_imbalance_tri_order_book_imbalance | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) 继承 scan_tri_job 模板 |
| ds·pv_tech_indicators_tri_pv_tech_indicators | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) 继承 scan_tri_job 模板 |
| ds·quant_factor_lib_tri_quant_factor_lib | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) 继承 scan_tri_job 模板 |
| ds·techindi_model_tri_techindi_model | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) 继承 scan_tri_job 模板 |
| ds·web_traffic_engage_tri_web_traffic_engage | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) 继承 scan_tri_job 模板 |
| v52b_hiring_margin | 在飞 | Y | Y | Y | Y | **优** | 已验证(进程存活, 0 429) |
| tri_track(独立账号) | 在飞 | N | N | Y | Y | **中** | 已验证(进程存活, 0 429) 独立账号·CONCURRENCY=3(据框架) |

- **批量提交 (标准1)**: scan_tri_job / scan_v52b 均经 multi_sim(BATCH_SIZE=8), 1 令牌换 8 回测, 令牌最省。
- **显式令牌桶闸门 (标准2)**: 经 `submit_gate.py` 跨进程令牌桶(文件锁, min_interval≈18s, 批间45s, 429退避), 运行时零 429 实证。
- **退避(标准3)/续跑(标准5)**: wd_lib_wrapper 退避 + checkpoint 健全, 鲁棒达标。
- **禁齐射(标准4)**: 多进程错峰启动(非 <2s 齐射), 实测零 429, 印证保守上限可上调, 真正约束是瞬时提交浓度 ≤ C=7。
- **tri_track_undug**: 独立账号 CONCURRENCY=3, 与本机主账号令牌桶互不干扰, 限速合规。

---

## 5. 并发模型与平台限制 (Token-Bucket C=7)

经对照实验确立为**令牌桶限流**: 突发容量 C=7, 慢补充 ~1 令牌/20–40s。

- **安全包络**: 瞬时并发 ≤6(可错峰放宽); 持续提交间隔 ≥15–20s; 同账号同时启动进程 ≤6(禁 <2s 齐射)。
- **本次实证**: v52b + 7 路 ds 舰队 + tri_track(独立账号) 多进程并发, 全局零 429 —— 关键在'错峰 + 每进程自带 submit_gate', 瞬时提交浓度被压在 C=7 内。
- **已验证危险**: ≥8 提交在 <2s 内并发 -> 必 429。

---

## 6. 吞吐量评估 (Throughput)

> 口径: 1 step = 1 次 multi-sim 批量(BATCH_SIZE=8), α/hr = 3600 / avg_sec_per_step × 8。

| 任务 | α/step | sec/step | α/hr |
|---|---:|---:|---:|
| ds·equity_kpi_forecast_tri_equity_kpi_forecast | 8 | 41.3 | 698 |
| ds·ml_factor_proj_tri_ml_factor_proj | 8 | 44.6 | 646 |
| ds·order_book_imbalance_tri_order_book_imbalance | 8 | 40.1 | 719 |
| ds·pv_tech_indicators_tri_pv_tech_indicators | 8 | 38.9 | 740 |
| ds·quant_factor_lib_tri_quant_factor_lib | 8 | 43.2 | 667 |
| ds·techindi_model_tri_techindi_model | 8 | 42.3 | 681 |
| ds·web_traffic_engage_tri_web_traffic_engage | 8 | 55.9 | 515 |
| **聚合 (在飞 7 进程)** | - | - | **4666** |

- **聚合并发吞吐 ≈ 4666 α/hr**。多进程接近线性叠加, 各进程 gate 节奏(45–70s/step)略有差异未完全同步。
- **方案层效率 = 优(令牌零浪费)**: multi-sim 使每次 POST 仅耗 1 令牌换 8 次回测; submit_gate 消除 429 重提; 实测零 429 无令牌浪费。相比单发(1 POST=1 回测) 令牌效率提升 8×。
- **效率天花板在 gate 而非平台**: 单进程吞吐由各自 submit_gate 节奏绑定, 未触达平台 compute 饱和, 理论上可再加进程(须错峰+每进程 gate, 受 C=7 约束)。
- **核心瓶颈 = 信号发现**: 在飞舰队首步 Sharpe 普遍偏低, 在出候选前加并发只是加速'挖 0 候选'。吞吐已不是限制, 范式转向才是。
- **早期乐观 vs 稳态**: 上表'在飞实测'由进度日志 `avg_sec_per_step` 推算, 因任务刚启动(仅数个 batch、暖队列)而偏小; 历史稳态基准 multi(8)=86.1 α/hr(见 `bench_v34_sim_speed_20260723_171444.json`)下, 7 路在飞真实可持续吞吐 ≈ **603 α/hr**。当前数字应视为上限, 实际趋近稳态值。

---

## 7. 效率结论与 ETA

- **最强信号方向(历史)**: V39b(PASS_CHEAP S=2.58) > V39(S=2.30) > V34(S=1.95, 平台侧失败); 均卡子宇宙 Sharpe 闸门。
- **当前 ds 舰队最佳信号**: web_traffic_engage 首步最佳 S=1.88(已过 S 闸但卡其他 IS 闸, 0 候选)、techindi_model 1.39、pv_tech_indicators 0.63, 其余 <0.5; 全舰队 0 个 PASS/CHEAP 候选 —— 信号发现仍是瓶颈。
- **v52b**: 降换手变体已 4 个过廉价 IS 闸, 是下一轮最值得挖的方向之一(仍差生产验证)。
- **ETA**: 在飞任务由各自 submit_gate 限速自然推进; 无全局阻塞。

---

## 8. 行动建议

1. **舰队继续**: 7 路 ds 舰队 + v52b + tri_track(独立账号) 运行时已验证合规(优, 0 429), 让其按各自 gate 自然跑完。
2. **攻克子宇宙 Sharpe 闸门**: 对 V39/V39b 类高 Sharpe 信号, 限定 universe=TOP3000 / 调整 neutralization / 加子宇宙约束。
3. **v52b 升维**: 继续调优降换手幅度(decay/中性化), 规模化过 M 闸门; 并补生产仿真+PROD_CORRELATION 验证。
4. **并发纪律(修订)**: 允许错峰多进程(>6)并发, 只要各进程自带 submit_gate 且非 <2s 齐射; 加任务前用本报告 §1 运维核验确认在飞进程数与 429。
5. **提交前须补四关**: 对 §10 候选逐个跑生产仿真 → 取全量 /check(PROD_CORRELATION/SELF_CORRELATION) → 平台 submittable 判定 → 显式 submit(关 no_submit)。优先验证已跨生产相关性关的 `YPgAa3WR`。

---

## 9. 全量进程对账 与 盲区修正

- **机器级 python 进程总数**: 34
- **WQ BRAIN MCP 宿主 (platform_functions.py, 不写本地日志)**: 14 个
- **挖掘进程 (scan_script + tri_miner)**: 10 个 (scan 1 + 三轨 9)
- **舰队守护 / watchdog / tracker**: 1 / 0 / 0
- **命令行命中 `RR11jN`**: 0 个

### 9.1 盲区⑤陷阱②: tri_track_undug.py 改判

- `tri_track_undug.py` 命令行含 `tri_track`, 初版正则(只认 `tri_track_miner.py`)会误判为 TRACKER; 实为**独立账号三轨挖掘(CONCURRENCY=3)**, 是真实挖掘任务。本报告已将其**改判为 tri_miner 单列**, 与 MCP 宿主/watcher 区分, **不漏报**。

### 9.2 关于 `set_RR11jN_` 的调查结论

- 全程检索(磁盘文件 / 进度日志 / 脚本源码 / 机器级进程命令行)均未发现 `RR11jN` 字面量; 本表'命中 RR11jN?' 全为否。
- 最可能的解释: `set_RR11jN_` 是 **WQ BRAIN 服务端仿真/多仿真实例 ID**, 经 MCP 助手/Web 控制台发起。{mcp_n} 个 MCP 进程是宿主, 但 `platform_functions.py` 仅输出控制台、**不写本地文件**, 故服务端任务天然不可见——这是本监控器的第二类盲区(服务端无本地日志)。
- 补充可见化: ① WQ BRAIN Web 控制台(账号 mthyzx@126.com) Research → Simulations 按 `RR11jN` 过滤; ② MCP 对话记录; ③ 在用户环境加 `query_wq_simulations()` 桥接(当前环境无 WQ 凭据)。

---

## 10. 候选 Alpha 评测 (研究仿真 IS 闸通过, 提交未验证)

> ⚠️ **口径纠正**: `status=PASS/PASS_CHEAP` **仅表示研究仿真(research sim)的廉价本地闸门通过, 绝不等于 WQ 提交就绪**。WQ 真实提交须过四关: ① 研究仿真 IS 指标(S>1.58/F>1.0/TVR∈[0.05,0.30]/M>10bp/Ret>0.05+近闸) ✅ 26/26 全过; ② 生产仿真(OOS) ❌ 0/26; ③ 生产相关性 PROD_CORRELATION+自相关(仅进 found_alphas 者记过 prod_corr) ✅ 仅 1/26 (`YPgAa3WR`); ④ 平台 submittable+真实提交 ❌ 0/26(脚本 no_submit=True)。

| # | 任务 | pid | label | 状态 | Sharpe | Fitness | sub_univ | tvr | 配置 |
|---|---|---|---|---|---:|---:|---:|---:|---|
| 1 | v52b_hiring_margin | zqRkPVbX | m0_TOP300_d4_SEC_t2 | PASS_CHEAP | 2.33 | 1.67 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 2 | v52b_hiring_margin | RR17rbe0 | m1_TOP300_d4_SEC_t2 | PASS_CHEAP | 2.33 | 1.67 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 3 | v52b_hiring_margin | 1YzwaMZz | m0_TOP300_d4_SEC_t5 | PASS_CHEAP | 2.32 | 1.65 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 4 | v52b_hiring_margin | WjV7a5eo | m0_TOP300_d4_SEC_t8 | PASS_CHEAP | 2.32 | 1.65 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 5 | v52b_hiring_margin | e7xzrba6 | m1_TOP300_d4_SEC_t5 | PASS_CHEAP | 2.32 | 1.65 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 6 | v52b_hiring_margin | vRvjmrY3 | m1_TOP300_d4_SEC_t8 | PASS_CHEAP | 2.32 | 1.65 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 7 | v52b_hiring_margin | Xg8720b0 | m0_TOP300_d4_SEC_t1 | PASS_CHEAP | 2.31 | 1.64 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 8 | v52b_hiring_margin | pwKj7Rd3 | m1_TOP300_d4_SEC_t1 | PASS_CHEAP | 2.31 | 1.64 | - | 0.15 | USA TOP3000 d1 decay4 SECTOR |
| 9 | v39b_sub_micro | j2rgVd0E | gz_t2_b66z189_TOP3000_d2_SEC_t1 | PASS_CHEAP | 2.18 | 1.80 | 1.08 | 0.12 | USA TOP3000 d1 decay2 SECTOR |
| 10 | v39b_sub_micro | zqRWAJmX | gz_t2_b66z189_TOP3000_d2_SEC_t12 | PASS_CHEAP | 2.17 | 1.79 | 1.08 | 0.12 | USA TOP3000 d1 decay2 SECTOR |
| 11 | v39b_sub_micro | N1RO8rLL | gz_t2_b66z189_TOP3000_d2_IND_t1 | PASS_CHEAP | 2.13 | 1.75 | 0.98 | 0.11 | USA TOP3000 d1 decay2 INDUSTRY |
| 12 | v39b_sub_micro | np8Wr2ml | gz_t2_b66z189_TOP3000_d2_IND_t12 | PASS_CHEAP | 2.12 | 1.74 | 0.99 | 0.12 | USA TOP3000 d1 decay2 INDUSTRY |
| 13 | v39b_sub_micro | YPgAa3WR | gz_t2_b66z189_TOP3000_d3_SEC_t1 | PASS_CHEAP | 2.08 | 1.67 | 1.00 | 0.11 | USA TOP3000 d1 decay3 SECTOR |
| 14 | v39b_sub_micro | le30awQe | gz_t2_b66z189_TOP3000_d3_SEC_t12 | PASS_CHEAP | 2.07 | 1.67 | 1.00 | 0.11 | USA TOP3000 d1 decay3 SECTOR |
| 15 | v39b_sub_micro | QP9QNw8G | gz_t2_b66z189_TOP3000_d3_IND_t1 | PASS_CHEAP | 2.00 | 1.59 | 0.89 | 0.10 | USA TOP3000 d1 decay3 INDUSTRY |
| 16 | v39b_sub_micro | RR1rlGge | gz_t2_b66z189_TOP3000_d3_IND_t12 | PASS_CHEAP | 1.99 | 1.59 | 0.90 | 0.10 | USA TOP3000 d1 decay3 INDUSTRY |
| 17 | v52b_hiring_margin | wpEjaENp | m2_TOP300_d3_SEC_t1 | PASS_CHEAP | 1.94 | 1.40 | - | 0.13 | USA TOP3000 d1 decay3 SECTOR |
| 18 | v52b_hiring_margin | E5elGemr | m2_TOP300_d3_SEC_t2 | PASS_CHEAP | 1.94 | 1.40 | - | 0.13 | USA TOP3000 d1 decay3 SECTOR |
| 19 | v52b_hiring_margin | 88elpeGW | m2_TOP300_d3_SEC_t8 | PASS_CHEAP | 1.92 | 1.37 | - | 0.14 | USA TOP3000 d1 decay3 SECTOR |
| 20 | v52b_hiring_margin | d5RjZR9K | m2_TOP300_d3_SEC_t5 | PASS_CHEAP | 1.91 | 1.36 | - | 0.14 | USA TOP3000 d1 decay3 SECTOR |
| 21 | v52b_hiring_margin | kqZjgQzO | m2_TOP300_d4_SEC_t2 | PASS_CHEAP | 1.81 | 1.31 | - | 0.12 | USA TOP3000 d1 decay4 SECTOR |
| 22 | v52b_hiring_margin | 9q7XWRzK | m2_TOP300_d4_SEC_t8 | PASS_CHEAP | 1.81 | 1.31 | - | 0.12 | USA TOP3000 d1 decay4 SECTOR |
| 23 | v52b_hiring_margin | qM6j0XKK | m2_TOP300_d4_SEC_t5 | PASS_CHEAP | 1.80 | 1.30 | - | 0.12 | USA TOP3000 d1 decay4 SECTOR |
| 24 | v52b_hiring_margin | gJ9jZxnM | m2_TOP300_d4_SEC_t1 | PASS_CHEAP | 1.79 | 1.29 | - | 0.12 | USA TOP3000 d1 decay4 SECTOR |
| 25 | v39b_sub_micro | KPELQn7l | gz_t2_b66z252_TOP3000_d2_SEC_t1 | PASS_CHEAP | 1.67 | 1.18 | 0.87 | 0.11 | USA TOP3000 d1 decay2 SECTOR |
| 26 | v39b_sub_micro | e7xrvnzJ | gz_t2_b66z252_TOP3000_d2_SEC_t12 | PASS_CHEAP | 1.67 | 1.19 | 0.87 | 0.12 | USA TOP3000 d1 decay2 SECTOR |

**按任务分组的共享公式 (共 2 个根集群)**:

- **v52b_hiring_margin** (16 个): 代表 `m0_TOP300_d4_SEC_t2` | 配置 `USA TOP3000 d1 decay4 SECTOR` | Sharpe 1.79–2.33
  ```
rank(group_zscore(ts_zscore(ts_backfill(vec_avg(aggregate_open_positions_count), 66), 63), industry))
  ```
- **v39b_sub_micro** (10 个): 代表 `gz_t2_b66z189_TOP3000_d2_SEC_t1` | 配置 `USA TOP3000 d1 decay2 SECTOR` | Sharpe 1.67–2.18
  ```
rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))
  ```

**评测结论与提交建议**:
- **验证层级**: ① 研究仿真 IS ✅26/26; ② 生产仿真 ❌0; ③ 生产相关性 ✅仅 1 (`YPgAa3WR`); ④ 平台提交 ❌0。→ **26 个均不满足 WQ 提交标准**, `PASS_CHEAP` 仅'廉价 IS 闸通过', 非'可提交'。
- **跨 2 个独立根集群**: 是不同信号方向, 提交时彼此不构成复制约束, 但仍需各自与已上线 alpha 查相关。
- **提交路径(须先补验证)**: ① 跑生产仿真; ② 取全量 /check 确认 PROD_CORRELATION/SELF_CORRELATION; ③ 平台判定 submittable; ④ 显式 submit(当前 no_submit=True)。优先验证已跨生产相关性关的 `YPgAa3WR`(prod_corr=0.5325)。
- **账号归属**: v52b/ds 舰队属主账号 `mthyzx@126.com`(checkpoint 落本机); `tri_track_undug` 属独立账号; 与 §9 `set_RR11jN_`(mlh 账号服务端任务)不同来源, 不可混淆。

*报告生成: 2026-07-25 21:30:20 GMT+8 · 数据源 机器级进程枚举(Get-CimInstance) + results/*_checkpoint.json(进程产物) + *_progress_*.log(运行时核验) + scan_*.py(源码) + 独立目录 tri_track_undug · 生成器 gen_report_live.py 可复跑*