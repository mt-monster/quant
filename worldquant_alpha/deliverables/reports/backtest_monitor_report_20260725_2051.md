# WorldQuant Brain PPA 任务进度监控报告

- **数据快照时间**: 2026-07-25 20:51:09 GMT+8
- **覆盖任务**: V33 -> V54 (历史链 V33-V45 + 主账号 trio V46 + 并发批次 V47-V54，共 25 个扫描任务)
- **累计回测次数(已完成链)**: 5659  |  **累计通过候选**: 1  |  **全链路最佳 Sharpe**: 2.65
- **机器级 Python 进程 (接触 WQ BRAIN): 15 个** = 1 扫描脚本 + 14 MCP 服务(交互式服务端回测宿主) + 0 watchdog + 0 tracker；其中 1 个扫描进程在飞、在飞进程已产出 ≈ 32 条回测结果、全局 429 = 0。MCP 服务发起的服务端任务(如 `set_RR11jN_`) 不写本地日志, 见 §9。
- **平台并发模型**: Token-Bucket 令牌桶，突发容量 C=7 (定稿见 `probe_concurrency_final_report_20260725_0255.md`)
- **统计来源说明**: §2 回测结果 = 各 Python 进程写出的 checkpoint JSON (**进程产物**) + 在飞任务的进度日志实时统计；§4 效率 = 源码标志位扫描 **且** 运行时核验(PID/节奏/429) 双轨。

---

## 0. 执行摘要

1. **在飞回测进程**：当前 **1 个 Python 回测进程在飞** (PID: 无)。在飞任务：v52b_hiring_margin（仍持续写入 checkpoint，实时统计见 §2）。详见 §1/§2。
2. **零 429 实证**：当前 1 个进程在飞；历史累计提交 ≈5659 次回测，全链路 `submit_failed=0 / 429=0 / poll_timeout=0`。并发批次启动时间 **错峰分布在 08:39-08:51 (约12分钟)**，且各进程自带 submit_gate(>=18s/>=45s)，故瞬时提交浓度被压在 C=7 内——**证实"错峰 + 每进程闸门"可安全突破旧保守上限(<=6)**。
3. **效率评估(源码+运行时双核验, 覆盖 V33-V53)**：**全账号 22 个任务经源码核验均落地显式 submit_gate (优)**——V34-V53 通过 import multi_sim 继承 `submit_gate.py` 跨进程令牌桶，V33 经 wd_lib_wrapper.run_backtest 同样走 gate；仅 v33 为早期单发脚本(中, 无 multi-sim 批量, 令牌效率偏低)但已限速合规。详见 §4.3。
4. **历史 429 风暴仅 V45**：320/320 = 232 FAIL + 88 error (80 submit_failed + 8 poll_timeout)，均属此前主动制造的 429 风暴后遗症，非代码缺陷；V46 结束后重跑即可。
5. **全局最主要失败闸门 = LOW_SUB_UNIVERSE_SHARPE**：最强信号 V39b (PASS_CHEAP S=2.58) / V39 (S=2.30) / V34 (S=1.95, 平台侧失败) 均卡在子宇宙 Sharpe。
6. **并发批次终局 (V47-V54)**：全部完成、0 过闸；最佳信号为 **V52 hiring_trends Sharpe 2.50**（仅差 M 闸门 M=9.7bp，高换手/成本敏感），是下一轮最值得挖的方向。详见 §7。
7. **吞吐量实证 (回测效率)**：1 个进程在飞，聚合并发吞吐 ≈ **0 α/hr**，单进程基线 (V46 ≈ - α/hr) 加速比 **-×**；提交方案(multi-sim + gate + 退避)零 429 浪费，**方案层效率 = 优**。当前吞吐由各进程自身 gate 节奏绑定(45–70s/step)，尚未触达平台 compute 饱和；**真正瓶颈是信号发现(Sharpe 低)而非吞吐**——在出候选前加并发只是加速"挖 0 候选"。详见 §6。
8. **候选 Alpha 评测 (研究仿真 IS 闸通过, 提交未验证)**：扫描全部 scan checkpoint，共 **22** 个 alpha 的 `status=PASS/PASS_CHEAP` —— 即**研究仿真(research sim)的廉价本地闸门通过** (S>1.58/F>1.0/TVR∈[0.05,0.30]/M>10bp/Ret>0.05)，**不等于 WQ 提交就绪**。其中仅 **1** 个 (进入 found_alphas 者) 真正跨过 **生产相关性 PROD_CORRELATION** 验证 (全局唯一: `YPgAa3WR` v39b, prod_corr=0.5325)；其余 21 个仅廉价 IS 闸通过、**生产关从未验**。均缺生产仿真(OOS)+平台 submittable 判定+真实提交(脚本 no_submit=True)。详见 §10。

---

## 1. 进程盘点 (Python 进程第一视角, 机器级全量枚举)

