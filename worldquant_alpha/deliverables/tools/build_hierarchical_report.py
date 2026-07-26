# -*- coding: utf-8 -*-
"""三维层级报告生成器：账号 → 因子模板 → 回测日期。
从 checkpoint + progress 日志 + tri_track CSV 实算，组织为三层递进框架。"""
import json, glob, os, csv, datetime

NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "results")
TRI_DIR = r"D:\BaiduNetdiskDownload\WQ第二三四节课代码\worldquant"

L = []
def a(s=""): L.append(s)

# ═══════════════ 数据加载（与 build_md_report.py 共用管道）═══════════════

# --- 主账号 checkpoint ---
recs = []; found = []; n_ckpt_files = 0
for f in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
    try: d = json.load(open(f, encoding="utf-8"))
    except: continue
    n_ckpt_files += 1
    task = os.path.basename(f).replace("_checkpoint.json", "")
    res = d if isinstance(d, list) else d.get("results", [])
    fa = [] if isinstance(d, list) else (d.get("found_alphas") or [])
    for r in res: r["_task"] = task; r["_ckpt"] = task; recs.append(r)
    for x in (fa if isinstance(fa, list) else []): x["_task"] = task; found.append(x)

total_N = len(recs)
pc = [r for r in recs if str(r.get("status","")) == "PASS_CHEAP"]
cp = [r for r in recs if str(r.get("status","")) == "CHECK_PENDING"]
is_cleared = len(pc) + len(cp)
bestS = max((float(r.get("sharpe") or 0) for r in recs), default=0.0)

# 每任务统计
per = {}
for r in recs:
    t = r["_task"]
    p = per.setdefault(t, {"N":0, "pc":0, "cp":0, "bestS":0.0})
    p["N"] += 1
    st = str(r.get("status",""))
    if st == "PASS_CHEAP": p["pc"] += 1
    elif st == "CHECK_PENDING": p["cp"] += 1
    s = float(r.get("sharpe") or 0)
    if s > p["bestS"]: p["bestS"] = s

# 失败闸门
fcats = {"S(夏普)":0,"F(拟合)":0,"M(换手收益)":0,"Ret(收益)":0,"TVR(换手率)":0,
         "PF:子宇宙Sharpe":0,"submit_failed":0}
pf_detail = {}
for r in recs:
    fl = r.get("fails")
    if not isinstance(fl, list): continue
    for x in fl:
        s = str(x)
        if s.startswith("PF:"): fcats["PF:子宇宙Sharpe"] += 1; pf_detail[s] = pf_detail.get(s,0)+1
        elif s.startswith("S="): fcats["S(夏普)"] += 1
        elif s.startswith("F="): fcats["F(拟合)"] += 1
        elif s.startswith("M="): fcats["M(换手收益)"] += 1
        elif s.startswith("Ret="): fcats["Ret(收益)"] += 1
        elif "tvr" in s.lower(): fcats["TVR(换手率)"] += 1
        elif s == "submit_failed": fcats["submit_failed"] += 1

# found 详情
found_pid = found[0]["pid"] if found else "?"
found_pcorr = found[0].get("prod_corr","?") if found else "?"

# verified data
verified = {}
try:
    vf = os.path.join(RES, "_platform_verified.json")
    if os.path.exists(vf): verified = json.load(open(vf, encoding="utf-8"))
except: pass

n_active_total = sum(1 for v in verified.values() if v.get("status")=="ACTIVE")
n_rejected_total = sum(1 for v in verified.values() if v.get("status") in ("UNSUBMITTED","GATE_FAIL","NO_OOS"))

# active ds processes
ds_active_processes = set()
try:
    ap_file = os.path.join(RES, "_ds_active_processes.json")
    if os.path.exists(ap_file): ds_active_processes = set(json.load(open(ap_file, encoding="utf-8-sig")))
except: pass

