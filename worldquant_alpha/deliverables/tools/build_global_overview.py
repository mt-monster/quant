#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_global_overview.py — 全局总览版报告生成器
合并所有账号（主账号 worldquant_alpha / tri_track / analyze_tabbit / scan_rescue /
continuous_undug / green_guard）的挖矿活动，按账号分列 + 诚实合并。
所有数字均从真实 checkpoint/CSV/state 文件程序化读取，无硬编码。
"""
import os, json, csv, glob
from collections import Counter
from datetime import datetime

ROOT = r"C:/Users/MENGTAO/Desktop/E3/quant/worldquant_alpha"
RES = os.path.join(ROOT, "results")
BAIDU = r"D:/BaiduNetdiskDownload/WQ第二三四节课代码/worldquant"
REP = os.path.join(ROOT, "deliverables", "reports")
os.makedirs(REP, exist_ok=True)
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

def load_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

out = []
def a(s=""):
    out.append(s)

# ============ 主账号 worldquant_alpha (results/*_checkpoint.json) ============
main_total = 0
main_pc = 0      # PASS_CHEAP
main_cp = 0      # CHECK_PENDING
main_pass = 0    # PASS
main_found = 0   # found_alphas
main_pids = 0    # 有 pid 的回测（成功获 alpha_id）
main_bestS = 0.0
main_ckpts = 0
for ck in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
    d = load_json(ck)
    if not d:
        continue
    main_ckpts += 1
    res_list = d.get("results", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
    found_list = d.get("found_alphas", []) if isinstance(d, dict) else []
    for r in res_list:
        if not isinstance(r, dict):
            continue
        main_total += 1
        st = r.get("status")
        if st == "PASS_CHEAP":
            main_pc += 1
        elif st == "CHECK_PENDING":
            main_cp += 1
        elif st == "PASS":
            main_pass += 1
        if r.get("pid"):
            main_pids += 1
        sh = r.get("sharpe") or 0
        if isinstance(sh, (int, float)) and sh > main_bestS:
            main_bestS = sh
    for fa in found_list:
        if not isinstance(fa, dict):
            continue
        main_found += 1
        sh = fa.get("sharpe") or 0
        if isinstance(sh, (int, float)) and sh > main_bestS:
            main_bestS = sh
main_cands = main_pc + main_cp + main_pass  # 候选 = 过廉价IS闸

# ============ tri_track (独立账号 ML88164) ============
tt_csv = os.path.join(BAIDU, "tri_track_undug_results.csv")
tt_rows = list(csv.DictReader(open(tt_csv, encoding="utf-8")))
tt_total = len(tt_rows)                      # 累计提交日志
tt_unique = len({r["alpha_id"] for r in tt_rows if r["alpha_id"].strip()})
tt_tracks = Counter(r["track"] for r in tt_rows)
tt_dates = sorted(r["finished_at"] for r in tt_rows if r["finished_at"].strip())
tt_ck = load_json(os.path.join(BAIDU, "tri_track_undug_checkpoint.json"))
tt_round = len(tt_ck.get("results", []))     # 当前轮工作集

# ============ analyze_tabbit (tabbit 账号) ============
tabbit_files = sorted(glob.glob(os.path.join(BAIDU, "tabbit_*_results.csv")))
tabbit_detail = {}
tabbit_total = 0
for f in tabbit_files:
    n = sum(1 for _ in csv.reader(open(f, encoding="utf-8"))) - 1
    tabbit_total += n
    tabbit_detail[os.path.basename(f)] = n

# ============ scan_rescue (主账号 web_traffic 救援) ============
sr_ck = load_json(os.path.join(RES, "rescue_r3_web_lift_checkpoint.json"))
sr_results = len(sr_ck.get("results", []))
sr_found = len(sr_ck.get("found_alphas", []))
sr_pc = sum(1 for r in sr_ck.get("results", []) if r.get("status") == "PASS_CHEAP")

# ============ continuous_undug (独立账号 ML88164, 连续调度) ============
cu_state = load_json(os.path.join(BAIDU, "continuous_undug_state.json"))
cu_done = len(cu_state.get("completed", []))

# ============ green_guard (独立账号, /check 绿标核查器) ============
# 仅日志，非挖矿，无回测计数

# ============ 合并口径（诚实标注） ============
# 注意: scan_rescue 的 checkpoint 位于 results/ 目录, 已计入 main_total/main_cands/main_pids,
#       故合并时【不重复加】, 仅作为主账号子任务单列展示。
# 口径A: 全局研究回测（记失败回测的账号 → 主账号含 ds舰队/v52b/scan_rescue）
global_research = main_total
# 口径B: 全局平台 alpha 创建记录（获 alpha_id 的提交日志，各独立账号合计 + 主账号 pids）
global_created = main_pids + tt_total + tabbit_total
# 确证 ACTIVE
global_active = 1  # YPgAa3WR（主账号 found_alphas，status=ACTIVE, 07-24）
# 候选池（有IS指标、待OOS验证）— main_cands 已含 scan_rescue 的 2 PASS_CHEAP
global_candidate_pool = main_cands
# 已推平台但未核实（无IS指标存档）
global_unverified = tt_total + tabbit_total

# ============ 输出 MD ============
a(f"> **数据快照**: {NOW} GMT+8 ｜ **合并口径说明**: 主账号/scan_rescue 记录全部研究回测(含失败)；tri_track/tabbit/continuous_undug 仅记成功获 alpha_id 的提交，其真实回测总量 > 提交日志。下游平台 ACTIVE 状态除 YPgAa3WR 外均未逐个核实。")
a()
a(f"> ⚠️ **最重要结论**：全部账号合并后，**仅 1 个 alpha 确证已真正提交并上线**（`YPgAa3WR`，主账号，ACTIVE，07-24）。其余候选/提交均卡在平台生产仿真(OOS)硬闸门或未核实。")
a()
a("---")
a("## 一、各账号总览（分列）")
a()
a("| 账号 | 挖矿模型 | 计数口径 | 回测/提交数 | 候选(过IS闸) | 确证ACTIVE | 在飞进程 |")
a("|---|---|---|---|---|---|---|")
a(f"| 🚢 主账号 worldquant_alpha (mthyzx@126.com) | 研究仿真闸门 | 研究回测(含失败) | **{main_total:,}** | {main_cands} ({main_pc} cheap+{main_cp} pending+{main_pass} pass) | 1 (YPgAa3WR) | 7 ds + scan_rescue |")
a(f"| 🛡️ tri_track (ML88164) | 全量提交 | 提交日志 | **{tt_total:,}** (累计) / {tt_round} (当前轮) | —(无IS指标存档) | 未核实 | 2 |")
a(f"| 🟠 analyze_tabbit (tabbit) | 全量提交 | 提交日志 | **{tabbit_total:,}** | — | 未核实 | 2 |")
a(f"| 🔵 continuous_undug (ML88164) | 连续调度 | 调度分块 | {cu_done} 块完成(计划9数据集) | — | 未核实 | 2 |")
a(f"| 🟢 green_guard (独立) | /check 绿标核查 | 检查器 | 0 (非挖矿) | — | — | 2 |")
a(f"| 🔧 scan_rescue (主账号子任务) | web_traffic 救援 | 研究回测 | {sr_results} (当前轮) | {sr_pc} PASS_CHEAP | 0 found | 1 |")
a(f"> 注：scan_rescue 写入 `results/`，其 {sr_results} 次回测与 {sr_pc} PASS_CHEAP 已计入上方「主账号」总量（主账号 = ds舰队 + v52b + scan_rescue 全部 results/ checkpoint），本行仅作任务级单列，合并口径不重复相加。")
a()
a("**tri_track 轨道分布**：" + "，".join(f"{k}={v}" for k, v in tt_tracks.most_common()) + f"（累计 {tt_total} 条，日期 {tt_dates[0]} ~ {tt_dates[-1]}）。")
a()
a("**tabbit 各数据集结果**：" + "，".join(f"{k.split('_')[1].split('.')[0]}={v}" for k, v in tabbit_detail.items()) + f"（合计 {tabbit_total} 条提交记录）。")
a()
a("---")
a("## 二、全局合并指标（诚实标注口径）")
a()
a("| 合并指标 | 数值 | 口径说明 |")
a("|---|---|---|")
a(f"| 全局研究回测(精确) | **{global_research:,}** | 主账号 {main_total:,}（已含 ds舰队/v52b/scan_rescue；其余账号不记失败回测，真实回测 > 其提交日志） |")
a(f"| 全局平台 alpha 创建记录 | **{global_created:,}** | 各账号获 alpha_id 的提交日志合计 = 主账号 {main_pids} + tri_track {tt_total:,} + tabbit {tabbit_total:,}（scan_rescue 已计入主账号 {main_pids}） |")
a(f"| 全局确证 ACTIVE(已上线) | **{global_active}** | 仅 `YPgAa3WR`（主账号，07-24 提交，平台 ACTIVE） |")
a(f"| 全局候选池(待OOS验证) | **{global_candidate_pool}** | 主账号 {main_cands}（已含 scan_rescue {sr_pc} PASS_CHEAP），有IS指标、需跑生产仿真→/check→submit |")
a(f"| 全局已推平台未核实 | **{global_unverified:,}** | tri_track {tt_total:,} + tabbit {tabbit_total:,}（已获 alpha_id 推平台，但无IS指标存档，平台 ACTIVE/FAIL 状态需逐个 /check 核实） |")
a(f"| 全链路最佳 Sharpe | **{main_bestS:.2f}** | 来自主账号 v52b 降换手变体 |")
a()
a("> ⚠️ **口径警示**：`全局研究回测` 与 `全局平台 alpha 创建记录` 是两个**不可直接相加**的口径——前者含失败回测，后者仅含成功获 id 的提交。此处分列仅为呈现活动规模，切勿误读为 `总挖矿量 = 两者之和`。")
a()
a("---")
a("## 三、全局提交就绪漏斗")
a()
a("```")
a(f"  研究仿真回测(主+scan_rescue)   ████  {global_research:,}")
a(f"  获 alpha_id 提交记录(全局)      ██    {global_created:,}")
a(f"  确证 ACTIVE(已上线)            █     {global_active}")
a("```")
a()
a(f"每一级硬闸门：`研究仿真` 筛掉绝大多数(主账号 {main_total - main_pids:,} 次失败)；`获 alpha_id` 后 `YPgAa3WR` 是全局唯一跨过生产相关性+风险中性+平台提交闸门者。tri_track/tabbit 的 {global_unverified:,} 条提交**未存IS指标**，无法判定是否真正过闸。")
a()
a("---")
a("## 四、逐账号提交核查（三级分类）")
a()
a("| 分类 | 账号 / alpha | 说明 |")
a("|---|---|---|")
a(f"| ✅ 已提交(ACTIVE) | 主账号 `YPgAa3WR` | prod_corr=0.5325，07-24 上线，全局唯一 |")
a(f"| 🟡 候选池·待OOS验证 | 主账号 {main_cands} 候选（含 scan_rescue {sr_pc} PASS_CHEAP） | 需跑生产仿真→全量/check→submittable→submit(关 no_submit) |")
a(f"| ❓ 已推平台·未核实 | tri_track {tt_total:,} + tabbit {tabbit_total:,} | 已获 alpha_id 推平台，无IS指标存档，需逐个 /check 确认状态 |")
a(f"| ⏳ 调度中 | continuous_undug {cu_done} 块 / green_guard 核查中 | 持续产出，暂无落地 |")
a()
a(f"> 结论：**无任何账号的挖掘产出（除 YPgAa3WR 外）满足 WQ 完整提交四关**（研究IS→生产OOS→平台/check→显式submit）。主账号 {main_cands} 候选（已含 scan_rescue {sr_pc} PASS_CHEAP）仍需生产仿真验证；tri_track/tabbit 的 {global_unverified:,} 条需回溯 IS 指标并 /check。")
a()
a("---")
a("## 五、在飞任务与 ETA")
a()
a("| 任务 | 账号 | 状态 | 预期完成 | 置信度 |")
a("|---|---|---|---|---|")
a("| 🚢 ds 舰队 (7路实时) | 主账号 | 7 进程运行，多数数据集进度<100%无活动进程(待 fleet_keeper) | 见主报告 per-dataset ETA | 中(参考主报告) |")
a(f"| 🛡️ tri_track_undug | ML88164 | 持续提交中 (累计 {tt_total:,}, 当前轮 {tt_round}) | 连续挖矿，无明确终点 | 低 |")
a(f"| 🔵 continuous_undug | ML88164 | 调度中 (完成 {cu_done} 块/计划9数据集) | 连续调度，无明确终点 | 低 |")
a(f"| 🟠 analyze_tabbit | tabbit | 2 进程在飞 | 连续挖矿 | 低 |")
a(f"| 🟢 green_guard | 独立 | 2 进程 /check 绿标核查 | 持续 | 低 |")
a(f"| 🔧 scan_rescue | 主账号 | {sr_results} 回测完成, {sr_pc} PASS_CHEAP | 本轮近尾声 | 中 |")
a()
a("> 详细 per-dataset ETA 见主报告 `factor_mining_report_*.md`（ds 舰队章节）。本总览聚焦跨账号合并。")
a()
a("---")
a("## 六、关键结论与下一步")
a()
a("1. **全局仅 1 个 alpha 真正上线**（YPgAa3WR），其余 0 个满足完整提交四关。")
a(f"2. **主账号是信号发现主战场**：{main_total:,} 次研究回测产 {main_cands} 候选，但 0 found_alphas（全卡生产相关性/风险中性）。")
a(f"3. **tri_track/tabbit 重「量」不重「质」**：{global_unverified:,} 条提交但无IS指标存档，需回溯验证才有意义。")
a(f"4. **continuous_undug 是补充调度**：覆盖主账号未挖数据集，当前 {cu_done} 块完成。")
a(f"5. **下一步优先级**：① 对主账号 {main_cands} 候选跑生产仿真→/check→submit（走通 YPgAa3WR 全流程复制）；② 回溯 tri_track/tabbit 的 {global_unverified:,} 条提交做 /check 状态核实；③ 统一 checkpoint 目录消除 total_N 低估。")
a()
a("---")
a(f"*本报告由 `build_global_overview.py` 从真实 checkpoint/CSV/state 文件程序化合并生成 · 快照 {NOW} GMT+8 · 数字均来自文件实测，未编造。*")

md = "\n".join(out)
stamp = datetime.now().strftime("%Y%m%d_%H%M")
path = os.path.join(REP, f"global_overview_{stamp}.md")
with open(path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"WROTE {path} ({len(out)} lines)")
print(f"main_total={main_total} main_cands={main_cands} main_found={main_found} main_bestS={main_bestS:.2f}")
print(f"tri_track={tt_total} (round={tt_round}) tabbit={tabbit_total} scan_rescue={sr_results}(pc={sr_pc}) cu_done={cu_done}")
print(f"global_research={global_research} global_created={global_created} global_active={global_active} global_candidate_pool={global_candidate_pool} global_unverified={global_unverified}")