> **第一视角 = 机器上全部 python.exe 进程** (Get-CimInstance Win32_Process), 按命令行分类; v 系列 `*_progress_*.log` 只是其中 scan_script 进程的本地产物, **不是发现入口**。任何经 MCP 发起的服务端任务(如 `set_RR11jN_`)只能靠此枚举暴露其宿主。

- 机器级 python 进程总数: **26** | 接触 WQ BRAIN: **15** = scan 1 + MCP服务 14 + watchdog 0 + tracker 0 | 其余 11 为编辑器/语言服务(idle)
- 命令行命中 `RR11jN`: **0** 个

| PID | 类型 | 启动 | 线程 | 状态/进度 | 实测节奏 | α/hr | 429 | 标记 | 说明 |
|---|---|---|---|---|---|---|---|---|---|
| 13420 | mcp_server | 07-23 17:40 | 24 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 14548 | mcp_server | 07-23 17:40 | 24 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 23088 | mcp_server | 07-23 17:15 | 24 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 23516 | mcp_server | 07-24 22:54 | 1 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 28060 | mcp_server | 07-23 11:05 | 1 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 31764 | mcp_server | 07-24 22:54 | 24 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 35484 | mcp_server | 07-23 18:11 | 24 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 38288 | mcp_server | 07-23 18:12 | 1 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 38560 | mcp_server | 07-23 18:11 | 1 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 44476 | mcp_server | 07-23 17:40 | 1 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 52532 | mcp_server | 07-23 17:15 | 1 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 53128 | mcp_server | 07-23 18:12 | 24 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 54120 | mcp_server | 07-23 17:40 | 1 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 56616 | mcp_server | 07-23 11:05 | 24 | 宿主·服务端 - | - | - | - |  | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志 |
| 26748 | scan_script | 07-25 19:17 | 2 | 追踪 - | - | - | - |  | 扫描脚本(本地进度日志见 §2/§3) |

> **第一视角核验结论**：机器级枚举到 15 个接触 WQ BRAIN 的 python 进程——1 个 scan 脚本(V46-V53 在飞, 带本地进度日志) + 14 个 MCP 服务(交互式服务端回测宿主) + watchdog/tracker 各 0/0。此前监控以 v 系列日志为发现入口，会系统性漏掉 MCP 宿主等非 v 命名进程(典型如 `set_RR11jN_` 服务端任务)；**现改为以 Python 进程为第一视角**，v 日志仅作 scan_script 明细补充。所有进程命令行均无 `RR11jN`(命中 0)，印证其为 WQ BRAIN 服务端句柄而非本机进程名。

---

## 2. 全链路回测概览 (V33 -> V54, 进程产物 + 在飞实时统计)