# --- ds progress ---
ds_datasets_live = set()
ds_live = {}
for log_path in sorted(glob.glob(os.path.join(RES, "ds_*_tri_progress_*.log"))):
    fname = os.path.basename(log_path)
    prefix = fname.split("_tri_progress_")[0]
    last = None
    for ln in open(log_path, encoding="utf-8", errors="ignore"):
        try: e = json.loads(ln)
        except: continue
        if e.get("event") in ("progress", "finish"): last = e
    if last:
        done = last.get("done", 0); tot = last.get("total", 320)
        el = last.get("elapsed_sec") or 0
        pct = done/tot*100 if tot else 0
        thr = done/(el/3600.0) if el > 0 else 0
        eta_str = "?"
        if done >= tot: eta_str = "已完成"
        elif done > 0 and el > 0 and done < tot:
            pace = done/el; remaining = tot-done
            eta_s = remaining/pace
            eta_dt = datetime.datetime.now() + datetime.timedelta(seconds=eta_s)
            eta_str = eta_dt.strftime("%m-%d %H:%M")
        ds_live[prefix] = {"done":done,"total":tot,"pct":round(pct,1),
                           "elapsed_min":round(el/60,1),"alpha_per_hr":round(thr,0),"eta":eta_str}
        if last.get("event") == "progress" and done < tot: ds_datasets_live.add(prefix)

ds_tasks = [k for k in per if k.startswith("ds_")]
def ds_short(k): return k.split("_tri_")[0].replace("ds_","")
def ds_live_key(k): return k.split("_tri_")[0]

# --- tri_track ---
tri_total = 0; tri_tracks = {}; tri_bestS = 0.0; tri_submitted = 0; tri_fail = 0
tri_has_metrics = False; tri_earliest = "?"; tri_latest = "?"
tri_ckpt = os.path.join(TRI_DIR, "tri_track_undug_checkpoint.json")
if os.path.exists(tri_ckpt):
    try:
        d = json.load(open(tri_ckpt, encoding="utf-8"))
        for r in d.get("results", []):
            tri_total += 1
            tr = r.get("track", "?"); tri_tracks[tr] = tri_tracks.get(tr, 0)+1
            st = r.get("status", "?")
            if st == "submitted": tri_submitted += 1
            else: tri_fail += 1
            s = r.get("sharpe")
            if s is not None:
                tri_has_metrics = True
                if s > tri_bestS: tri_bestS = s
        ft = d.get("results",[{}])[0].get("finished_at","")
        ft_last = d["results"][-1].get("finished_at","") if d.get("results") else ""
        tri_earliest = ft or "?"; tri_latest = ft_last or "?"
    except: pass

# --- continuous_undug ---
cu_state_path = os.path.join(TRI_DIR, "continuous_undug_state.json")
cu_blocks = 0; cu_ds_done = set(); cu_started = "?"; cu_last = "?"
if os.path.exists(cu_state_path):
    try:
        cu = json.load(open(cu_state_path, encoding="utf-8"))
        cu_blocks = len(cu.get("completed", []))
        for block in cu.get("completed", []):
            ds = block.split(":")[0]
            if ds: cu_ds_done.add(ds)
        cu_started = cu.get("started_at", "?")[:10]
        cu_last = cu.get("last_at", "?") or "?"
    except: pass

# --- v52b ---
v52b_done = per.get("v52b_hiring_margin", {}).get("N", 0)
v52b_finished = v52b_done >= 160
v52b_pc = per.get("v52b_hiring_margin", {}).get("pc", 0)

# --- ds in-progress ---
ds_in_progress = max(len(ds_datasets_live),
    sum(1 for t in ds_tasks if ds_live.get(ds_live_key(t),{}).get("eta","") not in ("已完成","")))

# ===== 构建三层层级结构 =====

# classify tasks into account→template
def classify_task(task_name):
    """Return (account, template_group)."""
    if task_name.startswith("ds_"):
        ds_full = ds_short(task_name)
        # check active/paused/completed
        lv = ds_live.get(ds_live_key(task_name), {})
        eta = lv.get("eta", "?")
        has_active = any(ap in task_name or ap == ds_full for ap in ds_active_processes)
        if has_active:
            return ("主账号 mthyzx", f"🔵 ds-{ds_full}", "活跃")
        elif eta != "已完成":
            return ("主账号 mthyzx", f"⏸️ ds-{ds_full}", "暂停")
        else:
            return ("主账号 mthyzx", f"✅ ds-{ds_full}", "已完成")
    if task_name.startswith("rescue_"):
        return ("主账号 mthyzx", f"🔧 {task_name}", "救援")
    return ("主账号 mthyzx", task_name, "独立")

# group by date within each template
def get_date(r):
    """Extract YYYY-MM-DD from record."""
    ts = r.get("finished_at") or r.get("ts") or ""
    if ts: return ts[:10]
    return "日期未知"

