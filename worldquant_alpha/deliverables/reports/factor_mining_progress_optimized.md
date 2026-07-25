# 因子挖掘进度汇报（优化版）

- **快照时间**：2026-07-25 21:30 GMT+8 ｜ **生成器**：`gen_report_live.py`（可复跑）
- **数据口径**：机器级 Python 进程枚举 + `results/*_checkpoint.json` + `*_progress_*.log` + 脚本源码核验

> ⚠️ **最重要结论**：全部 **26 个候选 Alpha 仅通过"研究仿真 IS 廉价闸门"、未经完整提交验证**；其中仅 **1 个**跨过生产相关性关（`YPgAa3WR`），**0 个完成平台真实提交**。**26 个均不满足 WQ 提交标准，请勿视作可提交 Alpha。**

---

## 一、核心结论（结论先行）

**1. 当前在飞架构已切换为 9 个挖掘任务（10 进程）。**
- 主账号：`v52b_hiring_margin` + **7 路新 `ds_*` 数据集舰队**（21:06–21:09 由 `fleet_keeper.py` 错峰拉起，目标 8 路）。
- 独立账号：`tri_track_undug.py`（tabbit/world6 体系，CONCURRENCY=3 分片挖掘）。
- 旧 `v47–v54` 舰队已结束；21:13 那份报告描述的是旧架构，**本次为最新真实状态**。

**2. 累计产出（全部 checkpoint 合计）：5859 次回测 / 26 个 IS 闸通过候选 / 1 个跨生产相关性验证 / 0 个平台提交。** 全链路最佳 Sharpe **2.65**（v52b 某 FAIL 变体）。

**3. 核心瓶颈是"信号发现"而非"吞吐"。** 7 路 ds 舰队目前 **0 个候选**，最佳首步 Sharpe 仅 `web_traffic_engage` 1.88、`techindi_model` 1.39、`pv` 0.63，其余 <0.5——加并发只是加速"挖 0 候选"。

**4. 平台并发模型 = 令牌桶限流，突发容量 C=7。** 在飞 10 进程（多账号/错峰/各带 submit_gate）实测**全局零 429**，并发纪律已落地合规。

---

## 二、关键问题（问题其次）

**问题 1：26 个候选无一满足提交标准。** 真实提交须过四关——① 研究仿真 IS 指标 ✅26/26；② 生产仿真(OOS) ❌0/26；③ 生产相关性（仅 `YPgAa3WR` 通过，prod_corr=0.5325）✅1/26；④ 平台 submittable+真实提交 ❌0/26（脚本 `no_submit=True`）。`PASS_CHEAP` 仅表示"廉价 IS 闸通过"，**不等于可提交**。

**问题 2：新 ds 舰队首步信号普遍偏弱，0 候选。** 7 路均含 submit_gate + multi-sim(BATCH=8) + 续跑，效率评级"优"、零 429，但信号质量未达 1.5 过闸线，是目前的真实短板。

**问题 3：历史最强信号仍卡"子宇宙 Sharpe"闸门。** 主导失败 = `LOW_SUB_UNIVERSE_SHARPE`（V39b S=2.58 / V39 S=2.30 / V34 S=1.95 均平台侧失败）。这是比 IS 闸更硬的约束。

**问题 4：监控盲区导致旧工具漏报。** 原 `gen_report.py` 用 `^v\d+` 过滤 checkpoint，**整个 `ds_*` 舰队被跳过**；`tri_track_undug.py` 被误判为 `other`（实为真实挖掘任务）。本报告已修正：改判单列 + 纳入 ds 舰队，不再漏报。

**问题 5：吞吐数字勿误读。** 在飞实测聚合并发 ≈ **4666 α/hr 是早期乐观值**（任务刚启动、暖队列）；稳态基准下 7 路真实可持续 ≈ **603 α/hr**。当前值应视为上限。

---

## 三、行动建议（方案最后）

**1. 舰队按现状继续跑完。** 7 路 ds 舰队 + v52b + tri_track 运行时已验证合规（优，零 429），让其按各自 submit_gate 自然推进。

**2. 主攻子宇宙 Sharpe 闸门。** 对 V39/V39b 类高 Sharpe 信号，限定 `universe=TOP3000` / 调整 neutralization / 加子宇宙约束，突破平台 FAIL。

**3. v52b 继续升维。** 降换手变体（decay4 SECTOR）已 4 个过廉价 IS 闸（S=2.31–2.33），是下一轮最值得挖的方向；规模化过 M 闸并补生产验证。

**4. 并发纪律（修订）。** 允许错峰多进程（>6）并发，只要各进程自带 submit_gate 且非 <2s 齐射；加任务前用 §进程对账确认在飞数 + 429。

**5. 提交前必补四关。** 对候选逐个跑 生产仿真 → `/check`(PROD/SELF_CORRELATION) → 平台 submittable 判定 → 显式 submit（关 `no_submit`）。**优先验证已跨生产相关性关的 `YPgAa3WR`。**

---

## 附：精简参考（详细数据见原始报告 `factor_mining_progress_20260725_2130.md`）

**A. 进程对账（机器级枚举）**：接触 WQ BRAIN 进程 25 = 挖掘 10（scan 1 + 三轨 9）+ MCP 宿主 14 + 舰队守护 1；编辑器 8（idle）。命令行命中 `RR11jN`：0（服务端实例，仅 WQ BRAIN 控制台可见）。

**B. 候选 Alpha 分布（26 个，2 个根集群）**：
- `v52b_hiring_margin`（16 个）：配置 `USA TOP3000 d1 decay4 SECTOR`，Sharpe 1.79–2.33；公式 `rank(group_zscore(ts_zscore(ts_backfill(vec_avg(aggregate_open_positions_count),66),63),industry))`。
- `v39b_sub_micro`（10 个）：配置 `USA TOP3000 d1 decay2/3 SECTOR/INDUSTRY`，Sharpe 1.67–2.18；公式 `rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2,66),189),industry))`。
- 跨集群无复制约束，但提交前仍需各自与已上线 alpha 查相关。

**C. ds 舰队进度（7 路均 24/320≈8%，零 429）**：首步最佳 Sharpe — web_traffic_engage 1.88、techindi_model 1.39、pv 0.63、order_book 0.45、equity_kpi 0.40、ml_factor 0.36、quant_factor_lib 0.21。
