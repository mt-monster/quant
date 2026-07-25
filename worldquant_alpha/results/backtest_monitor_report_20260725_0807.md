# WorldQuant Brain PPA 任务回测报告

- **数据快照时间**: 2026-07-25 08:07 GMT+8
- **覆盖任务**: V33 - V46 (共 16 个扫描任务)
- **累计回测次数**: 2755  |  **累计通过候选(found_alphas)**: 1  |  **全链路最佳 Sharpe**: 2.58
- **平台并发模型**: Token-Bucket 令牌桶，突发容量 C=7 (已定稿，详见 `probe_concurrency_final_report_20260725_0255.md`)

---

## 0. 执行摘要

1. **主账号 trio (V44/V45/V46，共享 mthyzx@126.com)** 是本轮并发监控对象。V44、V45 已自然结束；V46 仍在运行 (PID 48172)。
2. **V44** 完成 200/200，全部 FAIL (Sharpe 闸门，最佳 S=0.63，insider 信号偏弱)。
3. **V45** 完成 320/320：232 FAIL + **88 个 error (80 submit_failed + 8 poll_timeout，均属 429 风暴后遗症)** -- 提交被拒或轮询超时，并非代码缺陷，而是回测槽被主动制造的 429 风暴占满所致，需重跑。
4. **V46** 刚启动 (08:02:24)，脚本内置 Token-Bucket 提交闸门 (>=18s 间隔 / >=45s 批间)，已杜绝 429 风险。当前 8/320 步。
5. **全局最主要失败闸门 = LOW_SUB_UNIVERSE_SHARPE**：V39/V39b 等信号主宇宙 Sharpe 高达 1.9-2.6，但在子宇宙 (小盘/低流动性) 崩塌，系统性不通过。
6. **唯一通过候选**：v39b 产出 1 个 PASS_CHEAP (S=2.58, F=2.06)。

---

## 1. 进程盘点 (Process Inventory)

| 任务 | PID | 状态 | 启动时间 | 进度 |
|---|---|---|---|---|
| V44 insider_feats | 58956 | DEAD (已完成) | 2026-07-24 ~22:54 | 200/200 |
| V45 tri_insider_feats | 53520 | DEAD (已完成) | 2026-07-25 ~00:08 | 320/320 |
| **V46 tri_insider_trx** | **48172** | **ALIVE (运行中)** | 2026-07-25 08:02:24 | 8/320 |

> 进程核验：当前仅 PID 48172 (scan_v46_tri_insider_trx.py) 存活，V44/V45 进程已退出。V46 内置 submit_gate，多模拟提交按令牌桶节奏节流。

---

## 2. 全链路回测概览 (V33 -> V46)

| 任务 | 数据集方向 | N | PASS | FAIL | error | found | 最佳S | 最佳F | 主导失败原因 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| v33_hkg_anl10 | - | 59 | 0 | 59 | 0 | 0 | 0.76 | 0.34 | gate_S/F/M/Ret |
| v34_insider_matrix | - | 72 | 0 | 0 | 0 | 0 | 1.95 | 1.36 | platform_FAIL |
| v35_news_nlp | - | 24 | 0 | 24 | 0 | 0 | 0.65 | 0.25 | gate_S/F/M/Ret |
| v36_stock_cluster | - | 157 | 0 | 157 | 0 | 0 | 0.57 | 0.22 | gate_S/F/M/Ret |
| v37_other545 | - | 187 | 0 | 187 | 0 | 0 | 0.98 | 0.53 | gate_S/F/M/Ret |
| v38_sust_profit | - | 278 | 0 | 278 | 0 | 0 | 1.12 | 0.73 | gate_S/F/M/Ret |
| v38b_sust_rescue | - | 270 | 0 | 270 | 0 | 0 | 1.07 | 0.56 | gate_S/F/M/Ret |
| v39_insider_rescue | USA | 240 | 0 | 240 | 0 | 0 | 2.30 | 1.77 | PF:LOW_SUB_UNIVERSE_SHARPE |
| v39b_sub_micro | USA | 160 | 10 | 150 | 0 | 1 | 2.58 | 2.06 | PF:LOW_SUB_UNIVERSE_SHARPE |
| v40_cre | USA | 200 | 0 | 200 | 0 | 0 | 0.43 | 0.10 | gate_S/F/M/Ret |
| v41_earn_risk | USA | 180 | 0 | 180 | 0 | 0 | 0.75 | 0.27 | gate_S/F/M/Ret |
| v42_social | USA | 200 | 0 | 200 | 0 | 0 | 0.88 | 0.39 | gate_S/F/M/Ret |
| v43_event_rel | USA | 200 | 0 | 200 | 0 | 0 | 0.47 | 0.17 | gate_S/F/M/Ret |
| v44_insider_feats | USA | 200 | 0 | 200 | 0 | 0 | 0.63 | 0.22 | gate_S/F/M/Ret |
| v45_tri_insider_feats | USA | 320 | 0 | 232 | 88 | 0 | 0.69 | 0.29 | gate_S/F/M/Ret |
| v46_tri_insider_trx | USA | 8 | 0 | 8 | 0 | 0 | 0.82 | 0.44 | gate_S/F/M/Ret |

**合计**：2755 次回测，10 次 PASS/PASS_CHEAP，1 个 found_alphas。

> 说明：V34 的 72 条结果 status=None 且 fails=['platform_FAIL']，属数据集侧平台错误 (eur_aggregated_value 字段在平台不可用)，非闸门失败。V39/V39b 的 LOW_SUB_UNIVERSE_SHARPE 表示主宇宙 Sharpe 达标但在子宇宙不满足。

