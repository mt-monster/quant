> **本报告为「统一标准报告模板」的套用示范**：数据完全取自 `factor_mining_report_20260726_1838.md`（快照 2026-07-26 18:38 GMT+8），仅按 `standard_backtest_report_template.md` 四层骨架（背景概述 → 分析维度 → 核心发现 → 结论与建议）重新组织，未改动任何原始数字口径。
> **数据源**：`results/*_checkpoint.json`(权威) + `*_progress_*.log`(实时) + `tri_track_undug_results.csv` + 机器级进程枚举。

---

# 第一部分 · 背景概述（Background & Scope）

## 1.1 报告目的与触发场景
- **触发**：用户请求"拉取最新报告"（盯回测 / 盘点挖掘任务）。
- **核心结论预告**：全部 **44** 个候选中仅 **1 个**（`YPgAa3WR`，ACTIVE，07-24）真提交；**43 个**卡平台生产仿真(OOS)硬闸门，均**不可提交**。`PASS_CHEAP` 仅本地廉价 IS 闸通过，≠ 可提交。

## 1.2 监控范围与边界
- 本报告为**单账号视角**（主账号 `worldquant_alpha/results/` + 独立账号 `tri_track`）；多账号合并版见 `global_overview` 报告（§3.3 注）。
- 纳入：ds 舰队 7 路在飞 + v52b（已完成）+ tri_track(ML88164) + scan_rescue。
- 旁路未计入主账号 total_N：continuous_undug / green_guard / analyze_tabbit（见 D8）。

## 1.3 口径与定义（统一复述）
| 术语 | 定义 | 易错点 |
|---|---|---|
| 研究回测总量 | `results/*_checkpoint.json` 的 `results[]` 条数合计 | 13,779（32 个 checkpoint） |
| PASS_CHEAP / CHECK_PENDING | 仅研究仿真 IS 廉价闸门通过 | **≠ 可提交** |
| found_alphas | 跨过生产相关性验证（有 prod_corr 字段）者 | 全局仅 1（YPgAa3WR, 0.5325） |
| ACTIVE | 已真实提交至平台 | 唯一确证"上线" |
| 候选池 | 有 IS 指标、待 OOS 验证者 | 44 个 |

## 1.4 方法论铁律（发现入口）
- 第一视角 = 机器级全量 Python 进程枚举（`Get-CimInstance Win32_Process`）；日志/v 命名仅作 scan 脚本明细补充。
- 理由：非标准命名真实挖掘任务（continuous_undug / tri_track / analyze_tabbit）会被 `scan_v*` 过滤漏报。

---

# 第二部分 · 分析维度（Dimensions）

## D1 维度一 · 进程全景盘点（发现入口）
按命令行正则分类，机器级枚举确认：

| 分类 | 进程/脚本 | 账号域 | 进程数 | 角色 | 挖 alpha? |
|---|---|---|---|---|---|
| SCAN | ds 舰队 7 路 (`ds_*_tri_*`) | 主账号 | 7 | 7 数据集在飞 | ✅ |
| SCAN | `scan_rescue_r3_web_lift.py` | 主账号 | 1 | web_traffic 救援 | ✅ |
| MINING | `tri_track_undug.py` | ML88164 独立 | 2 | 三轨挖掘（explore/improve/misc） | ✅ |
| MINING | `continuous_undug.py` | ML88164 独立 | 2 | 连续未挖数据集调度器 | ✅ |
| MINING | `analyze_tabbit_parallel.py` | 独立 | 2 | 汇总+验证(`/check`) | ✅ |
| WATCHDOG | `green_guard.py` | 独立 | 2 | GREEN 守卫（非挖矿，检查器） | ❌ |
| WATCHDOG | `fleet_keeper.py` | 主账号 | 1 | ds 舰队守护+救援 | ❌ |

> ⚠️ **盲点暴露**：报告§1 标"在飞 15"，但机器枚举证实仅 **7 路 ds 进程实时运行**，其余 ds 未完成任务无活动进程（待 fleet_keeper 续补）；独立账号 continuous_undug/green_guard/analyze_tabbit 旁路在飞未计入主账号计数。