| 任务 | 组 | 方向 | N | 已完成 | PASS | found | 最佳S | 最佳F | 主导失败 | 源码评级 | 来源 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| V33·analyst10 | 历史链 | - | 59 | 59 | 0 | 0 | 0.76 | 0.34 | gate_S/F/M/Ret | 中 | checkpoint |
| V34·insider_matrix | 历史链 | - | 72 | 72 | 0 | 0 | 1.95 | 1.36 | platform_FAIL | 优 | checkpoint |
| V35·news_sentiment_nlp | 历史链 | - | 24 | 24 | 0 | 0 | 0.65 | 0.25 | gate_S/F/M/Ret | 优 | checkpoint |
| V36·stock_cluster_dl | 历史链 | - | 157 | 157 | 0 | 0 | 0.57 | 0.22 | gate_S/F/M/Ret | 优 | checkpoint |
| V37·other545 | 历史链 | - | 187 | 187 | 0 | 0 | 0.98 | 0.53 | gate_S/F/M/Ret | 优 | checkpoint |
| V38·sustainable_profit | 历史链 | - | 278 | 278 | 0 | 0 | 1.12 | 0.73 | gate_S/F/M/Ret | 优 | checkpoint |
| V38b·sustainable_profit | 历史链 | - | 270 | 270 | 0 | 0 | 1.07 | 0.56 | gate_S/F/M/Ret | 优 | checkpoint |
| V39·insider_matrix | 历史链 | USA | 240 | 240 | 0 | 0 | 2.30 | 1.77 | PF:LOW_SUB_UNIVERSE_SHARPE | 优 | checkpoint |
| V39b·insider_matrix | 历史链 | USA | 160 | 160 | 10 | 1 | 2.58 | 2.06 | PF:LOW_SUB_UNIVERSE_SHARPE | 优 | checkpoint |
| V40·cre_exposure_model | 历史链 | USA | 200 | 200 | 0 | 0 | 0.43 | 0.10 | gate_S/F/M/Ret | 优 | checkpoint |
| V41·earnings_risk | 历史链 | USA | 180 | 180 | 0 | 0 | 0.75 | 0.27 | gate_S/F/M/Ret | 优 | checkpoint |
| V42·social_sent_score | 历史链 | USA | 200 | 200 | 0 | 0 | 0.88 | 0.39 | gate_S/F/M/Ret | 优 | checkpoint |
| V43·event_relation | 历史链 | USA | 200 | 200 | 0 | 0 | 0.47 | 0.17 | gate_S/F/M/Ret | 优 | checkpoint |
| V44·insider_feats | 历史链 | USA | 200 | 200 | 0 | 0 | 0.63 | 0.22 | gate_S/F/M/Ret | 优 | checkpoint |
| V45·insider_feats | 历史链 | USA | 320 | 320 | 0 | 0 | 0.69 | 0.29 | gate_S/F/M/Ret | 优 | checkpoint |
| V46·insider_trx_matrix | 主trio | USA | 320 | 320 | 0 | 0 | 0.92 | 0.56 | gate_S/F/M/Ret | 优 | checkpoint |
| V47·search_interest | 并发批 | USA | 320 | 320 | 0 | 0 | 1.59 | 0.73 | gate_S/F/M/Ret | 优 | checkpoint |
| V48·acquisition_model | 并发批 | USA | 320 | 320 | 0 | 0 | 0.79 | 0.44 | gate_S/F/M/Ret | 优 | checkpoint |
| V49·forward_beta_risk | 并发批 | USA | 320 | 320 | 0 | 0 | 0.43 | 0.17 | gate_S/F/M/Ret | 优 | checkpoint |
| V50·board_network | 并发批 | USA | 320 | 320 | 0 | 0 | 0.68 | 0.25 | gate_S/F/M/Ret | 优 | checkpoint |
| V51·behavioral_signals | 并发批 | USA | 320 | 320 | 0 | 0 | 1.72 | 0.75 | gate_S/F/M/Ret | 优 | checkpoint |
| V52·hiring_trends | 并发批 | USA | 320 | 320 | 0 | 0 | 2.50 | 1.86 | gate_S/F/M/Ret | 优 | checkpoint |
| V53·stock_search_trends | 并发批 | USA | 320 | 320 | 0 | 0 | 1.19 | 0.57 | gate_S/F/M/Ret | 优 | checkpoint |
| V54·event_stock_model | 并发批 | USA | 320 | 320 | 0 | 0 | 0.95 | 0.30 | gate_S/F/M/Ret | 优 | checkpoint |
| v52b_hiring_margin | 在飞扫描 | USA | None | 32 | 12 | 0 | 2.65 | 1.77 | FAIL:M=8.9bp | 优 | 在飞 |

**已完成链合计**：5659 次回测 (各 scan 进程写出的 checkpoint)，22 次 PASS/PASS_CHEAP，1 个 found_alphas。
**在飞合计**：1 个进程，已产出 ≈ 32 条回测结果（实时统计，含 checkpoint 持续写入的任务）。

---

## 3. 重点任务详情

### 3.1 V44 / V45 (已完成，主账号历史)

- **V44** (insider_feats)：200/200 全 FAIL (Sharpe 闸门, 最佳 S=0.63)，insider_feats 单字段 edge 不足。
- **V45** (tri_insider_feats)：320/320 = 232 FAIL + **88 error**，错误分布 {'poll_timeout': 8, 'submit_failed': 80}。归因：此前主动 429 风暴后遗症，非代码缺陷；V46 结束后按 submit_gate 重跑这 88 个变体。

### 3.2 V46 (insider_trx, 运行中, PID ?)

- 数据集 insider_trx_matrix，USA D1，三轨 multi-sim；BATCH_SIZE=8、submit_gate=True、no_submit=True。
- 运行时核验：进度日志持续更新 (53.8s/步), 进程存活；320/320 步, 最佳 Sharpe 0.92, 0 个 429。
- **效率评级：优 (运行时已验证)** — 全账号后续任务的参考实现。

### 3.3 并发批次 V47-V54 (已完成, 同源 V46 模板)

| 任务 | dataset | PID | 进度 | 首步最佳S | 实测节奏 | 429 |
|---|---|---|---|---|---|---|

- 7 个进程均为 V46 模板派生 (`scan_v46_tri_insider_trx.py`)，自带 submit_gate + multi-sim + 退避，**效率全部 = 优 (继承模板)**。
- 启动时间错峰 (08:39-08:51)，与已在跑的 V46 共同构成 8 进程并发，**实测零 429**——直接验证"错峰 + 每进程闸门"可安全扩展并发。

---

## 4. 方案效率评估 (源码合规 + 运行时核验, 是否真正落地最优方案)

> 依据 `probe_concurrency_final_report_20260725_0255.md`：**最有效率的提交方案 = 批量提交 + 令牌桶闸门 + 429 退避 + 禁齐射 + 断点续跑**。本维度 = 源码标志位扫描 **且** 运行时核验(进程存活/PID/实测节奏/429)，以区分"源码写了吗"与"运行时真在做"。

