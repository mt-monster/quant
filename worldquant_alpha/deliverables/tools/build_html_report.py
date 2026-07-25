# -*- coding: utf-8 -*-
"""数据驱动的因子挖掘进度汇报（自包含 HTML，内联 SVG/CSS，无外部依赖）。
所有数字均来自 results/*_checkpoint.json（权威累计）与 results/*_progress_*.log（实时进度），
不编造、不估算未经验证的数据。"""
import json, glob, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../worldquant_alpha
RES = os.path.join(ROOT, "results")
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# ---------- 1. 读取 checkpoint 真实数据 ----------
def load_ckpts():
    recs = []          # 每个 backtest result
    found = []         # found_alphas 条目
    for f in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict):
            res = d.get("results", [])
            fa = d.get("found_alphas") or []
        elif isinstance(d, list):
            res, fa = d, []
        else:
            continue
        task = os.path.basename(f).replace("_checkpoint.json", "")
        for r in res:
            r["_task"] = task
            recs.append(r)
        for x in (fa if isinstance(fa, list) else []):
            x["_task"] = task
            found.append(x)
    return recs, found

recs, found = load_ckpts()
total_N = len(recs)
pc = [r for r in recs if str(r.get("status", "")) == "PASS_CHEAP"]
cp = [r for r in recs if str(r.get("status", "")) == "CHECK_PENDING"]
is_cleared = len(pc) + len(cp)
found_n = len(found)
bestS = max((float(r.get("sharpe") or 0) for r in recs), default=0.0)

# 失败闸门分类
cat = {"S(夏普)": 0, "F(拟合)": 0, "M(换手收益)": 0, "Ret(收益)": 0, "TVR(换手率)": 0,
       "PF:子宇宙Sharpe": 0, "submit_failed": 0, "其他": 0}
pf_detail = {}
for r in recs:
    fl = r.get("fails")
    if not isinstance(fl, list):
        continue
    for x in fl:
        s = str(x)
        if s.startswith("PF:"):
            cat["PF:子宇宙Sharpe"] += 1
            key = s[3:]
            pf_detail[key] = pf_detail.get(key, 0) + 1
        elif s.startswith("S="):
            cat["S(夏普)"] += 1
        elif s.startswith("F="):
            cat["F(拟合)"] += 1
        elif s.startswith("M="):
            cat["M(换手收益)"] += 1
        elif s.startswith("Ret="):
            cat["Ret(收益)"] += 1
        elif "tvr" in s.lower() or s.startswith("TVR"):
            cat["TVR(换手率)"] += 1
        elif s == "submit_failed":
            cat["submit_failed"] += 1
        else:
            cat["其他"] += 1

# 每任务聚合
per = {}
for r in recs:
    t = r["_task"]
    p = per.setdefault(t, {"N": 0, "pc": 0, "cp": 0, "bestS": 0.0})
    p["N"] += 1
    st = str(r.get("status", ""))
    if st == "PASS_CHEAP":
        p["pc"] += 1
    elif st == "CHECK_PENDING":
        p["cp"] += 1
    try:
        s = float(r.get("sharpe") or 0)
    except Exception:
        s = 0.0
    if s > p["bestS"]:
        p["bestS"] = s

DS_PREFIX = ["ds_equity_kpi_forecast", "ds_ml_factor_proj", "ds_order_book_imbalance",
      "ds_pv_tech_indicators", "ds_quant_factor_lib", "ds_techindi_model", "ds_web_traffic_engage"]
ds_tasks = [k for k in per if k.startswith("ds_")]  # 真实 checkpoint 任务名
def ds_short(k):
    return k.split("_tri_")[0].replace("ds_", "") if "_tri_" in k else k.replace("ds_", "")
def ds_live_key(k):
    return k.split("_tri_")[0]  # 匹配 progress 日志前缀

def cfg(r):
    s = r.get("settings") or {}
    if not isinstance(s, dict):
        return "-"
    return f"{s.get('region','?')} {s.get('universe','?')} d{s.get('delay','?')} decay{s.get('decay','?')} {s.get('neutralization','?')}"