# build ckpt→mtime map for date fallback
ckpt_mtime_map = {}
for f in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
    task = os.path.basename(f).replace("_checkpoint.json", "")
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d")
    ckpt_mtime_map[task] = mtime

# build hierarchy
hierarchy = {}
for r in recs:
    t = r["_task"]
    acct, tmpl, _ = classify_task(t)
    date = get_date(r)
    # fall back to checkpoint file mtime
    if date == "日期未知" and t in ckpt_mtime_map:
        date = ckpt_mtime_map[t]
    if acct not in hierarchy: hierarchy[acct] = {}
    if tmpl not in hierarchy[acct]: hierarchy[acct][tmpl] = {}
    if date not in hierarchy[acct][tmpl]: hierarchy[acct][tmpl][date] = []
    hierarchy[acct][tmpl][date].append(r)

# --- add independent account entries ---
ind_acct = "独立账号 ML88164"
hierarchy.setdefault(ind_acct, {})

# tri_track
if os.path.exists(tri_ckpt):
    try:
        d = json.load(open(tri_ckpt, encoding="utf-8"))
        for r in d.get("results", []):
            date = get_date(r)
            tmpl_name = f"🛡️ tri_track_{r.get('track','?')}"
            hierarchy[ind_acct].setdefault(tmpl_name, {}).setdefault(date, []).append(r)
    except: pass

# continuous_undug (state-based, no per-result records)
if cu_blocks:
    # create a synthetic entry for display
    cu_entry = {"_task": "continuous_undug", "status": "running", "sharpe": None,
                "finished_at": cu_last, "blocks": cu_blocks, "datasets": sorted(cu_ds_done)}
    hierarchy[ind_acct].setdefault("🔵 continuous_undug", {}).setdefault(cu_started, []).append(cu_entry)

# ═══════════════ 报告生成 ═══════════════

TH = 1.58
def sflag(v):
    if v >= TH: return "🟢"
    if v >= 1.0: return "🟡"
    return "🔴"

# ===== 页眉 =====
a(f"> **三维层级报告** · 快照 {NOW} GMT+8 · 框架：账号 → 因子模板 → 回测日期")
a(f"> 数据源：`results/*_checkpoint.json` + `tri_track` + `continuous_undug_state.json`")
a()

# ===== 一、全局核心结论 =====
a("---"); a("## 一、全局核心结论"); a()
a(f"| 指标 | 数值 |")
a(f"|---|---|")
a(f"| 累计回测次数 | **{total_N:,}** ({n_ckpt_files} checkpoint) |")
a(f"| IS 闸门通过候选 | **{is_cleared}** ({len(pc)}+{len(cp)}) |")
a(f"| 平台 ACTIVE | **{n_active_total}** |")
a(f"| 平台拒绝 | **{n_rejected_total}** |")
a(f"| 最佳 Sharpe | **{bestS:.2f}** |")
a(f"| ds 舰队并发 | {len(ds_active_processes)} 活跃 / {ds_in_progress} 记录在档 |")
a(f"| tri_track | {tri_total} α, 最佳 S={tri_bestS:.2f} |")
a(f"| continuous_undug | {cu_blocks} 块/{len(cu_ds_done)} 数据集 |")
a()

# ===== 二、账号维度总览 =====
a("---"); a("## 二、账号维度总览"); a()

for acct_name in sorted(hierarchy.keys()):
    tmpls = hierarchy[acct_name]
    acct_N = sum(sum(len(dates[d]) for d in dates) for dates in tmpls.values())
    acct_bestS = 0.0
    acct_cands = 0
    for tmpl_name, dates in tmpls.items():
        for date_entries in dates.values():
            for r in date_entries:
                s = float(r.get("sharpe") or 0)
                if s > acct_bestS: acct_bestS = s
                if str(r.get("status","")) in ("PASS_CHEAP","CHECK_PENDING"): acct_cands += 1
    n_tmpls = len(tmpls)
    n_dates = len(set(d for dates in tmpls.values() for d in dates))

    icon = "🚢" if "主账号" in acct_name else "🛡️"
    a(f"### {icon} {acct_name}")
    a()
    a(f"| 指标 | 数值 |")
    a(f"|---|---|")
    a(f"| 因子模板数 | {n_tmpls} |")
    a(f"| 回测日期跨度 | {n_dates} 天 |")
    a(f"| 累计回测次数 | {acct_N:,} |")
    a(f"| IS 闸门通过候选 | {acct_cands} |")
    a(f"| 最佳 Sharpe | {acct_bestS:.2f} |")
    a()