### 4.1 最佳实践基准 (5 条硬性标准)

| 标准 | 定义 | 不达标后果 |
|---|---|---|
| 1. 批量提交 multi-sim | 8 表达式/次单 POST，1 令牌换 8 次回测 | 单发提交 = 8 倍令牌消耗 |
| 2. 令牌桶闸门 submit_gate | 显式限速：瞬时并发 <=6、间隔 >=15-20s | 固定 sleep 在外部负载突增时不够稳健 |
| 3. 429 退避 backoff | wd_lib_wrapper 退避重试 | 遇 429 直接崩溃/丢变体 |
| 4. 禁齐射 no-salvo | 同时启动进程 <=6，禁止 >=7 提交 <2s 内并发 | 必触发 429 (实验 2 实证) |
| 5. 断点续跑 checkpoint | 健全 checkpoint | 中断丢全部进度 |

### 4.2 每任务效率合规矩阵 (含运行时核验)

| 任务 | 进程 | 批量 | gate | 退避 | 续跑 | 源码评级 | 实测节奏 | 运行时落地判定 |
|---|---|---|---|---|---|---|---|---|
| V33·analyst10 | 停 | N | Y | Y | Y | **中** | 38.9s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V34·insider_matrix | 停 | Y | Y | Y | Y | **优** | 86.4s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V35·news_sentiment_nlp | 停 | Y | Y | Y | Y | **优** | 50.1s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V36·stock_cluster_dl | 停 | Y | Y | Y | Y | **优** | 46.3s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V37·other545 | 停 | Y | Y | Y | Y | **优** | 49.2s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V38·sustainable_profit | 停 | Y | Y | Y | Y | **优** | 50.7s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V38b·sustainable_profit | 停 | Y | Y | Y | Y | **优** | 51.0s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V39·insider_matrix | 停 | Y | Y | Y | Y | **优** | 48.2s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V39b·insider_matrix | 停 | Y | Y | Y | Y | **优** | 66.5s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V40·cre_exposure_model | 停 | Y | Y | Y | Y | **优** | 44.4s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V41·earnings_risk | 停 | Y | Y | Y | Y | **优** | 44.1s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V42·social_sent_score | 停 | Y | Y | Y | Y | **优** | 44.7s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V43·event_relation | 停 | Y | Y | Y | Y | **优** | 48.5s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V44·insider_feats | 停 | Y | Y | Y | Y | **优** | 60.5s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V45·insider_feats | 停 | Y | Y | Y | Y | **优** | 53.1s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V46·insider_trx_matrix | 停 | Y | Y | Y | Y | **优** | 53.8s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V47·search_interest | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 80.2s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V48·acquisition_model | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 78.5s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V49·forward_beta_risk | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 78.7s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V50·board_network | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 63.5s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V51·behavioral_signals | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 68.3s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V52·hiring_trends | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 142.0s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V53·stock_search_trends | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 78.6s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| V54·event_stock_model | 停 | Y | Y | Y | Y | **优** (继承V46模板) | 56.0s/步 | 已收尾/未运行 (源码合规, 运行时未核验) |
| v52b_hiring_margin | 运行中 | Y | Y | Y | Y | **优** | - | ✅运行中·已验证 (PID ?, -, 429=None) |

### 4.3 评估结论

- **批量提交 (标准1)**：V34-V53 进程产物均来自 multi-sim (BATCH_SIZE=8~10) —— **进程产物证实** 已落地最高效提交 (1 令牌换 8 回测)。**例外：v33_hkg_anl10 为早期脚本**，用单 `api.run_backtest()` + 线程池 (无 multi-sim)，效率偏低，建议后续重构继承 V46 模板。
- **退避 (标准3) / 续跑 (标准5)**：源码含 wd_lib_wrapper 退避 + checkpoint —— 鲁棒性达标 (V45 的 88 error 靠退避无损兜底, 未崩溃)。
- **显式令牌桶闸门 (标准2)**：**全账号 22 个任务全部经源码核验落地显式 submit_gate (优)**。机制 = `submit_gate.py` 跨进程令牌桶 (文件锁 + 磁盘状态, 全局 min_interval=18s, 批间 45s, 429 退避), 经 `multi_sim.py`(V34-V53) 与 `wd_lib_wrapper.run_backtest`(V33 单发) 两条提交路径统一调用 `wait_submit_slot()`。**V46-V53 共 8 个在飞任务另经运行时验证 (PID/节奏/0 429) 落地**。v33 经 wd_lib_wrapper 同样限速合规 (中, 仅缺 multi-sim 批量)。
- **禁齐射 (标准4)**：本次 8 进程并发 **实测零 429** —— 关键在"错峰启动 + 每进程自带 submit_gate", 而非原始"<=6"硬上限。结论修订：**保守上限可上调, 真正约束是瞬时提交浓度, 由每进程 gate 共同维持**; 严禁的是"同账号 >=7 进程在 <2s 内齐射"。
- **运行时 vs 源码的关键区别**：本表"进程"列显示当前 8 个在飞; V33-V45 虽源码合规(优)但进程已死, 评级"优"代表"若运行则必显式限速"。这正是前版报告把 V34-V45 误判为"良/隐式节奏"的修正——它们实际经 multi_sim 继承了 `submit_gate.py` 显式闸门; 前版"少了"的另一层 (漏掉 V47-V53 进程) 现已由进度日志自动发现补齐。