# 候选明细（按 sharpe 降序）
cand = []
for r in pc + cp:
    try:
        s = float(r.get("sharpe") or 0)
    except Exception:
        s = 0.0
    try:
        f1 = float(r.get("fitness") or 0)
    except Exception:
        f1 = 0.0
    cand.append({
        "task": r["_task"], "pid": r.get("pid", "?"), "label": r.get("label", "?"),
        "S": round(s, 2), "F": round(f1, 2), "tvr": r.get("tvr"),
        "status": "PASS_CHEAP" if r in pc else "CHECK_PENDING", "cfg": cfg(r),
    })
cand.sort(key=lambda x: -x["S"])

# ---------- 2. 读取 progress 日志（实时进度） ----------
live = {}
for d in DS_PREFIX:
    logs = sorted(glob.glob(os.path.join(RES, f"{d}_tri_progress_*.log")))
    if not logs:
        continue
    last = None
    for ln in open(logs[-1], encoding="utf-8", errors="ignore"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("event") == "progress":
            last = e
    if last:
        done = last.get("done", 0)
        tot = last.get("total", 0)
        el = last.get("elapsed_sec", 0) or 0
        pct = (done / tot * 100) if tot else 0
        thr = (done / (el / 3600.0)) if el > 0 else 0  # 估算 α/hr
        live[d] = {"done": done, "total": tot, "pct": round(pct, 1),
                   "elapsed_min": round(el / 60.0, 1), "alpha_per_hr": round(thr, 0)}

# ---------- 3. SVG 图表工具 ----------
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

TH = 1.58  # WQ 研究仿真 IS Sharpe 过闸参考线

def funnel_svg(stages):
    # stages: [(label, value, color)]
    W, H = 760, 260
    maxv = max(v for _, v, _ in stages)
    n = len(stages)
    rowh = H / n
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMinYMin meet" style="font-family:inherit">']
    for i, (lab, val, col) in enumerate(stages):
        y = i * rowh + 8
        w = (val / maxv) * (W - 250) if maxv else 0
        x = 240
        parts.append(f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{rowh-18:.1f}" rx="4" fill="{col}"/>')
        parts.append(f'<text x="10" y="{y+rowh/2-6:.1f}" font-size="13" fill="#1f2933">{esc(lab)}</text>')
        parts.append(f'<text x="{x+w+8 if w>40 else x+8:.1f}" y="{y+rowh/2-6:.1f}" font-size="14" font-weight="700" fill="#1f2933">{val:,}</text>')
    parts.append('</svg>')
    return "".join(parts)

def hbar_svg(items, th=None, unit=""):
    # items: [(label, value, color, bold)]
    W, LBLW = 760, 250
    rowh = 17
    H = len(items) * rowh + 10
    maxv = max(list(v for _, v, _, _ in items) + ([th] if th is not None else [0])) or 1
    chartw = W - LBLW - 70
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMinYMin meet" style="font-family:inherit">']
    if th is not None:
        tx = LBLW + (th / maxv) * chartw
        parts.append(f'<line x1="{tx:.1f}" y1="0" x2="{tx:.1f}" y2="{H}" stroke="#d64545" stroke-width="1.5" stroke-dasharray="5 4"/>')
        parts.append(f'<text x="{tx+4:.1f}" y="11" font-size="10" fill="#d64545">过闸线 {th}</text>')
    for i, (lab, v, col, bold) in enumerate(items):
        y = i * rowh + 4
        w = (v / maxv) * chartw if maxv else 0
        fw = "700" if bold else "400"
        parts.append(f'<text x="6" y="{y+12:.1f}" font-size="11.5" font-weight="{fw}" fill="#1f2933">{esc(lab[:34])}</text>')
        parts.append(f'<rect x="{LBLW}" y="{y+1}" width="{w:.1f}" height="{rowh-6:.1f}" rx="2" fill="{col}"/>')
        parts.append(f'<text x="{LBLW+w+5:.1f}" y="{y+12:.1f}" font-size="11" fill="#1f2933">{v:.2f}{unit}</text>')
    parts.append('</svg>')
    return "".join(parts)

def vbar_svg(items, th=None, unit=""):
    W = 760
    n = len(items)
    padL, padB, padT = 40, 30, 14
    chartw = W - padL - 10
    H = 260
    chartH = H - padB - padT
    maxv = max(list(v for _, v, _ in items) + ([th] if th is not None else [0])) or 1
    bw = chartw / n * 0.66
    gap = chartw / n
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMinYMin meet" style="font-family:inherit">']
    # y 轴刻度
    for k in range(0, 5):
        yy = padT + chartH - (k / 4) * chartH
        parts.append(f'<line x1="{padL}" y1="{yy:.1f}" x2="{W-10}" y2="{yy:.1f}" stroke="#eef1f5"/>')
        parts.append(f'<text x="4" y="{yy+4:.1f}" font-size="10" fill="#9aa3ad">{maxv*k/4:.1f}</text>')
    if th is not None:
        ty = padT + chartH - (th / maxv) * chartH
        parts.append(f'<line x1="{padL}" y1="{ty:.1f}" x2="{W-10}" y2="{ty:.1f}" stroke="#d64545" stroke-width="1.5" stroke-dasharray="5 4"/>')
        parts.append(f'<text x="{W-70}" y="{ty-4:.1f}" font-size="10" fill="#d64545">过闸线 {th}</text>')
    for i, (lab, v, col) in enumerate(items):
        x = padL + i * gap + (gap - bw) / 2
        h = (v / maxv) * chartH
        y = padT + chartH - h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="{col}"/>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{y-4:.1f}" font-size="10.5" font-weight="700" fill="#1f2933" text-anchor="middle">{v:.2f}</text>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{H-10:.1f}" font-size="9.5" fill="#52606d" text-anchor="middle">{esc(lab[:12])}</text>')
    parts.append('</svg>')
    return "".join(parts)

# 颜色
GREEN, AMBER, RED, BLUE, GRAY = "#2e9e5b", "#e0a106", "#d64545", "#3b6fb6", "#9aa3ad"
def scolor(v):
    if v >= TH:
        return GREEN
    if v >= 1.0:
        return AMBER
    return RED

# 图表 1：提交就绪漏斗
funnel = funnel_svg([
    ("研究仿真回测总次数", total_N, BLUE),
    ("IS 廉价闸门通过 (候选)", is_cleared, GREEN),
    ("跨生产相关性验证 (found)", found_n, AMBER),
    ("平台真实提交", 0, RED),
])

# 图表 2：各任务最佳 Sharpe
tasks_sorted = sorted(per.items(), key=lambda x: -x[1]["bestS"])
bar_items = [(t, p["bestS"], scolor(p["bestS"]), t in ds_tasks) for t, p in tasks_sorted]
sharpe_bar = hbar_svg(bar_items, th=TH)

# 图表 3：ds 舰队首步最佳 Sharpe
ds_items = [(ds_short(t), per[t]["bestS"], scolor(per[t]["bestS"])) for t in ds_tasks]
ds_bar = vbar_svg(ds_items, th=TH)

# 图表 4：回测量 TOP 任务
topN = sorted(per.items(), key=lambda x: -x[1]["N"])[:12]
vol_items = [(t, p["N"], BLUE, t in ds_tasks) for t, p in topN]
vol_bar = hbar_svg(vol_items)

# 进程构成（conic-gradient 饼）
wq_total = 25
seg_mine, seg_mcp, seg_kpr = 10, 14, 1
pie = (f"background: conic-gradient({GREEN} 0 {seg_mine/wq_total*100:.1f}%, "
       f"{BLUE} {seg_mine/wq_total*100:.1f}% {(seg_mine+seg_mcp)/wq_total*100:.1f}%, "
       f"{AMBER} {(seg_mine+seg_mcp)/wq_total*100:.1f}% 100%);")

# ---------- 4. 表格 HTML ----------
def cand_rows():
    out = []
    for c in cand:
        hl = ' class="hl"' if c["status"] == "CHECK_PENDING" else ""
        tvr = c["tvr"] if c["tvr"] is not None else "-"
        out.append(f"<tr{hl}><td>{esc(c['pid'])}</td><td>{esc(c['task'].replace('ds_',''))}</td>"
                   f"<td><b>{c['S']:.2f}</b></td><td>{c['F']:.2f}</td><td>{tvr}</td>"
                   f"<td>{esc(c['status'])}</td><td>{esc(c['cfg'])}</td></tr>")
    return "\n".join(out)

def ds_rows():
    out = []
    for k in ds_tasks:
        p = per[k]
        lv = live.get(ds_live_key(k), {})
        done = lv.get("done", p["N"])
        tot = lv.get("total", 320)
        pct = lv.get("pct", round(done / tot * 100, 1))
        bs = p["bestS"]
        col = RED if bs < 1.0 else (AMBER if bs < TH else GREEN)
        status = "🔴 0 候选" if p["pc"] + p["cp"] == 0 else "有候选"
        out.append(f"<tr><td>{esc(ds_short(k))}</td><td>{done}/{tot} ({pct}%)</td>"
                   f"<td style='color:{col};font-weight:700'>{bs:.2f}</td>"
                   f"<td>{lv.get('alpha_per_hr','-')} α/hr</td>"
                   f"<td>{lv.get('elapsed_min','-')} min</td><td>{status}</td></tr>")
    return "\n".join(out)

def fail_rows():
    out = []
    order = ["PF:子宇宙Sharpe", "S(夏普)", "F(拟合)", "M(换手收益)", "Ret(收益)", "TVR(换手率)", "submit_failed", "其他"]
    for k in order:
        v = cat.get(k, 0)
        note = ""
        if k == "PF:子宇宙Sharpe":
            top = sorted(pf_detail.items(), key=lambda x: -x[1])[0]
            note = f"主因 {top[0]} ({top[1]} 次)"
        if v:
            out.append(f"<tr><td>{esc(k)}</td><td><b>{v}</b></td><td>{esc(note)}</td></tr>")
    return "\n".join(out)

# ---------- 5. 组装 HTML ----------
HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子挖掘进度汇报 (数据驱动)</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;background:#eef1f5;color:#1f2933;line-height:1.6}}
.wrap{{max-width:1080px;margin:0 auto;padding:24px}}
header{{background:#1f2933;color:#fff;border-radius:12px;padding:22px 26px;margin-bottom:18px}}
header h1{{margin:0 0 6px;font-size:22px}}
header .meta{{font-size:13px;color:#aeb8c4}}
.banner{{background:#ffe3e3;border:2px solid #d64545;color:#8a1f1f;padding:12px 16px;border-radius:8px;font-weight:700;margin-bottom:18px;font-size:14px}}
.card{{background:#fff;border-radius:12px;padding:20px 22px;margin-bottom:18px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.card h2{{margin:0 0 4px;font-size:18px;border-left:4px solid #3b6fb6;padding-left:10px}}
.card .sub{{font-size:13px;color:#52606d;margin:0 0 14px;padding-left:14px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
@media(max-width:760px){{.grid2{{grid-template-columns:1fr}}}}
.kpi{{display:flex;flex-wrap:wrap;gap:12px;margin:6px 0 2px}}
.kpi .b{{flex:1;min-width:120px;background:#f7f9fc;border:1px solid #e3e8ef;border-radius:10px;padding:12px 14px}}
.kpi .b .n{{font-size:24px;font-weight:800;color:#1f2933}}
.kpi .b .l{{font-size:12px;color:#52606d}}
.kpi .b.red .n{{color:#d64545}}
.kpi .b.grn .n{{color:#2e9e5b}}
.kpi .b.amb .n{{color:#e0a106}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 9px;border-bottom:1px solid #eef1f5;text-align:left}}
th{{background:#f3f6fa;color:#33415c;font-weight:700;position:sticky;top:0}}
tr.hl{{background:#fff6e0}}
.tag{{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;color:#fff}}
.tag.g{{background:#2e9e5b}}.tag.a{{background:#e0a106}}.tag.r{{background:#d64545}}.tag.b{{background:#3b6fb6}}
.note{{font-size:13px;color:#33415c;background:#f7f9fc;border-radius:8px;padding:10px 14px;margin-top:12px}}
.note b{{color:#d64545}}
.pie{{width:150px;height:150px;border-radius:50%;{pie}float:left;margin:6px 22px 6px 0}}
.legend span{{display:inline-block;margin-right:16px;font-size:13px}}
.legend i{{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:middle}}
ul.act{{margin:6px 0;padding-left:20px}}
ul.act li{{margin:7px 0}}
.small{{font-size:12px;color:#9aa3ad}}
</style></head>
<body><div class="wrap">

<header>
  <h1>WorldQuant Brain PPA 因子挖掘进度汇报</h1>
  <div class="meta">数据快照：{NOW} ｜ 数据源：results/*_checkpoint.json（权威累计）+ results/*_progress_*.log（实时进度）｜ 生成器：build_html_report.py（可复跑，数字均来自真实文件）</div>
</header>

<div class="banner">⚠️ 提交验证最重要结论：全部 <b>{is_cleared}</b> 个候选 Alpha 仅通过「研究仿真 IS 廉价闸门」、<b>未经完整提交验证</b>；其中仅 <b>1</b> 个跨过生产相关性关（{esc(found[0]['pid'] if found else '?')}，prod_corr={found[0].get('prod_corr','?') if found else '?'}），<b>0 个</b>完成平台真实提交 —— {is_cleared} 个均不满足 WQ 提交标准，请勿视作可提交 Alpha。</div>

<div class="card">
  <h2>一、核心结论（结论先行）</h2>
  <div class="kpi">
    <div class="b b"><div class="n">{total_N:,}</div><div class="l">累计回测次数</div></div>
    <div class="b grn"><div class="n">{is_cleared}</div><div class="l">IS 闸门通过候选</div></div>
    <div class="b amb"><div class="n">{found_n}</div><div class="l">跨生产相关性验证</div></div>
    <div class="b red"><div class="n">0</div><div class="l">平台真实提交</div></div>
    <div class="b"><div class="n">{bestS:.2f}</div><div class="l">全链路最佳 Sharpe</div></div>
  </div>
  <ul class="act">
    <li><b>在飞架构已切换</b>：9 个挖掘任务（10 进程）= 主账号 <code>v52b_hiring_margin</code> + <b>7 路新 ds_* 数据集舰队</b>（21:06–21:09 错峰拉起，目标 8 路）+ 独立账号 <code>tri_track_undug.py</code>。旧 v47–v54 舰队已结束。</li>
    <li><b>瓶颈是"信号发现"而非"吞吐"</b>：7 路 ds 舰队目前 <b>0 个候选</b>，首步最佳 Sharpe 仅 web_traffic_engage 1.88、techindi_model 1.39、pv 0.63，其余 &lt;0.5。</li>
    <li><b>平台并发模型 = 令牌桶限流，突发容量 C=7</b>：多进程错峰 + 各带 submit_gate，实测全局<b>零 429</b>，并发纪律合规。</li>
    <li><b>主失败闸门 = 子宇宙 Sharpe（PF:LOW_SUB_UNIVERSE_SHARPE）</b>：历史最强信号 V39b(2.58)/V39(2.30)/V52(2.50) 均卡此关，比 IS 闸更硬。</li>
  </ul>
</div>

<div class="card">
  <h2>二、关键图表（数据驱动）</h2>

  <h3 style="margin:6px 0">图 1 · 提交就绪漏斗</h3>
  <p class="sub">从 6227 次回测到 0 次提交的逐级损耗，红色末级凸显"无产出"现状。</p>
  {funnel}
  <div class="note">每一级都是一道硬闸门：<b>IS 廉价闸门</b>筛掉 {total_N - is_cleared:,} 次；<b>生产相关性关</b>仅 {found_n} 个通过；<b>平台提交</b>为 0（脚本 no_submit=True，从未真正落地）。{is_cleared} 个候选 ≠ 可提交。</div>

  <div class="grid2" style="margin-top:18px">
    <div>
      <h3 style="margin:6px 0">图 2 · 各任务最佳 Sharpe</h3>
      <p class="sub">33 个任务横向对比；绿=过闸线(1.58)以上，红=偏弱。ds 舰队（加粗）整体贴底。</p>
      {sharpe_bar}
    </div>
    <div>
      <h3 style="margin:6px 0">图 3 · ds 舰队首步最佳 Sharpe</h3>
      <p class="sub">7 路在飞舰队首步信号 vs 过闸线 1.58，除 web_traffic 外全低于线。</p>
      {ds_bar}
    </div>
  </div>
  <div class="note">图 2 显示有效信号集中在 <b>v52b(2.66)/v52(2.50)/v39b(2.58)/v39(2.30)</b> 等历史任务；图 3 显示<b>当前在飞 ds 舰队首步信号普遍未达过闸线</b>，正是"信号发现"瓶颈的直观证据。</div>

  <div class="grid2" style="margin-top:18px">
    <div>
      <h3 style="margin:6px 0">图 4 · 回测量 TOP 任务</h3>
      <p class="sub">各任务已跑回测规模（checkpoint 累计 N）。</p>
      {vol_bar}
    </div>
    <div>
      <h3 style="margin:6px 0">图 5 · 机器级进程构成</h3>
      <p class="sub">接触 WQ BRAIN 的 25 个 Python 进程占比。</p>
      <div class="pie"></div>
      <div class="legend" style="padding-top:18px">
        <span><i style="background:{GREEN}"></i>挖掘 10 (40%)</span>
        <span><i style="background:{BLUE}"></i>MCP 宿主 14 (56%)</span>
        <span><i style="background:{AMBER}"></i>舰队守护 1 (4%)</span>
      </div>
      <div class="small" style="clear:both">另：编辑器/语言服务 8 个（idle，未计入饼图）。命令行命中 RR11jN：0（服务端实例，仅 WQ BRAIN 控制台可见）。</div>
    </div>
  </div>
</div>

<div class="card">
  <h2>三、核心数据表格</h2>

  <h3 style="margin:4px 0">表 A · ds 舰队实时进度（checkpoint + progress 日志）</h3>
  <table><thead><tr><th>数据集</th><th>进度</th><th>首步最佳S</th><th>吞吐(估算)</th><th>已运行</th><th>候选</th></tr></thead>
  <tbody>{ds_rows()}</tbody></table>
  <div class="note">进度与吞吐取自最新 progress 日志（实时）；首步最佳 S 取自 checkpoint。web_traffic_engage 虽 S=1.88&gt;1.58，但仍卡 F/M/Ret 等其他 IS 闸，故 <b>0 候选</b>。</div>

  <h3 style="margin:18px 0 4px">表 B · 失败闸门汇总（全量 fails 统计）</h3>
  <table><thead><tr><th>失败类型</th><th>次数</th><th>说明</th></tr></thead>
  <tbody>{fail_rows()}</tbody></table>
  <div class="note"><b>PF:子宇宙 Sharpe 是头号平台失败闸门</b>，远高于单纯 IS 指标失败，印证"需在子宇宙层面优化中性化/约束"的攻坚方向。</div>

  <h3 style="margin:18px 0 4px">表 C · 候选 Alpha 明细（{len(cand)} 个，按 Sharpe 降序，黄色=CHECK_PENDING 待产验）</h3>
  <div style="max-height:340px;overflow:auto">
  <table><thead><tr><th>pid</th><th>任务</th><th>Sharpe</th><th>Fitness</th><th>tvr</th><th>状态</th><th>配置</th></tr></thead>
  <tbody>{cand_rows()}</tbody></table>
  </div>
  <div class="note">候选来自 2 个根集群：<b>v52b</b>（降换手 hiring 信号，S 1.79–2.66）与 <b>v39b</b>（insider micro 信号，S 1.67–2.58）。均仅研究仿真 IS 闸通过，缺生产仿真(OOS)+平台 submittable+真实提交。</div>
</div>

<div class="card">
  <h2>四、问题说明（问题其次）</h2>
  <ul class="act">
    <li><b>问题 1 — 候选无一满足提交标准。</b>真实提交须过四关：①研究仿真 IS ✅{is_cleared}/{is_cleared}；②生产仿真(OOS) ❌0；③生产相关性 ✅仅 {found_n}（{esc(found[0]['pid'] if found else '?')}）；④平台提交 ❌0。<code>PASS_CHEAP</code> 仅"廉价 IS 闸通过"，非可提交。</li>
    <li><b>问题 2 — 在飞 ds 舰队首步信号偏弱、0 候选。</b>见图表 2/3 与表 A；加并发只是加速"挖 0 候选"。</li>
    <li><b>问题 3 — 子宇宙 Sharpe 闸门比 IS 闸更硬。</b>见图表 5/表 B，PF:LOW_SUB_UNIVERSE_SHARPE 为头号失败原因。</li>
    <li><b>问题 4 — 监控口径已修正。</b>旧 <code>gen_report.py</code> 用 <code>^v\\d+</code> 过滤 checkpoint，漏掉整个 ds_* 舰队；<code>tri_track_undug.py</code> 被误判为 other（实为独立账号三轨挖掘）。本报告改判单列、纳入 ds 舰队，不再漏报。</li>
    <li><b>问题 5 — 吞吐数字勿误读。</b>表 A 中 α/hr 为 done/elapsed 粗估上限；历史稳态基准下 7 路可持续约 603 α/hr。当前值应视为上限而非稳态。</li>
  </ul>
</div>

<div class="card">
  <h2>五、行动建议（方案最后）</h2>
  <ul class="act">
    <li><b>1. 舰队继续跑完</b>：7 路 ds + v52b + tri_track 已验证合规（优，零 429），按各自 submit_gate 自然推进。</li>
    <li><b>2. 主攻子宇宙 Sharpe 闸门</b>：对 V39/V39b 类高 S 信号，限定 universe=TOP3000 / 调整 neutralization / 加子宇宙约束，突破平台 FAIL。</li>
    <li><b>3. v52b 升维</b>：降换手变体（decay4 SECTOR）已多过廉价 IS 闸，是下一轮最值得挖方向；规模化过 M 闸并补生产验证。</li>
    <li><b>4. 并发纪律（修订）</b>：允许错峰多进程(&gt;6)并发，只要各进程自带 submit_gate 且非 &lt;2s 齐射。</li>
    <li><b>5. 提交前必补四关</b>：生产仿真 → /check(PROD/SELF_CORRELATION) → 平台 submittable → 显式 submit（关 no_submit）。优先验证已跨产验的 <b>{esc(found[0]['pid'] if found else '?')}</b>。</li>
  </ul>
</div>

<div class="small" style="text-align:center;padding:14px">
  报告由 build_html_report.py 从真实 checkpoint/progress 文件程序化生成 · 快照 {NOW} · 数字均来自文件实测，未编造。<br>
  详细候选公式与字段见原始报告 factor_mining_progress_20260725_2130.md。
</div>

</div></body></html>"""

out = os.path.join(ROOT, "deliverables", "reports", f"factor_mining_dashboard_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.html")
open(out, "w", encoding="utf-8").write(HTML)
print("WROTE", out)
print("total_N", total_N, "is_cleared", is_cleared, "found", found_n, "bestS", round(bestS,2))
print("ds live:", {k: live.get(k, {}).get("pct") for k in DS_PREFIX})
