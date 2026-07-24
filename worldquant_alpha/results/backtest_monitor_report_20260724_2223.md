# 回测监控报告 — 2026-07-24 22:23 (GMT+8)

> 自动生成（V33 HKG PPA 进度汇报 / 每小时轮次）｜框架：进程盘点 → 并发模型 → 效率结论 → ETA 分析

## 一、进程盘点（Python 全量枚举 + 分类）

| 类别 | PID | 任务 | 进度 | 状态 |
|---|---|---|---|---|
| WQ 挖掘 | 45780 | `scan_v43_event_relation.py`（主账号 mthyzx@126.com，multi-sim） | 168/200 (84%) | 运行中 |
| WQ 挖掘 | 19996 | `tabbit_option9.py`（教程账号 mthyzx@gmail.com，ThreadPool=3） | CSV 370 done | 运行中（父 25740） |
| 基础设施 | 28024 / 5756 等 ~20 个 | Cursor Jedi LSP / MCP-SVC / EDITOR 等空闲进程 | — | idle，非挖掘 |

- 全量 `python.exe` 共 **23** 个，其中 **2 个为 WQ 挖掘任务**，其余为空闲基础设施（确认无第三个隐藏挖掘任务；与 22:22 快照一致）。
- V43 进度日志末条 `done=168 @ 22:19:54`，至今无新增完成（下一批次进行中）。
- tabbit CSV 末次落盘 `22:24:53`，仍在持续写入。

## 二、并发模型

| 任务 | 并发模型 | 批次/并发 | 实测吞吐 | 账号 | 平台槽位 |
|---|---|---|---|---|---|
| V43 | multi-sim（单 POST 提 8 条 list，1 槽并行 8 子任务）+ 冷却 45s | BATCH=8 | ≈78 α/hr（168 变体 / 7751s） | 主账号 | 占 1 个 multi-sim 槽 |
| tabbit | ThreadPoolExecutor CONCURRENCY=3（教程账号无 multi-sim，开 3 单模拟） | 3 | ≈120 α/hr（近 3 min +6） | 教程账号 | 占 3 个单模拟槽 |

- 两任务分属**独立账号/额度**，互不争用槽位；叠加平台并发 ≈ 8（multi-sim 子任务）+ 3 = **~11 路并行模拟**。
- V43 BATCH=8 即此前基准 `bench_v34_sim_speed` 的最优档（multi(8)=86.1 α/hr）；本次 78 α/hr 略低于基准，因 event_relation 数据集更重、部分批次 wall 达 342s（非 279s）。
- tabbit CONCURRENCY=3 为教程账号硬上限，已满配。

## 三、效率结论

1. **吞吐已达各自模型设计最优区**：V43=8/批 multi-sim、tabbit=3 单模拟均为对应账号/配置的上限档；批大小 >8 从未基准测试，理论上限无法证实，但调优并发**无边际收益**。
2. **绝对瓶颈仍是信号发现，非吞吐**：V31–V43 + tabbit 累计 ≈2000+ alpha，仅 V39b（YPgAa3WR）1 条通过全部门槛并提交。V43 最佳 Sharpe **0.35** ≪ 闸门 1.25；近 20 个变体（step 149–168）全部 FAIL，Sharpe −0.14~−0.65、Fitness −0.02~−0.23——**event_relation 方向确认死胡同**。
3. **优先动作应为范式转向，而非并发调优**：主账号槽位将于 V43 收尾后（~22:45）空闲，应立即拉起 V44。

## 四、ETA 分析（必填）

### V43 event_relation（PID 45780）
- **完成/总数**：168 / 200（84%）
- **已运行**：~2h09m（7751s，自 20:10）
- **剩余**：32 变体
- **吞吐**：78 α/hr（平均 46.14 s/step，稳定）
- **墙钟 ETA**：32 × 46.14s ≈ **1476s ≈ 24.6 min → 约 2026-07-24 22:45–22:49**
- **后处理阶段**：脚本 `NO_SUBMIT=True`，且 0 个 `pass_cheap` 候选 → **无后处理阶段**，收尾即释放主账号槽位。
- **置信度**：**高**。multi-sim 批次节奏确定、平均步时稳定、剩余批次少（4 批）；无突跳风险。
- **结论**：自然收尾，无需人工 cut；收尾后主账号空闲。

### tabbit_option9（PID 19996）
- **完成**：CSV 370 done（371 行含表头），较 22:22 的 364 +6 / ~3min
- **吞吐**：~120 α/hr
- **ETA**：**开放**（field-sweep，TOP_FIELDS=12 遍历 75 字段，总预算不定，无法给固定墙钟 ETA）
- **候选**：0/370（option9 模板家族 Fitness 结构性过低，同生产 scan_v* 死结）
- **置信度**：中（开放 ETA，依赖字段预算）
- **处置提示**：与「先停」决策仍冲突，但单实例无 CSV 交叉写入风险；建议维持现状收割 CSV。

## 五、综合建议（待用户决策）

1. **🚀 范式转向优先级最高**：V43 收尾（~22:45）后主账号空闲，立即用 V39b 锚点起草并拉起 `scan_v44_*`（未点亮金字塔 value 家族 `eur_top_value_*` + 低自相关 `group_zscore(ts_zscore(ts_backfill(...)))` 结构；保留 checkpoint 续跑 + `NO_SUBMIT` 人工确认）。
   - V39b 锚点：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2,66),189),industry))`，USA/TOP3000/SECTOR/decay3/trunc0.01/P6Y，IS Sharpe 2.08 / Fitness 1.67 / selfCorr 0.20（已回填 IS 明细）。
2. **tabbit 去留**：维持单实例运行收割 CSV，或按「先停」决策终止（PID 19996）。无 CSV 损坏风险。
3. **V33 HKG**：自 07-23 14:20 暂停，未动（与本轮无关）。

---
*数据源：V43 `results/v43_event_rel_checkpoint.json` + `v43_event_rel_progress_20260724_201042.log`；tabbit `results/tabbit_option9_results.csv`；`tasklist`/`wmic` 进程枚举。*