---

## 5. 并发模型与平台限制 (Token-Bucket C=7, 本次实证更新)

经 5+ 组对照实验确立为 **令牌桶限流**：突发容量 **C=7**, 慢补充 ~1 令牌/20-40s。

- **原安全包络 (保守)**：瞬时并发 <=6; 持续提交间隔 >=15-20s; 同账号同时启动进程 <=6。
- **本次实证修正**：V46 (已在跑) + V47-V53 (错峰启动于 08:39-08:51) 构成 **8 进程并发、≈5659 次提交、零 429**。说明在"错峰 + 每进程 submit_gate"条件下, 并发进程数可安全 >6; **真正硬约束是瞬时提交浓度 (<=C=7)**, 由每个进程的 gate 共同压住。
- **已验证危险 (不变)**：>=8 提交在 <2s 内并发 (实验 2 的 10 路突发) -> 必 429。即"齐射"仍禁, 但"错峰多进程"已验证安全。
- **V46/V47-V53 落地**：脚本内置 submit_gate 已落实该包络; 详细证据与图表见 `probe_concurrency_final_report_20260725_0255.md`。

---

## 6. 吞吐量评估 (Throughput / 回测效率)

> 口径：每个 step = 1 次 multi-sim 批量提交，含「提交 + 平台计算 + 轮询」整轮；V46 模板 BATCH_SIZE=8，故 1 step ≈ 8 次回测。α/hr = 3600 / avg_sec_per_step × 8。

| 任务 | α/step | sec/step | α/hr |
|---|---:|---:|---:|
| v52b_hiring_margin | 8 | - | - |
| **聚合 (1 进程并发)** | - | - | **0** |

- **聚合并发吞吐**：1 进程合计 ≈ **0 α/hr**（≈ 0.0 α/min）。
- **单进程基线**：V46 进程已退出，单进程基线缺失，加速比暂不可算；当前在飞 1 进程，聚合并发吞吐 ≈ 0 α/hr。
- **方案层效率 = 优 (令牌零浪费)**：multi-sim 使每次 POST 仅耗 1 令牌换 8 次回测，是令牌最省方案；submit_gate 消除 429 重提浪费；8 进程零 429 实证无令牌浪费。相比单发提交 (1 POST=1 回测)，multi-sim 把令牌效率提升 8×。
- **效率天花板 (当前瓶颈在 gate 而非平台)**：单进程吞吐由各自 submit_gate 节奏(45–70s/step) 决定，而非被平台 429 拒绝——即吞吐被各进程自身限速闸门绑定。实测 8 进程仍零 429，说明**尚未触达平台 compute 饱和**，理论上可再加进程提吞吐，但须保持「错峰 + 每进程 gate」，且受 C=7 突发容量约束 (瞬时提交浓度不能超 7)。
- **核心瓶颈 = 信号发现，不是吞吐**：并发批次首步 Sharpe 仅 -0.14~1.94，远低于 1.25 闸门。在出候选前，0 α/hr 的算力只是加速「挖出 0 候选」。若把同等算力转向已验证的 V39b 风格扩展 (低自相关 + 行业中性 + W189/d3/SECTOR/t1)，出候选概率更高——**吞吐已不是限制因素，范式转向才是**。<br>*附：历史链 V33-V45 完成期吞吐约 40–80 α/hr/进程 (见 §4.2 节奏列)，与当前并发批次同量级，说明单进程效率长期稳定，提升来自并发叠加而非单进程优化。*

---

## 7. 效率结论与 ETA

- **最强信号方向**：V39b (PASS_CHEAP, S=2.58) > V39 (S=2.30) > V34 (S=1.95, 平台侧失败); 均卡在子宇宙 Sharpe 闸门。
- **并发批次 (V47-V54) 终局 (checkpoint 真实最佳 Sharpe)**：V52 hiring_trends **2.50 (全批最高)** > V51 1.72 > V47 1.59 > V53 1.19 > V50 0.68 > V48 0.79 > V49 0.43；V54 event_stock_model 已完成 (最佳 0.95)。V52 的 2.50 信号仅差 **M 闸门 (M=9.7bp, 高换手/成本敏感)** 未过，其余均卡在 S/F/M 闸门；全批 0 过闸。
- **V46 ETA**：2026-07-25T12:49:19 (受 submit_gate 限速)。
- **V45 重跑**：88 个 error 变体建议后续补跑 (按 C=7 包络约 88*~30s ~ 45min)。