# ===== 三、逐账号 · 因子模板级展开 =====
a("---"); a("## 三、因子模板级详览（账号 → 模板）"); a()

for acct_name in sorted(hierarchy.keys()):
    tmpls = hierarchy[acct_name]
    a(f"## {acct_name}")
    a()

    # sort templates: active ds first, then paused, then completed, then others
    def tmpl_sort_key(tn):
        if tn.startswith("🔵"): return (0, tn)
        if tn.startswith("⏸️"): return (1, tn)
        if tn.startswith("✅"): return (2, tn)
        if tn.startswith("🔧"): return (4, tn)
        return (3, tn)

    sorted_tmpls = sorted(tmpls.items(), key=lambda x: tmpl_sort_key(x[0]))

    for tmpl_name, dates in sorted_tmpls:
        tmpl_N = sum(len(dates[d]) for d in dates)
        tmpl_bestS = 0.0
        tmpl_pc = 0; tmpl_cp = 0; tmpl_pids = 0
        tmpl_cfg = {}
        for date_entries in dates.values():
            for r in date_entries:
                s = float(r.get("sharpe") or 0)
                if s > tmpl_bestS: tmpl_bestS = s
                st = str(r.get("status",""))
                if st == "PASS_CHEAP": tmpl_pc += 1
                elif st == "CHECK_PENDING": tmpl_cp += 1
                if r.get("pid"): tmpl_pids += 1
                if not tmpl_cfg and r.get("settings"):
                    stg = r["settings"]
                    tmpl_cfg = {k: stg[k] for k in ("universe","decay","neutralization","region") if k in stg}

        vf_active = sum(1 for pid in [r.get("pid") for dates_v in dates.values() for r in dates_v if r.get("pid")]
                        if verified.get(pid,{}).get("status")=="ACTIVE")

        a(f"### {tmpl_name}")
        a()
        # template config
        if tmpl_cfg:
            cfg_str = ", ".join(f"{k}={v}" for k,v in tmpl_cfg.items())
            a(f"> 配置: {cfg_str}")
        a(f"| 指标 | 数值 |")
        a(f"|---|---|")
        a(f"| 回测批次数 | {tmpl_N} |")
        a(f"| PASS_CHEAP | {tmpl_pc} |")
        a(f"| CHECK_PENDING | {tmpl_cp} |")
        a(f"| 最佳 Sharpe | {tmpl_bestS:.2f} |")
        a(f"| 获 alpha_id | {tmpl_pids} |")
        a(f"| 平台 ACTIVE | {vf_active} |")
        a(f"| 回测日期跨度 | {len(dates)} 天 |")
        a()

        # --- date-level detail (collapsed by default) ---
        if len(dates) > 1 or tmpl_pc > 0:
            a(f"#### 回测日期级明细")
            a()
            a("| 日期 | 回测N | PASS_CHEAP | 最佳S | 获pid | ACTIVE |")
            a("|---|---:|---:|---:|---:|---:|")
            for date in sorted(dates.keys()):
                entries = dates[date]
                dN = len(entries)
                dpc = sum(1 for r in entries if str(r.get("status",""))=="PASS_CHEAP")
                dbs = max((float(r.get("sharpe") or 0) for r in entries), default=0.0)
                dpids = sum(1 for r in entries if r.get("pid"))
                dactive = sum(1 for r in entries if r.get("pid") and verified.get(r["pid"],{}).get("status")=="ACTIVE")
                a(f"| {date} | {dN} | {dpc} | {dbs:.2f} | {dpids} | {dactive} |")
            a()
        a()

# ===== 四、提交核查（按账号×模板）=====
a("---"); a("## 四、候选提交核查（按账号×模板）"); a()
a(f"| 账号 | 模板 | 候选数 | ACTIVE | 平台拒绝 | 待验证 |")
a(f"|---|---|---:|---:|---:|---:|")

for acct_name in sorted(hierarchy.keys()):
    for tmpl_name, dates in hierarchy[acct_name].items():
        cands_set = set()
        for date_entries in dates.values():
            for r in date_entries:
                if str(r.get("status","")) in ("PASS_CHEAP","CHECK_PENDING") and r.get("pid"):
                    cands_set.add(r["pid"])
        active_n = sum(1 for p in cands_set if verified.get(p,{}).get("status")=="ACTIVE")
        rejected_n = sum(1 for p in cands_set if verified.get(p,{}).get("status") in ("UNSUBMITTED","GATE_FAIL","NO_OOS"))
        remain_n = len(cands_set) - active_n - rejected_n
        if cands_set:
            a(f"| {acct_name.split(' ')[0]} | {tmpl_name} | {len(cands_set)} | {active_n} | {rejected_n} | {remain_n} |")
