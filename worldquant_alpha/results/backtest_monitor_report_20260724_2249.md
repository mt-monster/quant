# 回测监控报告 — 2026-07-24 22:49 (GMT+8)

> 用户手动发起（V33 HKG PPA 进度汇报框架）｜框架：进程盘点 → 并发模型 → 效率结论 → ETA 分析

## 一、进程盘点（Python 全量枚举 + 分类）

| 类别 | PID | 任务 | 进度 | 状态 |
|---|---|---|---|---|
| WQ 挖掘 | 45780 | `scan_v43_event_relation.py`（主账号 mthyzx@126.com，multi-sim） | 192/200 (96%) | 运行中（末批 193–200 in-flight） |
| WQ 挖掘 | 19996 | `tabbit_option9.py`（教程账号 mthyzx@gmail.com，ThreadPool=3） | CSV 414 done | 运行中 |
| 基础设施 | ~21 个 | Cursor LSP / MCP-SVC / EDITOR 等 | — | idle，非挖掘 |

- 全量 `python.exe` 共 **23** 个，其中 **2 个为 WQ 挖掘任务**，其余为空闲基础设施（确认无隐藏第三挖掘任务）。
- V43 检查点 `v43_event_rel_checkpoint.json` 末次写入 `22:42:08`；日志末条 `done=192 @ 22:42:08`；现 22:49:21 进程仍在，末批进行中。
- tabbit CSV 末次落盘 `22:49:11`，持续写入。

## 二、并发模型

| 任务 | 并发模型 | 批次/并发 | 实测吞吐 | 账号 | 平台槽位 |
|---|---|---|---|---|---|
| V43 | multi-sim（单 POST 提 8 条 list，1 槽并行 8 子任务）+ 冷却 45s | BATCH=8 | ≈76 α/hr（192 / 9084.6s） | 主账号 | 占 1 个 multi-sim 槽 |
| tabbit | ThreadPoolExecutor CONCURRENCY=3（教程账号无 multi-sim，开 3 单模拟） | 3 | ≈110 α/hr（近 24min +44） | 教程账号 | 占 3 个单模拟槽 |

- 两任务分属**独立账号/额度**，互不争用；叠加平台并发 ≈ 8 + 3 = **~11 路并行模拟**。
- V43 BATCH=8 即基准最优档（multi(8)=86.1 α/hr）；本次 76 α/hr 略低于基准，因 event_relation 数据集更重、末批 latency 偏高。
- tabbit CONCURRENCY=3 为教程账号硬上限，满配。

## 三、效率结论

1. **吞吐已达各自模型设计最优区**：V43=8/批 multi-sim、tabbit=3 单模拟均为对应账号/配置上限档；批 >8 未基准测试，理论上限无法证实，并发调优无边际收益。
2. **绝对瓶颈仍是信号发现**：V31–V43 + tabbit 累计 ≈2000+ alpha，仅 V39b（YPgAa3WR）1 条通过全部门槛。V43 末态最佳 Sharpe **0.47**（较 168 步时的 0.35 略升，但仍 ≪ 1.25 闸门），**0 候选**；末 32 变体 Sharpe 仍全负或远低于闸门——**event_relation 方向确认死胡同**。
3. **优先动作应为范式转向**：V43 收尾（~22:50–22:53）后主账号槽位空闲，应立即拉起 V44。

## 四、ETA 分析（必填）

### V43 event_relation（PID 45780）
- **完成/总数**：192 / 200（96%）
- **已运行**：9084.6s ≈ 2h31m（自 20:10）
- **剩余**：8 变体（末批 193–200，multi-sim 单批次 in-flight）
- **吞吐**：76 α/hr（平均 47.32 s/step，稳定）
- **墙钟 ETA**：日志末条自投影 22:48:27；现 22:49:21 已过，进程仍 alive，末批 latency 略高于均值的批次 wall（279–342s）→ **预计 ≈ 22:50–22:53 收尾（置信度：高）**。
- **后处理阶段**：脚本 `NO_SUBMIT=True`，且 0 个候选 → **无后处理阶段**，收尾即释放主账号槽位。
- **置信度**：高。仅剩 1 个 in-flight 批次，节奏确定。
- **结论**：自然收尾，无需人工 cut；收尾后主账号空闲，**V44 可立即拉起**。

### tabbit_option9（PID 19996）
- **完成**：CSV 414 done（415 行含表头），较 22:24 的 370 +44 / ~24min
- **吞吐**：~110 α/hr
- **ETA**：**开放**（field-sweep，TOP_FIELDS=12 遍历 75 字段，总预算不定）
- **候选**：0/414（option9 模板家族 Fitness 结构性过低）
- **置信度**：中（开放 ETA）
- **处置提示**：单实例无 CSV 交叉写入风险；维持收割 CSV 或与「先停」决策冲突（待用户定夺）。

## 五、综合建议（待用户决策）

1. **🚀 范式转向优先级最高**：V43 约 22:50–22:53 收尾后主账号空闲，立即用 V39b 锚点起草并拉起 `scan_v44_*`（未点亮金字塔 value 家族 `eur_top_value_*` + 低自相关 `group_zscore(ts_zscore(ts_backfill(...)))` 结构；保留 checkpoint 续跑 + `NO_SUBMIT` 人工确认）。
   - V39b 锚点：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2,66),189),industry))`，USA/TOP3000/SECTOR/decay3/trunc0.01/P6Y，IS Sharpe 2.08 / Fitness 1.67 / selfCorr 0.20（已回填 IS 明细）。
2. **tabbit 去留**：维持单实例收割 CSV，或按「先停」决策终止（PID 19996）。无 CSV 损坏风险。
3. **V33 HKG**：自 07-23 14:20 暂停，未动。

---
*数据源：V43 `results/v43_event_rel_checkpoint.json` + `v43_event_rel_progress_20260724_201042.log`；tabbit `results/tabbit_option9_results.csv`；`tasklist` 进程枚举。*