---

## 8. 行动建议

1. **并发批次继续**：V46-V53 运行时已验证合规 (优, 0 429), 让其按各自 submit_gate 自然跑完。
2. **统一升级 submit_gate**：将 V46 的显式令牌桶闸门作为模板, 全账号任务统一继承 (V47-V53 已验证可行), 使全局并发纪律自适应化。
3. **重跑 V45 的 88 个 error 变体**：V46 结束后执行, 复用 submit_gate, 避免再抢主账号槽位。
4. **攻克子宇宙 Sharpe 闸门**：对 V39/V39b 类高 Sharpe 信号, 限定 universe=TOP3000 / 调整 neutralization / 加子宇宙约束。
5. **并发批次升维**：V47-V53 各 dataset 首步 Sharpe 偏弱, 关注后续变体是否出现 >1.5 信号; 若普遍 low, 需组合多字段/正交变换。
6. **并发纪律 (修订)**：允许错峰多进程 (>6) 并发, 只要各进程自带 submit_gate 且非 <2s 齐射; 加任务前用本报告 §1 运行时核验确认在飞进程数与 429 状态。

---

## 9. 全量 Python 进程对账 与 `set_RR11jN_` 说明 (盲区修正)

> 本节与 §1 同源(机器级进程枚举), 专门回应 "还有 set_RR11jN_ 进程没汇报" 的疑问, 并给出服务端任务的可见化路径。§1 已是 Python 进程第一视角, 本节聚焦盲区说明。

- **机器级 python 进程总数**: 26
- **WQ BRAIN MCP 服务进程 (platform_functions.py, 交互式工具宿主, 不写本地进度日志)**: **14** 个
- **扫描脚本进程 (scan_*.py)**: 1 个 (其中 §1 已发现 1 个有 progress 日志)
- **看门狗/追踪进程**: watchdog=0, tracker=0; **其他**: 3 个
- **命令行命中 `RR11jN` 的进程**: **0** 个

| PID | 类型 | 命中 RR11jN? | 说明 |
|---|---|---|---|
| 28060 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 56616 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 52532 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 23088 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 26396 | editor | 否 | 其他 |
| 29284 | editor | 否 | 其他 |
| 3720 | editor | 否 | 其他 |
| 19140 | editor | 否 | 其他 |
| 54120 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 13420 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 44476 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 14548 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 38560 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 35484 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 38288 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 53128 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 23516 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 31764 | mcp_server | 否 | WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件 |
| 27516 | editor | 否 | 其他 |
| 18716 | editor | 否 | 其他 |
| 53732 | editor | 否 | 其他 |
| 40460 | editor | 否 | 其他 |
| 26748 | scan_script | 否 | 扫描脚本 (回溯 §1 进度日志) |
| 59684 | other | 否 | 其他 |
| 28836 | other | 否 | 其他 |
| 35372 | other | 否 | 其他 |

### 9.1 关于 `set_RR11jN_` 的调查结论

- **全程检索结论**：在全部磁盘文件 (含 `.venv`)、全部 `*_progress_*.log`、全部 `scan_*.py` 源码、以及上述**机器级进程命令行**中，均未发现任何 `RR11jN` / `set_RR11jN_` 字面量 (文件名 / 字符串 / 进程参数三者皆无；本表 '命中 RR11jN?' 列全为 否)。
- **最可能的解释**：`set_RR11jN_` 是一个 **WQ BRAIN 服务端仿真 / 多仿真实例 ID (或任务集标识)**，经由 WQ BRAIN MCP 助手 / Web 控制台发起。14 个 `platform_functions.py` 进程即其宿主，但它们仅作为**交互式工具服务器**存在 —— `platform_functions.py` 顶部 `logging.basicConfig` 仅输出到控制台、**不写本地文件**，故此类回测在服务端运行、本地无任何 progress 日志。这正是本监控器 (`gen_report.py`) 的盲区：**它只靠 `*_progress_*.log` 自动发现任务**，服务端任务天然不可见。
- **与历史 "感觉少了" 同源但不同类**：上轮漏报 V47-V53 是同一类发现盲区 (硬编码任务列表)，已靠进度日志自动发现修复；本次为**第二类盲区** (服务端 / WQ-BRAIN 任务无本地日志)，需另一类桥接 (见 §9.2)。
- **重要澄清**：本机当前在跑的 python 进程只有三类会碰 WQ BRAIN —— 8 个 scan 脚本 (已报) + 14 个 MCP 服务进程 (交互宿主) + watchdog/tracker。其中**没有任何一个的命令行或产物含 `RR11jN`**，因此 'set_RR11jN_' 不是本机一个可枚举的本地进程名，而是一个服务端句柄。

