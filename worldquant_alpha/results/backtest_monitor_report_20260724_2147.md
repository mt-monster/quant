# 回测任务监控报告

**生成时间**：2026-07-24 21:47 (GMT+8)
**分析视角**：Python 进程全量枚举 + 逐任务并发模型 + 回测效率结论（固化框架）
**自动化**：V33 HKG PPA 进度汇报（每小时触发，本轮回应用户「拉一份最新的监控报告」）

---

## 一、执行概要（关键结论先行）

| 项 | 状态 |
|---|---|
| 当前活跃挖掘作业 | **1 个**：V43 event_relation（主账号 multi-sim） |
| 已处置异常 | tabbit_option9 出现 **2 个并发实例**，已按「先停」决策全部终止（PID 17988 / 7408） |
| V43 进度 | 120 / 200（60%），**0 候选**，最佳 Sharpe 0.35，近 20 步全部 FAIL |
| tabbit 累计 | CSV 309 done / 311 行，历史筛查 **0/92 候选**（Fitness 结构性死结） |
| 全局累计 | V31–V43 + tabbit ≈ **2000+ alpha，仅 1 条上线（V39b）** |
| 瓶颈判断 | **信号发现，不是吞吐**；提并发只加速「挖出 0 候选」 |

---

## 二、Python 进程全量盘点（21:47 快照）

> 全盘枚举 `python.exe` 后按命令行分类。MCP-SVC / EDITOR 为基础设施，CPU≈0、idle，不计入挖掘产能。

### 挖掘作业（ACTIVE）

| 分类 | PID | 启动时间 | 线程 | 内存 | 账号 | 并发模型 | 状态 |
|---|---|---|---|---|---|---|---|
| SCAN | **45780** | 07-24 20:10 | 2 | 23.3 MB | 主 `mthyzx@126.com` | multi-sim `BATCH_SIZE=8` + 冷却 45s | 运行中（V43） |
| OTHER（已停） | ~~17988~~ | 07-24 21:45 | 5 | 36.8 MB | 教程 `mthyzx@gmail.com` | ThreadPool `CONCURRENCY=3` | **已终止** |
| OTHER（已停） | ~~7408~~ | 07-24 21:46 | 5 | 37.1 MB | 教程 `mthyzx@gmail.com` | ThreadPool `CONCURRENCY=3` | **已终止** |

> **CPU 占用**：V43 进程 `UserModeTime≈5.6s / 运行 97min` ≈ 0.1% → 纯 I/O 等待型（等 WQ 网络 + 批间冷却），本机算力非瓶颈。

### 基础设施（IDLE，忽略）

- **MCP-SVC**（cnhkmcp `platform_functions.py`）：约 10 进程，父 28060/52532/54120/44476/38560/38288/36532，子进程各 24 线程，CPU≈0。
- **EDITOR**（Cursor jedi language server）：4 进程（26396/29284/3720/19140/28024），idle。

---

## 三、各挖掘任务详情

### 3.1 V43 event_relation（SCAN，PID 45780）

| 维度 | 值 |
|---|---|
| 数据集 | `event_relation`（USA D1，覆盖率≈0.89，**未点亮金字塔**） |
| 信号风格 | 文本事件关系强度/类型（异于 insider/舆情/盈利风险），`ops<6`，禁 add/multiply/trade_when |
| 并发 | multi-sim，1 次 POST 提交 8 条 list → 平台 1 槽位并行 8 子任务；批间冷却 45s |
| 变体空间 | 7 字段 × 3 universe × 4 decay × 3 neut × 6 模板 + 3 配对 × 3 × 4 × 3 × 3 模板 ≈ 2484，脚本按优先级截断至 **200** |
| 闸门 | `GATE_SHARPE=1.58`、`GATE_FITNESS=1.0`（与生产闸门一致） |
| 进度 | **120 / 200（60%）**，errors=0，pass_cheap=0，**候选=0**，found=0 |
| 最佳 Sharpe | **0.35**（来自 `z_rs_score_general_ILLIQUID_MINVOL1M_d8_SUB`）；近 20 步（step 100–120）Sharpe 普遍 **−0.1 ~ −0.5**，全 FAIL |
| 吞吐 | 120 / 92.7 min ≈ **77.6 α/hr**（略低于 86.1 基准，因 event_relation 数据集更重、回测更慢） |
| ETA | 日志末次 ≈ 22:45（按 avg 46.3 s/step） |
| 提交策略 | **NO_SUBMIT**（仅标 READY_MANUAL） |

**趋势判断**：60% 进度 0 候选、近期批量 Sharpe 全面转负，且 `GATE_SHARPE=1.58` 对该弱信号明显过高 → **强烈趋向另一个死胡同方向**。建议 step 150 前若仍无 pass_cheap 即提前 cut。

### 3.2 tabbit_option9（OTHER，教程账号，已停）

| 维度 | 值 |
|---|---|
| 数据集 | `option9`（Options Analytics） |
| 并发 | ThreadPool `CONCURRENCY=3`（教程账号无 multi-sim 权限，3 为硬上限），独立凭据 `brain.txt` |
| CSV（resume） | 311 行：309 done / 1 timeout / 1 failed，309 alpha_ids，末次写入 21:47:11 |
| 历史闸门筛查 | 0/92 候选；100% 触发 `LOW_SHARPE`(≥1.25) 与 `LOW_FITNESS`(≥1.0)；max Sharpe=1.21（差 0.04）、max Fitness=0.53（差近半） |
| 结论 | option9 模板家族 **Fitness 结构性过低**，与生产 scan_v* 同属信号质量死结 |

