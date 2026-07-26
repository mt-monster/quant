> **数据快照**: 2026-07-26 18:54 GMT+8 ｜ **合并口径说明**: 主账号/scan_rescue 记录全部研究回测(含失败)；tri_track/tabbit/continuous_undug 仅记成功获 alpha_id 的提交，其真实回测总量 > 提交日志。下游平台 ACTIVE 状态除 YPgAa3WR 外均未逐个核实。

> ⚠️ **最重要结论**：全部账号合并后，**仅 1 个 alpha 确证已真正提交并上线**（`YPgAa3WR`，主账号，ACTIVE，07-24）。其余候选/提交均卡在平台生产仿真(OOS)硬闸门或未核实。

---
## 一、各账号总览（分列）

| 账号 | 挖矿模型 | 计数口径 | 回测/提交数 | 候选(过IS闸) | 确证ACTIVE | 在飞进程 |
|---|---|---|---|---|---|---|
| 🚢 主账号 worldquant_alpha (mthyzx@126.com) | 研究仿真闸门 | 研究回测(含失败) | **13,851** | 44 (40 cheap+4 pending+0 pass) | 1 (YPgAa3WR) | 7 ds + scan_rescue |
| 🛡️ tri_track (ML88164) | 全量提交 | 提交日志 | **1,911** (累计) / 84 (当前轮) | —(无IS指标存档) | 未核实 | 2 |
| 🟠 analyze_tabbit (tabbit) | 全量提交 | 提交日志 | **758** | — | 未核实 | 2 |
| 🔵 continuous_undug (ML88164) | 连续调度 | 调度分块 | 5 块完成(计划9数据集) | — | 未核实 | 2 |
| 🟢 green_guard (独立) | /check 绿标核查 | 检查器 | 0 (非挖矿) | — | — | 2 |
| 🔧 scan_rescue (主账号子任务) | web_traffic 救援 | 研究回测 | 64 (当前轮) | 2 PASS_CHEAP | 0 found | 1 |
> 注：scan_rescue 写入 `results/`，其 64 次回测与 2 PASS_CHEAP 已计入上方「主账号」总量（主账号 = ds舰队 + v52b + scan_rescue 全部 results/ checkpoint），本行仅作任务级单列，合并口径不重复相加。

**tri_track 轨道分布**：explore=1014，improve=481，misc=416（累计 1911 条，日期 2026-07-25 11:58:04 ~ 2026-07-26 18:52:58）。

**tabbit 各数据集结果**：news18=221，option9=434，pv1=2，socialmedia8=101（合计 758 条提交记录）。

---
## 二、全局合并指标（诚实标注口径）

| 合并指标 | 数值 | 口径说明 |
|---|---|---|
| 全局研究回测(精确) | **13,851** | 主账号 13,851（已含 ds舰队/v52b/scan_rescue；其余账号不记失败回测，真实回测 > 其提交日志） |
| 全局平台 alpha 创建记录 | **14,216** | 各账号获 alpha_id 的提交日志合计 = 主账号 11547 + tri_track 1,911 + tabbit 758（scan_rescue 已计入主账号 11547） |
| 全局确证 ACTIVE(已上线) | **1** | 仅 `YPgAa3WR`（主账号，07-24 提交，平台 ACTIVE） |
| 全局候选池(待OOS验证) | **44** | 主账号 44（已含 scan_rescue 2 PASS_CHEAP），有IS指标、需跑生产仿真→/check→submit |
| 全局已推平台未核实 | **2,669** | tri_track 1,911 + tabbit 758（已获 alpha_id 推平台，但无IS指标存档，平台 ACTIVE/FAIL 状态需逐个 /check 核实） |
| 全链路最佳 Sharpe | **2.66** | 来自主账号 v52b 降换手变体 |

> ⚠️ **口径警示**：`全局研究回测` 与 `全局平台 alpha 创建记录` 是两个**不可直接相加**的口径——前者含失败回测，后者仅含成功获 id 的提交。此处分列仅为呈现活动规模，切勿误读为 `总挖矿量 = 两者之和`。