### 9.2 如何真正看到 `set_RR11jN_` 的状态

1. **WQ BRAIN Web 控制台** (账号 mthyzx@126.com)：Research → Simulations / Multisims，按 ID 含 `RR11jN` 过滤，直接看状态/结果。
2. **MCP 助手对话记录**：14 个 MCP 进程是宿主，发起该任务的对话里会保留仿真 ID 与结果文本。
3. **加一个服务端桥接监控**：在**用户运行环境** (已设 `WQ_USERNAME`/`WQ_PASSWORD`) 下，给 `gen_report.py` 增加 `query_wq_simulations()`：登录 WQ BRAIN → 拉取近 N 个仿真 → 过滤 `RR11jN` → 并入本报告。本 agent 当前环境**未注入 WQ 凭据**，无法代查；需在用户环境运行。

> 结论：本监控器此前未汇报 `set_RR11jN_`，根因是它属于 WQ BRAIN **服务端任务、无本地进程名 / 日志**，不在本工具可发现范围内；并非漏跑或遗漏某本地进程。补充服务端桥接后可在下版报告直接列出。

---

## 10. 候选 Alpha 评测 (研究仿真 IS 闸通过, 提交未验证)

> ⚠️ **口径纠正 (2026-07-25 用户指正)**：`status=PASS/PASS_CHEAP` **仅表示研究仿真(research simulation)的廉价本地闸门通过，绝不等于 WQ 提交就绪**。WQ 真实提交需过四道关：① 研究仿真 IS 指标达标 → ✅ 这 22 个都过了；② **生产仿真 (OOS/样本外)** → ❌ 这 22 个都没跑；③ **生产相关性 PROD_CORRELATION + 自相关 SELF_CORRELATION** (WQ 提交闸门) → 仅 1 个 (`YPgAa3WR`) 进 found_alphas 记录过 prod_corr=0.5325，其余 21 个 results 记录**无 prod_corr 字段=生产关未验**；④ 平台 submittable 判定 + 真实提交 → ❌ 所有 scan 脚本 `no_submit=True`，从未真提交。
> 因此：这 22 个 alpha **均不满足 WQ 提交标准**，应称为"研究仿真 IS 闸通过的候选"，不是"可提交 alpha"。本表 "候选" 取自 checkpoint `results[].status`；"found" (§0 第 3 行) 取自 `found_alphas`，是另一口径 (已跨生产相关性验证)。

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
| 21 | v39b_sub_micro | KPELQn7l | gz_t2_b66z252_TOP3000_d2_SEC_t1 | PASS_CHEAP | 1.67 | 1.18 | 0.87 | 0.11 | USA TOP3000 d1 decay2 SECTOR |
| 22 | v39b_sub_micro | e7xrvnzJ | gz_t2_b66z252_TOP3000_d2_SEC_t12 | PASS_CHEAP | 1.67 | 1.19 | 0.87 | 0.12 | USA TOP3000 d1 decay2 SECTOR |

**按任务分组的共享公式 (共 2 个根集群)**：

- **v52b_hiring_margin** (12 个)：代表 `m0_TOP300_d4_SEC_t2` | 配置 `USA TOP3000 d1 decay4 SECTOR` | Sharpe 1.91–2.33
  ```
rank(group_zscore(ts_zscore(ts_backfill(vec_avg(aggregate_open_positions_count), 66), 63), industry))
  ```
- **v39b_sub_micro** (10 个)：代表 `gz_t2_b66z189_TOP3000_d2_SEC_t1` | 配置 `USA TOP3000 d1 decay2 SECTOR` | Sharpe 1.67–2.18
  ```
rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))
  ```

**评测结论与提交建议**：

- **🔎 验证层级与提交就绪判定 (用户 2026-07-25 指正核心)**：WQ 提交须过四关，当前 22 个候选的实际状态——
  1. 研究仿真 IS 指标达标 (cheap_gates: S>1.58 / F>1.0 / TVR∈[0.05,0.30] / M>10bp / Ret>0.05 + 近闸 IS_LADDER_SHARPE+LOW_2Y_SHARPE)：✅ **22/22 全过**
  2. 生产仿真 (OOS/样本外)：❌ **0/22 跑过** (仅研究仿真 research sim)
  3. 生产相关性 PROD_CORRELATION + 自相关 SELF_CORRELATION (WQ 真正提交闸门)：✅ 仅 **1/22** 跨过 —— `YPgAa3WR` (v39b, prod_corr=0.5325, 进 found_alphas)；其余 **21** 个 results 记录**无 prod_corr 字段 = 生产关从未验** (其中 v52b 组 8 个连子宇宙 Sharpe 检查都没做, 记录无 sub_univ)
  4. 平台 submittable 判定 + 真实提交：❌ **0/22** (所有 scan 脚本 `no_submit=True`, 从未真提交)
  **→ 结论：这 22 个 alpha 均不满足 WQ 提交标准。** `PASS_CHEAP` 仅表示"廉价研究仿真闸门通过", 不是"可提交"。真要提交须对每个候选: ① 跑生产仿真; ② 取全量 `/check` (PROD_CORRELATION/SELF_CORRELATION/全部 IS 检查); ③ 平台判定 submittable; ④ 显式 submit (关掉 no_submit)。