> **本轮回异常（已处置）**：21:45–21:46 出现 **两个独立 tabbit 实例**（PID 17988 父 42496、PID 7408 父 51456，不同父进程=两次独立启动，间隔 22s），同时向同一 resume CSV 追加。风险：① CSV 写交叉 → 损坏/行丢失；② 两进程读同一「已完成」集合并重复提交相同表达式 → gmail 账号配额浪费 + 重复 alpha。此状态与用户「tabbit 已确认 0/293 死结建议先停」决策冲突。已执行 `Stop-Process` 终止两实例，复检 `remaining tabbit procs: 0`。

---

## 四、本轮回测效率结论（越详细越好）

### 4.1 各任务是否跑在最大并发档

- **V43（主账号）**：multi-sim `BATCH=8` + 45s 冷却，是该账号/脚本设计的**最优并发档**（基准 `_bench_v34_sim_speed`：multi(8)=86.1 α/hr vs 逐条=54.3 α/hr，speedup **1.59×**）。实测 77.6/hr 因数据集更重略低于基准，但并发模型本身未退化。
- **tabbit（教程账号）**：`CONCURRENCY=3` 是教程账号硬上限（无 multi-sim）。单实例已打满；本轮回出现 2 实例 = 6 路并行，但**覆盖同一字段集**，属重复而非增量。

### 4.2 平台整体并发利用率

- 主账号：1 个 multi-sim 作业（8 子任务并行，占 1 槽）。
- 教程账号（停前）：2 实例 × 3 = 6 路单模拟并行。
- 两账号独立额度 → 峰值约 **14 路并发模拟**，优于单作业。但 tabbit 第 2 实例不增加新覆盖，纯属浪费。

### 4.3 是否达平台绝对上限

- **不能称「已达平台绝对上限」**：① `BATCH>8` 从未做基准测试；② 历史上长期仅 1 个作业在跑，槽位大量闲置。8 仅证明「显著优于逐条」(1.59×)，非平台极值。

### 4.4 核心论断（固定结论）

> **V31–V43 生产 + tabbit 教程，累计 ≈ 2000+ alpha，仅 V39b 上线 1 条。瓶颈是信号发现，不是吞吐。** 在出候选之前，加并发 / 多开作业只是加速「挖出 0 候选」。

### 4.5 可行动建议

1. **维持 tabbit 停止**（已执行）；除非用户明确要对其做最终筛查收割，否则不再拉起。
2. **V43 提前 cut**：step 150 前若无 pass_cheap，终止以省主账号配额。
3. **范式转向（最高优先级）**：见第五节，用 V39b 锚点起草 V44。

---

## 五、范式转向锚点（V39b 已提取，供 V44 设计）

通过主账号 API 实时拉取已上线 alpha `YPgAa3WR` 完整定义：

| 项 | 值 |
|---|---|
| **表达式** | `rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))` |
| 数据集 | `eur_top_value_2`（**未点亮金字塔** value 家族） |
| 设置 | USA / TOP3000 / EQUITY，delay=1，decay=3，**neutralization=SECTOR**，truncation=**0.01**，pasteurization=ON，testPeriod=P6Y，FASTEXPR |
| IS 指标 | Sharpe **2.08**，Fitness **1.67**，turnover 0.106，returns 0.081，drawdown 0.048 |
| 自相关 | **selfCorrelation=0.20**（关键：低自相关使其过 PC 闸门），prodCorrelation=0.53 |
| 闸门 | LOW_SHARPE PASS(2.08≥1.58)、CLUSTER_TEST PASS … |

**制胜配方拆解**：
1. **数据源**：未点亮金字塔的 value 类数据集（`eur_top_value_*`）。
2. **变换链**：`ts_backfill(field, 66)` → `ts_zscore(189)` → `group_zscore(by industry)` → `rank`。
3. **中性化**：SECTOR（组内 z-score 进一步压低自相关）。
4. **严苛截断**：truncation=0.01（比 V43 的 0.08 紧得多）。
5. **参数**：decay=3、delay=1、TOP3000、P6Y。

**V44 草案方向**（待实施，未拉起）：
- 以同一变换链为模板，遍历 value/未点亮金字塔家族字段（种子：`eur_top_value_1/2/3/4`、`eur_aggregated_value_1..4` 等，实施前先经 API 列出该家族全量字段核对）。
- 参数网格：`backfill∈{22,66,126}` × `ts_zscore∈{126,189,252}` × `group∈{industry,sector,subindustry}` × `{rank, -rank}`。
- 复用 V43 的 `WqApiSimple + multi_sim` 框架、`BATCH_SIZE=8`、checkpoint 续跑（用户硬要求）、`GATE_SHARPE=1.58/GATE_FITNESS=1.0`、`TARGET_ALPHAS` 控制、`NO_SUBMIT`（人工确认后提交）。
- 目标：复现「低自相关 + 行业中性 + 未点亮金字塔 value」这一已验证可过闸门的信号结构。

---

## 六、建议与下一步

1. ✅ **tabbit 双实例已停**（遵循「先停」决策，消除 CSV 损坏/重复提交风险）。
2. ⚠️ **V43 建议 step 150 前提前 cut**（趋势为死胡同）。
3. 🚀 **范式转向优先级最高**：用第五节 V39b 锚点起草并实施 `scan_v44_*`，聚焦未点亮金字塔 value 家族 + 低自相关组内 z-score 结构。
4. 📋 维持「盯回测必做 Python 角度分析 + 详细效率结论」框架（已固化至 `~/.workbuddy/MEMORY.md`）。

---
*附：本报告为自动化每小时汇报的本次执行；tabbit 进程终止为本轮回显式处置动作，非脚本自动行为。*