---

## 3. 重点任务详情

### 3.1 V44 - insider_feats (已完成)

- 规模：200/200，全部 FAIL (gate_S/F/M/Ret)。
- 最佳 Sharpe **0.63**，最佳 Fitness 0.22，Margin 约 4-5bp -- 信号强度整体偏低。
- 失败主因：Sharpe/Fitness/Margin/Return 四项闸门均不达标 (如 S=0.600 F=0.270 M=4.7bp Ret=0.0246)。
- 结论：insider_feats 单字段直接构造的 alpha 在该数据集上 edge 不足，需进阶变换或组合。

### 3.2 V45 - tri_insider_feats (已完成，含 429 风暴)

- 规模：320/320 = 232 FAIL + **88 error**。
- 88 个 error 的失败字符串分布：{'poll_timeout': 8, 'submit_failed': 80}（80 `submit_failed` = 提交即被拒，多为 429；8 `poll_timeout` = 提交已被接受但轮询超时）。
- **归因**：这 88 个 error 全部发生在并发探测阶段 (measure_L / measure_rate 系列) 我主动制造的 **429 风暴**期间 -- 回测槽被占满导致提交被拒或轮询超时，**非 V45 代码缺陷**。这 88 个变体在平台上实际未完成评估，需对它们重跑。
- 正常完成的 232 个 FAIL 最佳 Sharpe 0.69 -- 与 V44 同属 insider 信号偏弱区间。
- **行动项**：重跑 V45 中 88 个 error 变体 (80 submit_failed + 8 poll_timeout，建议待 V46 结束、主账号空闲后执行，避免再次抢槽)。

### 3.3 V46 - tri_insider_trx (运行中，PID 48172)

- 数据集：insider_trx_matrix (未点亮 MATRIX，cov~0.77)，USA D1，三轨 multi-sim。
- 配置：BATCH_SIZE=8、submit_gate=True (>=18s 间隔 / >=45s 批间)、no_submit=True (只存草稿，不落平台)。
- 进度：启动于 08:02:24，截至快照 8/320 步。前 8 个 (explore/improve/rescue 各 3/3/2) 最佳 Sharpe 0.82 (improve 轨 imp0_0_w189to126)。
- 队列余量：explore 1239 / improve 85 / rescue 97 (约 1421 待跑，但脚本 total_steps=320 预算封顶，会按预算截断)。
- **ETA (来自进度日志自估)**：2026-07-25T10:37:10 (仍随节拍稳定中；受令牌桶闸门限速，预计约 2026-07-25 10:40-14:00 收尾)。
- 并发安全：V46 已内置令牌桶闸门，且 no_submit，不会触发 429，可与其他任务安全并行。

---

## 4. 并发模型与平台限制 (Token-Bucket C=7)

经 5 组对照实验 (measure_L / measure_L2 / measure_L3 / measure_rate / probe_concurrency)，已推翻"固定并发槽"假设，确立为 **令牌桶 (token-bucket) 限流**：

- **突发容量 C=7**：瞬时并发提交上限约 7 个槽；超过即 429。
- **慢速补充**：约每 20-40s 回补 1 个令牌，决定性因素是**瞬时提交集中度**而非总 K 数。
- **实测证据链**：K=10 同步突发曾 10/0 全过 (桶满)，K=11/12 出现 4-5 个 429；双次满桶 K=8 突发均稳定 7/1 -> 锁定 C=7(+-1)。
- **生产安全包络**：瞬时并发 <=6；持续提交间隔 >=15-20s；单批 <=6 路同时发起。
- **V46 落地**：脚本内置 submit_gate 已落实该包络，后续任务应复用此闸门。
- 详细证据与图表见：`results/probe_concurrency_final_report_20260725_0255.md`。

---

## 5. 效率结论与 ETA

- **最强信号方向**：V39b (PASS_CHEAP, S=2.58) > V39 (S=2.30) > V34 (S=1.95，但平台侧失败)。这些高 Sharpe 信号卡在 **子宇宙 Sharpe 闸门** -- 核心瓶颈是信号在低流动性子宇宙失效。
- **insider 方向 (V44/V45/V46)**：Sharpe 仅 0.6-0.8，明显弱于 eur_aggregated / indmom 系，需更强特征工程或正交化。
- **V46 ETA**：见 3.3，预计 2026-07-25 上午至中午收尾。
- **V45 重跑**：88 个 poll_timeout 变体建议后续补跑，预计量级与正常回测相当 (按 C=7 包络约 88*~30s ~ 45min)。

---

## 6. 行动建议

1. **勿动 V46**：让其按令牌桶闸门自然跑完 (已安全)。
2. **重跑 V45 的 88 个 error 变体 (80 submit_failed + 8 poll_timeout)**：待 V46 结束后执行，复用 submit_gate，避免再抢主账号槽位。
3. **攻克子宇宙 Sharpe 闸门**：对 V39/V39b 类高 Sharpe 信号，尝试限定 universe=TOP3000、调整 neutralization、或加子宇宙约束，突破 LOW_SUB_UNIVERSE_SHARPE。
4. **insider 方向升维**：V44/V45/V46 信号偏弱，建议组合多字段 / 加入正交变换，而非单字段直用。
5. **固化并发闸门**：将 V46 的 submit_gate (>=18s / >=45s) 作为所有主账号任务的标配，杜绝 429 风暴。

---
*报告生成：2026-07-25 08:07 GMT+8 · 数据源 results/*_checkpoint.json + v46 进度日志*