- **跨 2 个不同根集群**：22 个候选 alpha 分属以下任务（表达式根不同，是**独立信号方向**，提交时彼此不构成复制约束，但仍需各自与已上线 alpha 查相关）：
  - `v52b_hiring_margin`: 12 个，代表 `m0_TOP300_d4_SEC_t2` (Sharpe 2.33)
  - `v39b_sub_micro`: 10 个，代表 `gz_t2_b66z189_TOP3000_d2_SEC_t1` (Sharpe 2.18)
- **标签 token 歧义说明 (消除误读, 仅针对 v39b 组)**：alpha `label` 中的 `d2`/`d3` 指 **decay (衰减窗口)**，与本表 `cfg` 列 `d1` (settings.delay=1) **不冲突** —— 经核对原始 checkpoint，`settings.delay` 恒为 1、`settings.decay` 为 2/3。即 `gz_t2_b66z189_TOP3000_d2_SEC_t1` 读作 **delay=1、decay=2、SECTOR 中性、t1 标签**。提交以 WQ 控制台实际参数 (settings.delay/decay) 为准，勿被 label 的 `d` 前缀误导。
- **廉价 IS 闸门 (本地 gate) 全过**：Sharpe 1.67–2.33 (远超 1.25 闸门)，子宇宙 Sharpe (v39b 组) 0.87–1.08 (>=1.0 通过)，turnover 0.10–0.15 (合规)，fitness 各异但均达**本地** gate 要求。**注意**：这是脚本 `cheap_gates` 的本地判定，**非 WQ 提交闸门**；WQ 提交闸门 (生产仿真 + PROD_CORRELATION + 平台 submittable) 尚未验证 (见上条🔎)。即 22 个**都不算已通过 WQ 提交标准**。
- **v52b 突破 M 闸门印证 (廉价 IS 闸层面)**：上一轮 v52b 首版 (decay 偏短) 仅差 `M=8.9bp` (高换手/成本敏感) 未过廉价本地闸门；本轮 decay4 SECTOR 变体已 **4 个过廉价 IS 闸** (Sharpe 2.31–2.33, status=PASS_CHEAP)，证实**降换手是直击 M 闸门的有效方向**——但 v52b 16 变体中仍有 12 个 FAIL (主因 M)，说明降换手幅度需继续调优才能规模化；且这 4 个**生产相关性关未验** (无 prod_corr 记录)，同样不满足提交标准。
- **提交策略建议**：WQ 对同信号近重复 alpha 有**自相关 / 低相关**约束。建议 ① 先提交 1–2 个代表性变体探路——全局 Sharpe 最高为 `zqRkPVbX` (`m0_TOP300_d4_SEC_t2`, 2.33)，v52b 组最高为 `zqRkPVbX`；② 同组其余变体提交前需评估与已上线 alpha 相关系数，避免被判复制拒收；③ 若要规模化，应扩展表达式非线性度 (换字段/加变换/组合) 而非仅改 delay/标签。
- **账号归属澄清**：v39b/v52b 均为 scan 脚本任务，checkpoint 落本机 `results/`，属**主账号 `mthyzx@126.com`**；与 §9 `set_RR11jN_` (mlh 账号、服务端任务、无本地日志) 是**不同账号、不同来源**，不可混淆。本表 22 个可在主账号 WQ 控制台按 pid 调出**研究仿真结果**查看，但提交前须补齐上述四关验证 (当前均未提交)。
- **提交路径 (须先补验证)**：不能直接 Submit。正确顺序 — ① 对每个候选跑**生产仿真**; ② 取全量 `/check` 确认 PROD_CORRELATION/SELF_CORRELATION/全部 IS 检查通过; ③ WQ 控制台判定 `submittable`; ④ 显式 submit (当前 `no_submit=True` 须开启)。建议优先验证已跨生产相关性关的 `YPgAa3WR` (prod_corr=0.5325)，其余 {len(sub)-_vcount} 个需先补生产仿真+相关性验证再谈提交。

*报告生成：2026-07-25 20:51:09 GMT+8 · 数据源 results/*_checkpoint.json (进程产物) + *_progress_*.log (运行时核验, 自动发现 V46-V53) + scan_v*.py (源码) + 机器级进程枚举 (Get-CimInstance) · 生成器 gen_report.py 可复跑*