## D2 维度二 · 逐任务并发模型与进度
**并发配置对比（ds 舰队 vs tri_track）**：

| 维度 | 🚢 ds 舰队 (主账号) | 🛡️ tri_track (独立) |
|---|---|---|
| 账号 | mthyzx@126.com | ML88164 |
| 并发模型 | submit_gate + multi-sim(BATCH=8) | CONCURRENCY=3 三轨 |
| 在飞任务 | 7 路 dataset | 1 进程(8 分片) |
| 总任务量 | 7×320=2,240 | 8×10=80 |
| 结果落盘 | `results/ds_*_checkpoint.json` | `tri_track_undug_results.csv` |

**ds 舰队实时进度（7 路在飞，节选关键）**：

| 数据集 | 进度 | 首步最佳S | 候选 |
|---|---|---|---|
| equity_forum_data | 312/320 (97.5%) | 🟡 1.26 | 🔴 0 |
| finnews_nlp_scores | 296/320 (92.5%) | 🟡 1.11 | 🔴 0 |
| forum_sentiment | 264/320 (82.5%) | 🟡 1.43 | 🔴 0 |
| ai_news_scores | 280/320 (87.5%) | 🔴 0.77 | 🔴 0 |
| chart_cnn_alpha | 8/320 (2.5%) | 🔴 0.00 | 🔴 0 |
| fundamental65 | 40/320 (12.5%) | 🔴 0.00 | 🔴 0 |
| multi_horizon_alpha | 24/320 (7.5%) | 🔴 0.00 | 🔴 0 |

> 19 路 ds 数据集已 100% 完成（含 dl_riskfree_returns S=2.33、web_traffic_engage S=2.27），但 **0 候选**；7 路在飞首步 Sharpe 普遍贴底（🔴），直观体现信号发现瓶颈。

**tri_track 进度**：84 alpha 已提交（submitted=84/failed=0），分片 4/8、5/8 已完成，其余在飞；最佳 S=1.59。

## D3 维度三 · 回测效率分析
- **吞吐实测**：ds 舰队表列 α/hr 为 done/elapsed 粗估上限（多数在飞任务运行时长计 0 → 显示 ~0 α/hr）；稳态基准下 **7 路真实可持续约 603 α/hr**。
- **基准对比**：`bench_v34_sim_speed` 测得多-sim(BATCH=8)=86.1 α/hr vs 单模拟=54.3 α/hr，speedup 1.59×（来自方法论 skill）。
- **并发利用率**：全局 429=0（多进程错峰 + submit_gate，令牌零浪费）；独立账号令牌与主账号互不干扰。
- **瓶颈定调**：当前真正瓶颈 = **信号发现不是吞吐**（并发批次首步 Sharpe 远低于闸门，加并发=加速挖 0 候选）。

## D4 维度四 · 候选产能与质量漏斗
```
研究仿真回测               13,779  (100%)
  → IS 廉价闸门通过         44      (0.3%)   ← 40 PASS_CHEAP + 4 CHECK_PENDING
    → 跨生产相关性验证       1      (0.0%)   ← YPgAa3WR, prod_corr=0.5325
      → 平台真实提交         1      (0.0%)   ← YPgAa3WR, ACTIVE, 07-24
```
> ⚠️ **修正原报告矛盾**：原报告漏斗末行写"平台真实提交 0"，与核心结论表"平台真实提交 1（YPgAa3WR, ACTIVE）"自相矛盾。按模板诚实性规范（总数≠分项之和须核验）修正为 **1**。每一级都是硬闸门：IS 闸筛掉 99.7%，生产相关性关仅 1 个通过。**44 个候选 ≠ 可提交**。

## D5 维度五 · 提交就绪四关审计（核心质量门）
| 关 | 内容 | 本链现状 | 取证 |
|---|---|---|---|
| ① 研究仿真 IS | S>1.58/F>1.0/TVR∈[0.05,0.30]/M>10bp/Ret>0.05 | ✅ 44 候选过 | checkpoint `results[].status` |
| ② 生产仿真 OOS | 样本外稳健 | ❌ 0 跑过 | 平台侧未触发 |
| ③ 生产相关性 | PROD+SELF_CORRELATION<0.7 | ✅ 仅 1（YPgAa3WR） | `found_alphas[]` prod_corr |
| ④ submittable+submit | 平台判定+真实落平台 | ✅ 仅 1（YPgAa3WR） | status=ACTIVE |

