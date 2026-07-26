# -*- coding: utf-8 -*-
"""优化 431 行 section 13 的层级钻取文件：添加树形结构概览 + 仅展开 Top 模板。"""
import json, glob, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "results")
OUT_DIR = os.path.join(ROOT, "deliverables", "reports", "details")

# --- helpers ---
def extract_field_name(expr):
    if not expr: return "?"
    s = expr
    for wrapper in ("rank(", "group_zscore(", "ts_zscore(", "ts_backfill(", "group_rank("):
        if wrapper in s: s = s.split(wrapper, 1)[-1]
    for prefix in ("vec_avg(", "vec_sum(", "ts_mean("):
        if s.startswith(prefix): s = s[len(prefix):]
    field = s.split(",")[0].split(")")[0].strip()
    if "(" in field: field = field.split("(")[-1]
    return field[:30]

# --- collect data ---
recs = []
per = {}  # task -> {N, bestS, candidates}
for f in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
    try: d = json.load(open(f, encoding="utf-8"))
    except: continue
    task = os.path.basename(f).replace("_checkpoint.json", "")
    items = d if isinstance(d, list) else d.get("results", [])
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d")
    for r in items:
        r["_task"] = task; r["_ckpt_date"] = mtime
        recs.append(r)
    # per-task stats
    p = per.setdefault(task, {"N": 0, "bestS": 0.0, "cands": 0, "ckpt_date": mtime,
                              "field": "", "universe": "?", "decay": "?", "neutral": "?"})
    for r in items:
        p["N"] += 1
        s = float(r.get("sharpe") or 0)
        if s > p["bestS"]: p["bestS"] = s
        if str(r.get("status","")) in ("PASS_CHEAP","CHECK_PENDING"): p["cands"] += 1
        if not p["field"]:
            expr = r.get("expr","")
            p["field"] = extract_field_name(expr)
        if not p.get("cfg_set"):
            stg = r.get("settings") or {}
            p["universe"] = stg.get("universe","?")
            p["decay"] = stg.get("decay","?")
            p["neutral"] = str(stg.get("neutralization","?"))[:3]
    p["cfg_set"] = True

# --- classify accounts ---
main_tasks = sorted(per.keys(), key=lambda t: -per[t]["bestS"])
# Group into categories
v_series = [t for t in main_tasks if t.startswith("v")]  # v52b, v39b, etc
ds_active = [t for t in main_tasks if t.startswith("ds_")]  # all ds fleet
rescue = [t for t in main_tasks if t.startswith("rescue_")]

# Filter for display: top templates by bestS
TOP_N = 12
all_sorted = sorted(main_tasks, key=lambda t: -per[t]["bestS"])
top_templates = [t for t in all_sorted if per[t]["bestS"] >= 1.0][:TOP_N]
if len(top_templates) < 8:
    top_templates = all_sorted[:TOP_N]

# --- build output ---
L = []
def a(s=""): L.append(s)
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

a("# 三维层级钻取（账号 → 模板 → 日期）")
a()
a(f"> 生成时间：{NOW} GMT+8")
a(f"> 从 {len(per)} 个因子模板 / {len(recs):,} 回测记录中提取")
a()

# ═══ 树形结构概览 ═══
a("## 一、层级结构概览")
a()
a("```")
a(f"🚢 主账号 mthyzx")
a(f"├── 📦 v系列独立模板 ({len(v_series)} 个)")
for t in sorted(v_series, key=lambda t: -per[t]["bestS"])[:6]:
    p = per[t]
    cand_mark = f" 🔥{p['cands']}候选" if p["cands"] else ""
    a(f"│   ├── {t:35s} S⚡{p['bestS']:.2f}  N={p['N']:>4}{cand_mark}")
if len(v_series) > 6:
    a(f"│   └── ... +{len(v_series)-6} 个")
a(f"│")
a(f"├── 🌐 ds 舰队 ({len(ds_active)} 个数据集)")
# sub-group by status (approximate from bestS > 0 means had progress)
ds_with_progress = [t for t in ds_active if per[t]["N"] > 0]
ds_top5 = sorted(ds_with_progress, key=lambda t: -per[t]["bestS"])[:5]
for t in ds_top5:
    p = per[t]
    a(f"│   ├── {t[:50]:50s} S⚡{p['bestS']:.2f}  N={p['N']}")
a(f"│   └── ... +{len(ds_active)-5} 个数据集")
a(f"│")
a(f"├── 🔧 rescue 救援 ({len(rescue)} 个)")
for t in sorted(rescue, key=lambda t: -per[t]["bestS"])[:3]:
    p = per[t]
    a(f"│   ├── {t[:50]:50s} S⚡{p['bestS']:.2f}")
if len(rescue) > 3:
    a(f"│   └── ... +{len(rescue)-3} 个")
a(f"│")
a(f"└── 🛡️ 独立账号 ML88164")
a(f"    ├── tri_track_undug  (三轨挖掘)")
a(f"    └── continuous_undug  (连续未挖数据集调度)")
a("```")
a()
a(f"> **统计**：{len(per)} 模板、{len(ds_active)} 个 ds 数据集、{len(rescue)} 个救援、{len(v_series)} 个独立变体序列。")
a()

# ═══ Top 模板展开 ═══
a("## 二、Top 模板详览（按 Sharpe 降序，前 12）")
a()
a("仅展开最佳 Sharpe ≥ 1.0 的 Top 模板。完整 79 模板的全量数字见第五、第八节明细文件。")
a()

for t in top_templates:
    p = per[t]
    cand_mark = "🔥" if p["cands"] else ""
    a(f"### {cand_mark} {t}")
    a()
    # extract config from first record
    field = p.get("field", "?")
    cfg = f"{p['universe']} d{p['decay']} {p['neutral']}"
    a(f"> 信号字段：`{field}` · 配置：{cfg} · 回测日期：{p['ckpt_date']}")
    a()
    a(f"| 指标 | 数值 |")
    a(f"|---|---|")
    a(f"| 回测量 | **{p['N']}** |")
    a(f"| 最佳 Sharpe | **{p['bestS']:.2f}** |")
    a(f"| PASS_CHEAP | **{p['cands']}** |")
    a()

    # date breakdown
    task_recs = [r for r in recs if r["_task"] == t]
    if task_recs:
        dates = {}
        for r in task_recs:
            d = r.get("_ckpt_date", "?")
            dates.setdefault(d, []).append(r)
        if len(dates) > 1 or p["cands"] > 0:
            a(f"**回测日期明细：**")
            a()
            a("| 日期 | 回测N | PASS_CHEAP | 最佳S |")
            a("|---|---:|---:|---:|")
            for d in sorted(dates.keys()):
                entries = dates[d]
                dn = len(entries)
                dc = sum(1 for r in entries if str(r.get("status","")) in ("PASS_CHEAP","CHECK_PENDING"))
                db = max((float(r.get("sharpe") or 0) for r in entries), default=0.0)
                a(f"| {d} | {dn} | {dc} | {db:.2f} |")
            a()
    a()

a("---")
a(f"*完整 79 模板的全量数据见 [Sharpe 排名明细](detail_sharpe_ranking.md) 和 [候选 Alpha 列表](detail_candidates.md)。*")

# write
out_path = os.path.join(OUT_DIR, "detail_hierarchical_drilldown.md")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print(f"WROTE {out_path} ({len(L)} lines)")
print(f"Templates: {len(per)}, Top expanded: {len(top_templates)}")