---
## 三、全局提交就绪漏斗

```
  研究仿真回测(主+scan_rescue)   ████  13,851
  获 alpha_id 提交记录(全局)      ██    14,216
  确证 ACTIVE(已上线)            █     1
```

每一级硬闸门：`研究仿真` 筛掉绝大多数(主账号 2,304 次失败)；`获 alpha_id` 后 `YPgAa3WR` 是全局唯一跨过生产相关性+风险中性+平台提交闸门者。tri_track/tabbit 的 2,669 条提交**未存IS指标**，无法判定是否真正过闸。

---
## 四、逐账号提交核查（三级分类）

| 分类 | 账号 / alpha | 说明 |
|---|---|---|
| ✅ 已提交(ACTIVE) | 主账号 `YPgAa3WR` | prod_corr=0.5325，07-24 上线，全局唯一 |
| 🟡 候选池·待OOS验证 | 主账号 44 候选（含 scan_rescue 2 PASS_CHEAP） | 需跑生产仿真→全量/check→submittable→submit(关 no_submit) |
| ❓ 已推平台·未核实 | tri_track 1,911 + tabbit 758 | 已获 alpha_id 推平台，无IS指标存档，需逐个 /check 确认状态 |
| ⏳ 调度中 | continuous_undug 5 块 / green_guard 核查中 | 持续产出，暂无落地 |

> 结论：**无任何账号的挖掘产出（除 YPgAa3WR 外）满足 WQ 完整提交四关**（研究IS→生产OOS→平台/check→显式submit）。主账号 44 候选（已含 scan_rescue 2 PASS_CHEAP）仍需生产仿真验证；tri_track/tabbit 的 2,669 条需回溯 IS 指标并 /check。

---
## 五、在飞任务与 ETA

| 任务 | 账号 | 状态 | 预期完成 | 置信度 |
|---|---|---|---|---|
| 🚢 ds 舰队 (7路实时) | 主账号 | 7 进程运行，多数数据集进度<100%无活动进程(待 fleet_keeper) | 见主报告 per-dataset ETA | 中(参考主报告) |
| 🛡️ tri_track_undug | ML88164 | 持续提交中 (累计 1,911, 当前轮 84) | 连续挖矿，无明确终点 | 低 |
| 🔵 continuous_undug | ML88164 | 调度中 (完成 5 块/计划9数据集) | 连续调度，无明确终点 | 低 |
| 🟠 analyze_tabbit | tabbit | 2 进程在飞 | 连续挖矿 | 低 |
| 🟢 green_guard | 独立 | 2 进程 /check 绿标核查 | 持续 | 低 |
| 🔧 scan_rescue | 主账号 | 64 回测完成, 2 PASS_CHEAP | 本轮近尾声 | 中 |

> 详细 per-dataset ETA 见主报告 `factor_mining_report_*.md`（ds 舰队章节）。本总览聚焦跨账号合并。

---
## 六、关键结论与下一步

1. **全局仅 1 个 alpha 真正上线**（YPgAa3WR），其余 0 个满足完整提交四关。
2. **主账号是信号发现主战场**：13,851 次研究回测产 44 候选，但 0 found_alphas（全卡生产相关性/风险中性）。
3. **tri_track/tabbit 重「量」不重「质」**：2,669 条提交但无IS指标存档，需回溯验证才有意义。
4. **continuous_undug 是补充调度**：覆盖主账号未挖数据集，当前 5 块完成。
5. **下一步优先级**：① 对主账号 44 候选跑生产仿真→/check→submit（走通 YPgAa3WR 全流程复制）；② 回溯 tri_track/tabbit 的 2,669 条提交做 /check 状态核实；③ 统一 checkpoint 目录消除 total_N 低估。

---
*本报告由 `build_global_overview.py` 从真实 checkpoint/CSV/state 文件程序化合并生成 · 快照 2026-07-26 18:54 GMT+8 · 数字均来自文件实测，未编造。*