- **三级分类**（详见 §3.4）：✅ 已提交 1 / ✅ 回测完成待提交 0 / 🔶 仍需验证 43。
- **红线**：绝不称 PASS_CHEAP 为"可提交"；CHECK_PENDING（4 个 v52_tri_hiring_trends）仅"平台产验中"，≈ 1/2 路程。

## D6 维度六 · 在飞任务 ETA（强制章节）
| 任务 | 当前进度 | 预期完成 | 置信度 |
|---|---|---|---|
| 🚢 equity_forum_data | 312/320 (97.5%) | **?** | 低（进度日志 done 计 0） |
| 🚢 finnews_nlp_scores | 296/320 (92.5%) | **?** | 低 |
| 🚢 forum_sentiment | 264/320 (82.5%) | **?** | 低 |
| 🚢 ai_news_scores | 280/320 (87.5%) | **?** | 低 |
| 🚢 chart_cnn_alpha | 8/320 (2.5%) | **?** | 低 |
| 🚢 fundamental65 | 40/320 (12.5%) | **?** | 低 |
| 🚢 multi_horizon_alpha | 24/320 (7.5%) | **?** | 低 |
| 🛡️ tri_track_undug | 84 alpha | **07-27 23:49** | 中（分片推算） |
| ✅ v52b_hiring_margin | 160/160 (100%) | **已完成 (23:29)** | 已完成 |

> ds 舰队进度日志 `done` 字段计 0 导致 ETA 不可算，统一标 **?**；建议补进度日志（与 v52b 同样问题，已修复 v52b 但 ds 舰队日志仍缺 done）。

## D7 维度七 · 失败闸门与风险归因
| 失败类型 | 次数 | 占比 | 归因 |
|---|---:|---:|---|
| F(拟合) | 10,954 | 21.9% | IS 指标闸 |
| S(夏普) | 10,788 | 21.5% | IS 指标闸 |
| M(换手收益) | 10,758 | 21.5% | IS 指标闸 |
| Ret(收益) | 10,339 | 20.6% | IS 指标闸 |
| TVR(换手率) | 5,110 | 10.2% | IS 指标闸 |
| submit_failed | 1,816 | 3.6% | 研究仿真本地拒（非平台 429） |
| PF:子宇宙Sharpe | 304 | 0.6% | **头号平台失败闸门**（PF:LOW_SUB_UNIVERSE_SHARPE 219 次） |

> **结构性结论**：IS 指标失败（S/F/M/Ret）合计 47,839 次占主体，但 **PF:子宇宙 Sharpe 是头号平台级硬闸门**——印证"在子宇宙层面优化中性化/约束"才是攻坚方向；V39b(2.58)/V39(2.30) 均卡此处（属工程可调，非信号方向无解）。

## D8 [贯穿] 监控盲点扫描（防漏报）
逐类排查（对应模板五类盲点）：
1. **硬编码任务列表**：旧 gen_report.py 漏 ds 舰队、误判 tri_track → 已改用 build_md_report.py 自动发现。✅ 已闭合
2. **服务端任务无本地日志**：WQ-BRAIN 服务端仿真任务本机零日志 → 须到控制台查。⚠️ 本机不触发
3. **账号维度盲区**：continuous_undug/green_guard/analyze_tabbit（独立账号）数据在 BaiduNetdisk WQ 目录，未并入主账号。⚠️ 由本数组补充（见 D1）
4. **只写 checkpoint 不写进度日志**：v52b 已补；ds 舰队进度日志 `done` 仍计 0。🔶 部分闭合
5. **非 scan_v 命名真实挖掘**：continuous_undug / tri_track / analyze_tabbit 已人工改判单列。✅ 已闭合

---

# 第三部分 · 核心发现（Core Findings）

