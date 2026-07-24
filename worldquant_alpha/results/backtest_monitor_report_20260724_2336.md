# 回测监控报告 — 2026-07-24 23:36 (GMT+8)

> 用户手动发起（V33 HKG PPA 进度汇报框架）｜框架：进程盘点 → 并发模型 → 效率结论 → ETA 分析

## 一、进程盘点（Python 全量枚举 + 分类）

| 类别 | PID | 任务 | 进度 | 状态 |
|---|---|---|---|---|
| 基础设施 | 19 个 | Cursor LSP / MCP-SVC / EDITOR 等 | — | idle，非挖掘 |
| ~~WQ 挖掘~~ | 45780 | `scan_v43_event_relation.py` | 200/200 (100%) | **已结束（22:52:25）** |
| ~~WQ 挖掘~~ | 19996 | `tabbit_option9.py` | CSV 434 done | **已停止（~23:01:07 末次写入）** |

- 全量 `python.exe` 共 **19** 个（较 22:49 的 23 减少 4：V43 + tabbit 两进程均已退出）。**当前无任何活跃 WQ 挖掘任务。**
- `tasklist` 过滤 `45780|19996|scan_v4|scan_v3|tabbit` → 无匹配；确认 V43 与 tabbit 进程均已退出，且无 V44 等任何新扫描任务拉起。
- V43 检查点 `v43_event_rel_checkpoint.json` 末态写入 `22:52:25`；日志含 `finish` 事件，末条 `done=200 @ 22:52:25`。
- tabbit CSV 末次落盘 `23:01:07`，之后无新写入、进程退出。

## 二、并发模型（末态复盘）

| 任务 | 并发模型 | 批次/并发 | 实测吞吐 | 账号 | 末态 |
|---|---|---|---|---|---|
| V43 | multi-sim BATCH=8 + 45s 冷却 | 8 | 最终 200/ (约 2h42m) ≈ **74 α/hr**（avg 48.51 s/step） | 主账号 | 完成，主账号释放 |
| tabbit | ThreadPool CONCURRENCY=3 | 3 | ≈110 α/hr | 教程账号 | 停止，教程账号释放 |

- 两任务历史上分属独立账号，叠加 ~11 路并行；现已全部退出，两账号槽位均空闲。
- V43 BATCH=8 即基准最优档（multi(8)=86.1 α/hr）；实测 74 α/hr 略低于基准，因 event_relation 数据集更重。

## 三、效率结论

1. **吞吐已达各自模型设计最优区**：V43=8/批 multi-sim、tabbit=3 单模拟均为对应账号/配置上限档；并发调优无边际收益。
2. **绝对瓶颈仍是信号发现**：V31–V43 + tabbit 累计 ≈2000+ alpha，仅 V39b（YPgAa3WR）1 条通过全部门槛并提交。V43 末态最佳 Sharpe **0.47**（≪ 1.25 闸门），**0 候选**；tabbit 434 done **0 候选**（option9 模板家族 Fitness 结构性过低）。两任务均以「零候选」收场，再次印证信号质量死结。
3. **当前系统处于"双账号全空闲"状态**：这是启动范式转向（V44）的**最佳窗口**——无竞争、无槽位占用、无 CSV 冲突风险。

## 四、ETA 分析（必填）

### V43 event_relation（PID 45780，已结束）
- **完成/总数**：200 / 200（100%）✅
- **已运行**：约 2h42m（自 20:10 至 22:52:25）
- **剩余**：0
- **吞吐**：74 α/hr（avg 48.51 s/step）
- **墙钟 ETA**：**已收尾（22:52:25），无需 ETA**。
- **后处理阶段**：`NO_SUBMIT=True` + 0 候选 → 无后处理，结束后主账号槽位立即释放。
- **置信度**：任务已结束，确定性 100%。
- **结论**：自然完成，event_relation 方向零候选，死胡同确认。

### tabbit_option9（PID 19996，已停止）
- **完成**：CSV 434 done（435 行含表头），末次写入 23:01:07 后进程退出。
- **吞吐**：≈110 α/hr（22:24→23:01 间 +20 done/约 37min 放缓，或末段 field-sweep 收尾）。
- **ETA**：**进程已退出，无 ETA**（非活跃任务）。
- **候选**：0/434。
- **置信度**：任务已停止，确定性 100%。
- **结论**：option9 模板家族同样零候选收场；教程账号槽位释放。

### 全局活跃度
- **当前无活跃 WQ 挖掘任务**（19 个 python 进程全为基础设施）。
- 主账号（mthyzx@126.com）+ 教程账号（mthyzx@gmail.com）**槽位均空闲** → **V44 启动窗口完全打开（置信度：高，无竞争）**。

## 五、综合建议（待用户决策）

1. **🚀 范式转向窗口已完全打开——立即拉起 V44**：两账号均空闲、无竞争、无 CSV 冲突。用 V39b 锚点起草 `scan_v44_*`（未点亮金字塔 value 家族 `eur_top_value_*` + 低自相关 `group_zscore(ts_zscore(ts_backfill(...)))` 结构；保留 checkpoint 续跑 + `NO_SUBMIT` 人工确认）。
   - V39b 锚点：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2,66),189),industry))`，USA/TOP3000/SECTOR/decay3/trunc0.01/P6Y，IS Sharpe 2.08 / Fitness 1.67 / selfCorr 0.20（已回填 IS 明细）。
2. **tabbit 处置**：已自然停止（434 done，0 候选）。如需继续收割 option9 字段可重启，否则保持停止（符合此前「先停」决策）。
3. **V33 HKG**：自 07-23 14:20 暂停，未动。

---
*数据源：V43 `results/v43_event_rel_checkpoint.json` + `v43_event_rel_progress_20260724_201042.log`；tabbit `results/tabbit_option9_results.csv`；`tasklist` 进程枚举。*