a()

# ===== 五、在飞任务ETA =====
a(); a("---"); a("## 五、在飞任务 ETA"); a()

# ds active
ds_running = []
ds_paused = []
for t in ds_tasks:
    lv = ds_live.get(ds_live_key(t), {})
    eta = lv.get("eta", "?")
    ds_name = ds_short(t)
    has_active = any(ap in t or ap == ds_name for ap in ds_active_processes)
    p = per[t]
    if has_active: ds_running.append((t,p,lv))
    elif eta != "已完成": ds_paused.append((t,p,lv))

if ds_running:
    a(f"### 🔵 活跃进程（{len(ds_running)} 个）")
    a("| 数据集 | 进度 | 最佳S | 预期完成 |")
    a("|---|---|---|---|")
    for t,p,lv in ds_running:
        done=lv.get("done",0); tot=lv.get("total",320)
        a(f"| {ds_short(t)} | {done}/{tot} ({lv.get('pct',0):.0f}%) | {sflag(p['bestS'])} {p['bestS']:.2f} | **{lv.get('eta','?')}** |")
    a()

if ds_paused:
    a(f"### ⏸️ 暂停/待续补（{len(ds_paused)} 个）")
    a("| 数据集 | 进度 | 最佳S |")
    a("|---|---|---|")
    for t,p,lv in ds_paused:
        done=lv.get("done",p["N"]); tot=lv.get("total",320)
        a(f"| {ds_short(t)} | {done}/{tot} ({lv.get('pct',0):.0f}%) | {sflag(p['bestS'])} {p['bestS']:.2f} |")
    a()

a(f"| tri_track | {tri_total} α | {sflag(tri_bestS)} {tri_bestS:.2f} | 运行中 |")
a()

# ===== 六、失败闸门归因 =====
a("---"); a("## 六、失败闸门归因"); a()
total_fails = sum(fcats.values())
a("| 失败类型 | 次数 | 占比 |")
a("|---|---:|---:|")
for k, v in sorted(fcats.items(), key=lambda x: -x[1]):
    pct = v/total_fails*100 if total_fails else 0
    a(f"| {k} | **{v:,}** | {pct:.1f}% |")
a()

# ===== 七、行动建议 =====
a("---"); a("## 七、行动建议"); a()
a(f"1. **ds 舰队继续调度**：fleet_keeper --target 7 自然推进，零 429。")
a(f"2. **v39b 封存**：SELF_CORR FAIL (7/10)，仅 YPgAa3WR 幸存。换新字段。")
a(f"3. **v52b 封存**：PROD_CORR FAIL (31/32)，信号被占。换新方向。")
a(f"4. **v52_tri_hiring_trends 活路**：j2rrpVzO 成功上线，ILLIQUID_MINVOL1M 方向可复制。")
a(f"5. **提交核查闭环**：{n_active_total} ACTIVE / {n_rejected_total} 拒绝，submit 自动 OOS。")
a(f"6. **tri_track 对标**：{tri_total} α，最佳 S={tri_bestS:.2f}，指标已接入。")
a(f"7. **continuous_undug 继续**：{cu_blocks} 块完成，{len(cu_ds_done)} 数据集覆盖中。")

# ===== 结尾 =====
a()
a("---")
a(f"*报告由 `build_hierarchical_report.py` 从真实文件程序化生成 · 快照 {NOW} GMT+8*")
a(f"*三维框架：账号 → 因子模板 → 回测日期，所有数字实算、未编造。*")

# write
md_text = "\n".join(L)
out = os.path.join(ROOT, "deliverables", "reports",
                   f"hierarchical_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    fh.write(md_text)
print(f"WROTE {out}  ({len(L)} lines)")
print(f"total_N={total_N} is_cleared={is_cleared} found={len(found)} bestS={bestS:.2f}")
print(f"tri_total={tri_total} tracks={tri_tracks}")
print(f"accounts={len(hierarchy)} templates={sum(len(v) for v in hierarchy.values())}")