## 3.1 核心指标汇总表（结论先行的数据版）
| 指标 | 数值 | 环比(18:36) |
|---|---|---|
| 累计回测次数 | **13,779** | +8 |
| IS 廉价闸门通过 | **44** (40+4) | +1 |
| 跨生产相关性验证 | **1** | — |
| 平台真实提交 | **1** | — |
| 全链路最佳 Sharpe | **2.66** (v52b 降换手) | — |
| 在飞挖掘任务 | **15** (ds 7 实时 + 旁路) | — |
| 全局 429 | **0** | — |

## 3.2 逐维度发现摘要
- **D1 进程盘点**：挖掘舰队结构稳定，7 路 ds 实时 + 独立账号旁路在飞；"在飞 15"含无活动进程项。
- **D2 并发进度**：ds 舰队 19 路完成、7 路在飞，全部 0 候选；tri_track 84 已提交无 IS 指标。
- **D3 效率**：吞吐达标、429=0；瓶颈是信号发现非吞吐。
- **D4 漏斗**：13,779 → 44 → 1 → 1，每一级硬闸门损耗极大。
- **D5 四关审计**：仅 YPgAa3WR 走完四关；43 候选卡 OOS。
- **D6 ETA**：ds 舰队因日志 done=0 不可算；tri_track 07-27 23:49。
- **D7 失败归因**：PF 子宇宙 Sharpe 为头号平台硬闸门。
- **D8 盲点**：独立账号未并入主账号计数，报告以 D1/D8 表格补充。

## 3.3 全局合并视图（多账号场景占位）
- 本报告为单账号视角。多账号合并（主账号 + tri_track + tabbit + continuous_undug + green_guard + scan_rescue）见 `global_overview_20260726_1854.md`：全局研究回测 13,851、全局 alpha 创建记录 14,216、全局确证 ACTIVE 仍仅 1。
- **口径诚实标注**：研究回测 vs 提交记录两口径不可相加；scan_rescue 已计入主账号不重复加。

## 3.4 逐项候选核查表（三级分类，强制）
**三级分类汇总**：
| 分类 | 数量 | 说明 |
|---|---|---|
| ✅ 已正式提交 | **1** | `YPgAa3WR` (ACTIVE, 07-24, prod_corr=0.5325) |
| ✅ 回测完成待提交 | **0** | 其余均缺 OOS 硬闸门 |
| 🔶 仍需验证 | **43** | 缺生产仿真(OOS)+submittable+submit |

**✅ 已正式提交 (1)**：
| pid | 任务 | S | 验证链 | 提交时间 |
|---|---|---:|---|---|
| **YPgAa3WR** | v39b_sub_micro | 2.08 | IS✅ 产验(0.5325)✅ 风险中性✅ 稳健性✅ | 2026-07-24 |

**🔶 仍需验证 (43)** — 取前 12 行示例（全量 43 行见原报告第八章）：
| pid | 任务 | S | 状态 | 卡点 |
|---|---|---:|---|---|
| j2rrpVzO | v52_tri_hiring_trends | 2.19 | 平台产验中 | 等产验+OOS+submit |
| j2rgVd0E | v39b_sub_micro | 2.18 | 仅IS闸 | OOS+产验+submittable+submit |
| zqRkPVbX | v52b_hiring_margin | 2.33 | 仅IS闸 | OOS+产验+submittable+submit |
| 1YzwaMZz | v52b_hiring_margin | 2.32 | 仅IS闸 | OOS+产验+submittable+submit |
| RR17rbe0 | v52b_hiring_margin | 2.33 | 仅IS闸 | OOS+产验+submittable+submit |
| zqRWAJmX | v39b_sub_micro | 2.17 | 仅IS闸 | OOS+产验+submittable+submit |
| N1RO8rLL | v39b_sub_micro | 2.13 | 仅IS闸 | OOS+产验+submittable+submit |
| np8Wr2ml | v39b_sub_micro | 2.12 | 仅IS闸 | OOS+产验+submittable+submit |
| le30awQe | v39b_sub_micro | 2.07 | 仅IS闸 | OOS+产验+submittable+submit |
| e7xQoWZM | rescue_r3_web_lift | 1.74 | 仅IS闸 | OOS+产验+submittable+submit |
| 1YzZvLKm | rescue_r3_web_lift | 1.74 | 仅IS闸 | OOS+产验+submittable+submit |
| RR11Gzbd | v52_tri_hiring_trends | 1.63 | 平台产验中 | 等产验+OOS+submit |

> 候选来自 2 根集群：**v52b**（`aggregate_open_positions_count` 降换手，S 1.79–2.66）与 **v39b**（`eur_top_value_2` insider micro，S 1.67–2.58）。均仅研究仿真 IS 闸通过。

---

# 第四部分 · 结论与建议（Conclusions & Recommendations）

## 4.1 结论先行（Executive Summary）
1. 全局仍仅 **1 个 alpha（`YPgAa3WR`）确证上线**（ACTIVE, 07-24）；44 候选中 43 个卡 OOS 硬闸门，**均不可提交**。
2. **信号发现是瓶颈，非吞吐**：ds 舰队 19 路完成 + 7 路在飞、v52b 160 变体全跑完，合计 0→28 PASS_CHEAP 但 found_alphas=0；加并发=加速挖 0 候选。
3. **PF:子宇宙 Sharpe 是头号平台硬闸门**（304 次，V39b/V39 均卡此处），属工程可调方向。
4. 报告"在飞 15"含无活动进程项；独立账号旁路（continuous_undug/green_guard/analyze_tabbit）未并入主账号计数，实际全局挖矿量更大。

## 4.2 问题说明
1. 候选提交率 **1/44**，43 个缺 OOS 硬闸门。
2. ds 舰队首步信号偏弱、7 路 0 候选。
3. 子宇宙 Sharpe 闸门比 IS 闸更硬（PF:LOW_SUB_UNIVERSE_SHARPE）。
4. tri_track 独立账号 CSV 仅记提交状态，无 Sharpe/Fitness，无法与主账号比信号质量。
5. 监控盲区虽已用机器级枚举补，但 continuous_undug/green_guard/analyze_tabbit 仍不计入主账号 total_N。
6. 吞吐数字勿误读：ds 表 α/hr 为 done/elapsed 粗估上限，稳态约 603 α/hr。

## 4.3 行动建议（优先级排序）
1. **ds 舰队继续跑完**（合规零 429，自然推进）。
2. **主攻子宇宙 Sharpe 闸门**：对 V39/V39b 限 universe=TOP3000 / 调 neutralization。
3. **v52b 升维**：降换手变体（decay4 SECTOR）已过廉价 IS 闸，规模化过 M 闸。
4. **并发纪律**：允许错峰多进程(>6) 并发，需自带 gate + 禁 <2s 齐射。
5. **提交核查路线（按优先级）**：YPgAa3WR → 4 个 CHECK_PENDING 等平台结果 → 40 个 PASS_CHEAP 排队。对 YPgAa3WR：跑 OOS → /check → submittable → submit(关 no_submit)，走通后批量复制。
6. **监控 CHECK_PENDING 结果**：4 个 v52_tri_hiring_trends 在平台自动产验中，返回后立即评估 prod_corr/self_corr。
7. **tri_track 脚本升级**：改输出 checkpoint 格式（含 Sharpe/Fitness/失败闸门），纳入统一监控。

## 4.4 风险与未决项
- 🔶 **CHECK_PENDING 4 个**（v52_tri_hiring_trends）结果未回，prod_corr 未知，优先级待定。
- 🔶 **ds 舰队 ETA 不可算**（进度日志 done=0），无法承诺完成时间。
- 🔶 **独立账号未并入主账号计数**：total_N=13,779 低估真实全局挖矿量。
- ⚠️ **额度风险**：当前 429=0，但批量提交 OOS/submit 时若同账号齐射仍可能触发（须 submit_gate 限速）。

---

*本报告为 `standard_backtest_report_template.md` 套用示范，数据快照 2026-07-26 18:38 GMT+8，全部数字来自文件实测、未编造。修正了原报告漏斗"平台真实提交 0/1"内部矛盾（按模板诚实性规范定为 1）。*
