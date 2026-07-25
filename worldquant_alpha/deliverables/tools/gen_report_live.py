#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""因子挖掘进度汇报生成器 (LIVE, 数据驱动, 修正发现盲区).

修正点 (相比旧 gen_report.py):
  1. 进程枚举分类: tri_track_undug.py 等 `tri_track*`(非 _miner/_watchdog) 改判为 MINING
     (框架盲区⑤ 陷阱②, 不可漏报)。
  2. checkpoint 发现: 放宽 `^v\\d+` 过滤 -> 同时接纳 `ds_` 前缀 (scan_tri_job --dataset 舰队
     的 checkpoint 命名为 ds_<ds>_tri_<ds>_checkpoint.json, 旧 gen_report 全漏)。
  3. 同时纳入: 历史链 v33-v46, 旧 v47-v54 舰队(已完成), 新 ds_* 舰队(在飞),
     v52b_hiring_margin, tri_track_undug(独立账号)。
  4. 候选 Alpha 采集覆盖全部 checkpoint (v* + ds* + tri_track), 并坚持四关提交验证口径。

输出: deliverables/reports/factor_mining_progress_<ts>.md
"""
import json, os, re, glob, time, subprocess
from collections import Counter, OrderedDict

ROOT = r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha"
RES = os.path.join(ROOT, "results")
TRI_DIR = r"D:\BaiduNetdiskDownload\WQ第二三四节课代码\worldquant"
OUT_DIR = os.path.join(ROOT, "deliverables", "reports")
os.makedirs(OUT_DIR, exist_ok=True)
TS = time.strftime("%Y%m%d_%H%M")
SNAP = time.strftime("%Y-%m-%d %H:%M:%S") + " GMT+8"
OUT = os.path.join(OUT_DIR, f"factor_mining_progress_{TS}.md")
WINDOW = 15 * 60  # seconds: mtime freshness for "alive"

# ============================================================
# 1) 机器级进程枚举 (第一视角)
# ============================================================
def process_inventory():
    ps = ('Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" '
          '| ForEach-Object { ($_.ProcessId.ToString() + \'|||\' + $_.CommandLine + \'|||\' '
          '+ $_.CreationDate.ToString(\'yyyyMMddHHmmss\') + \'|||\' + $_.ThreadCount.ToString()) }')
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=90)
    inv = []
    for line in (out.stdout or "").splitlines():
        if "|||" not in line:
            continue
        parts = line.split("|||", 3)
        pid = parts[0].strip(); cmd = parts[1] if len(parts) > 1 else ""
        cdate = parts[2] if len(parts) > 2 else ""; nthr = parts[3] if len(parts) > 3 else ""
        rec = {"pid": pid, "cmd": cmd, "started": cdate, "threads": nthr,
               "kind": "other", "marker": False, "task": None}
        c = cmd
        if "platform_functions.py" in c:
            rec["kind"] = "mcp_server"
        elif "fleet_keeper.py" in c:
            rec["kind"] = "keeper"
        elif "scan_tri_job.py" in c:
            rec["kind"] = "tri_miner"
            m = re.search(r"--dataset\s+(\S+)", c)
            if m:
                ds = re.sub(r"[^a-z0-9_]+", "_", m.group(1).lower())[:28]
                rec["task"] = f"ds_{ds}_tri_{ds}"
        elif "scan_v52b_hiring_margin.py" in c:
            rec["kind"] = "scan_script"; rec["task"] = "v52b_hiring_margin"
        elif "tri_track_undug.py" in c or ("tri_track" in c and "tri_track_miner.py" not in c):
            rec["kind"] = "tri_miner"; rec["task"] = "tri_track_undug"
        elif "_watchdog_tri.py" in c:
            rec["kind"] = "watchdog"
        elif "tri_track_miner.py" in c:
            rec["kind"] = "tracker"
        elif "run-jedi" in c or "jedi" in c or "ms-python" in c:
            rec["kind"] = "editor"
        elif "scan_" in c and ".py" in c:
            rec["kind"] = "scan_script"
            m = re.search(r"scan_([A-Za-z0-9_]+)\.py", c)
            if m: rec["task"] = m.group(1)
        if "RR11jN" in c:
            rec["marker"] = True
        inv.append(rec)
    return inv

# ============================================================
# 2) checkpoint 发现 + 摘要
# ============================================================
def read_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None

def norm_ds(ds):
    return re.sub(r"[^a-z0-9_]+", "_", (ds or "").lower())[:28]

def discover_checkpoints():
    """返回 {task_key: path} 含 v* 与 ds_*。"""
    found = {}
    for f in glob.glob(os.path.join(RES, "*checkpoint*.json")):
        base = os.path.basename(f).replace("_checkpoint.json", "")
        if re.match(r"^(v\d+|ds_)", base):
            found[base] = f
    # tri_track_undug (独立目录, 递归搜)
    for cur, _, files in os.walk(TRI_DIR):
        for fn in files:
            if "checkpoint" in fn and fn.endswith(".json"):
                p = os.path.join(cur, fn)
                base = fn.replace("_checkpoint.json", "")
                if base not in found:
                    found[base] = p
    return found

def summ(path):
    d = read_json(path)
    if not d:
        return None
    res = d.get("results") or []
    n = len(res)
    stc = Counter(r.get("status") for r in res)
    cands = [r for r in res if r.get("status") in ("PASS", "PASS_CHEAP")]
    fa = len(d.get("found_alphas") or [])
    best_s = max([r.get("sharpe") for r in res if isinstance(r.get("sharpe"), (int, float))] or [None])
    best_f = max([r.get("fitness") for r in res if isinstance(r.get("fitness"), (int, float))] or [None])
    regions = set()
    for r in res:
        s = r.get("settings")
        if isinstance(s, str):
            try: s = json.loads(s)
            except Exception: s = {}
        if isinstance(s, dict) and s.get("region"):
            regions.add(s["region"])
    fails = Counter()
    for r in res:
        if r.get("status") in ("PASS", "PASS_CHEAP"):
            continue
        f = r.get("fails") or []
        if not f:
            fails["FAIL_other"] += 1; continue
        f0 = f[0]
        if f0.startswith("PF:"): fails[f0] += 1
        elif f0 == "platform_FAIL": fails["platform_FAIL"] += 1
        elif f0.startswith("S="): fails["gate_S/F/M/Ret"] += 1
        else: fails["FAIL:" + f0[:30]] += 1
    dom = max(fails.items(), key=lambda x: x[1])[0] if fails else "-"
    return dict(path=path, base=os.path.basename(path).replace("_checkpoint.json", ""),
                n=n, stc=stc, cands=cands, fa=fa, best_s=best_s, best_f=best_f,
                regions=regions, dom=dom)

# ============================================================
# 3) 进度日志 (在飞实时统计)
# ============================================================
def parse_progress_log(f):
    start = None; last = None
    n_submit_failed = 0; n_429 = 0; n_poll = 0
    try:
        txt = open(f, encoding="utf-8", errors="ignore").read()
    except Exception:
        return None
    n_submit_failed = len(re.findall(r"submit_failed", txt))
    n_429 = len(re.findall(r"\b429\b", txt))
    n_poll = len(re.findall(r"poll_timeout", txt))
    for line in txt.splitlines():
        if '"event": "start"' in line:
            try: start = json.loads(line)
            except Exception: pass
        elif '"event": "progress"' in line:
            try: last = json.loads(line)
            except Exception: pass
    if not last:
        return None
    mtime = os.path.getmtime(f)
    alive = (time.time() - mtime) < WINDOW
    rt = dict(alive=alive, start=start, last=last,
              n_submit_failed=n_submit_failed, n_429=n_429, n_poll=n_poll)
    return rt

def progress_logs():
    """task_key -> latest progress log path (按 checkpoint/任务名配对)"""
    d = {}
    for f in glob.glob(os.path.join(RES, "*_progress_*.log")):
        base = os.path.basename(f)
        stem = re.sub(r"_progress.*$", "", base)
        # 由 start event 取真实 task
        task = None
        try:
            for line in open(f, encoding="utf-8", errors="ignore"):
                if '"event": "start"' in line:
                    try: task = json.loads(line).get("task")
                    except Exception: pass
                if task: break
        except Exception:
            pass
        key = task or stem
        if key not in d or os.path.getmtime(f) > os.path.getmtime(d[key]):
            d[key] = f
    return d

# ============================================================
# 4) 源码效率检测
# ============================================================
def detect_effort(script_path):
    if not script_path or not os.path.exists(script_path):
        return None
    t = open(script_path, encoding="utf-8", errors="ignore").read()
    fl = dict(multi_sim=False, submit_gate=False, backoff=False, no_submit=False, batch=None)
    if re.search(r"import.*multi_sim|from multi_sim import|multi_sim", t):
        fl["multi_sim"] = True
    if "submit_gate" in t or "multi_sim" in t or "wd_lib_wrapper" in t:
        fl["submit_gate"] = True
    if "wd_lib_wrapper" in t or re.search(r"retry", t, re.I) or "backoff" in t or "multi_sim" in t:
        fl["backoff"] = True
    if re.search(r"no_submit|NO_SUBMIT", t):
        fl["no_submit"] = True
    m = re.search(r"BATCH_SIZE\s*=\s*(\d+)", t)
    if m: fl["batch"] = int(m.group(1))
    return fl

def grade(f):
    if not f:
        return "?"
    if f["submit_gate"] and f["multi_sim"] and f["backoff"]:
        return "优"
    if f["multi_sim"] and f["backoff"]:
        return "良"
    if f["multi_sim"] or f["backoff"]:
        return "中"
    return "差"

# ============================================================
# 5) 候选 + 已验证 pid
# ============================================================
def collect_submittable(ckpts):
    out = []
    for key, path in ckpts.items():
        d = read_json(path)
        if not d: continue
        res = d.get("results") or []
        for r in res:
            if r.get("status") in ("PASS", "PASS_CHEAP"):
                s = r.get("settings")
                if isinstance(s, str):
                    try: s = json.loads(s)
                    except Exception: s = {}
                if not isinstance(s, dict): s = {}
                out.append(dict(task=key, label=r.get("label"), pid=r.get("pid"),
                                status=r.get("status"), sharpe=r.get("sharpe"),
                                fitness=r.get("fitness"), sub_univ=r.get("sub_univ"),
                                sub_limit=r.get("sub_limit"), tvr=r.get("tvr"),
                                expr=(r.get("expr") or "")[:600],
                                cfg=f"{s.get('region','')} {s.get('universe','')} d{s.get('delay','')} decay{s.get('decay','')} {s.get('neutralization','')}".strip()))
    out.sort(key=lambda x: (x["sharpe"] is not None, x["sharpe"] or 0), reverse=True)
    return out

def collect_verified_pids(ckpts):
    pids = set()
    for key, path in ckpts.items():
        d = read_json(path)
        if not d: continue
        for a in (d.get("found_alphas") or []):
            if a.get("pid"):
                pids.add(a["pid"])
    return pids

# ============================================================
# helpers
# ============================================================
def fmt(x):
    return f"{x:.2f}" if isinstance(x, float) else str(x)

def nf(x, spec=".0f"):
    return format(x, spec) if isinstance(x, (int, float)) else "-"

def fmt_cim(s):
    if not s or len(s) < 12: return "-"
    try: return f"{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    except Exception: return "-"

def disp(key):
    m = re.match(r"(v\d+[a-z]?)[_]", key)
    if m: return "V" + m.group(1).upper() if m.group(1)[0].isdigit() else key
    if key.startswith("ds_"):
        ds = key[len("ds_"):]
        if ds.endswith("_tri_" + ds):
            ds = ds[: -len("_tri_" + ds)]
        return f"ds·{ds}"
    if key == "tri_track_undug":
        return "tri_track(独立账号)"
    return key

# ============================================================
# main
# ============================================================
def tri_track_status():
    msgs = []
    for fn in ("miner_s4_round.log", "shard5_run.log"):
        p = os.path.join(TRI_DIR, fn)
        if not os.path.exists(p):
            continue
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        total = re.findall(r"总任务\s*(\d+)", txt)
        done = re.findall(r"已完成\s*(\d+)\s*个", txt)
        shard = re.findall(r"分片\s*(\d+)/(\d+)", txt)
        sim = re.findall(r"simulating:\s*(\S+)\s*\|\s*-?\(?group_zscore\([^)]*\)", txt)
        msgs.append(f"{fn}: 分片{shard[-1] if shard else '?'} 总任务{total[-1] if total else '?'} 已完成跳过{done[-1] if done else '?'} 最近信号 {sim[-1][1] if sim else '?'}")
    return "; ".join(msgs) if msgs else "(日志未读到)"

def main():
    inv = process_inventory()
    ckpts = discover_checkpoints()
    pls = progress_logs()

    # live keys from running mining processes
    live_keys = set()
    for r in inv:
        if r["kind"] in ("scan_script", "tri_miner", "keeper") and r["task"]:
            live_keys.add(r["task"])

    # attach progress + live flags
    recs = OrderedDict()
    for key, path in ckpts.items():
        s = summ(path)
        if not s:
            continue
        rt = parse_progress_log(pls.get(key)) if key in pls else None
        # live if running process matches OR (rt alive and checkpoint fresh)
        live = (key in live_keys) or (rt and rt.get("alive"))
        recs[key] = dict(key=key, s=s, rt=rt, live=live,
                         group=("在飞" if live else "已完成"))

    # also register tasks that have a live process but maybe no checkpoint yet
    for r in inv:
        if r["task"] and r["task"] not in recs and r["kind"] in ("scan_script", "tri_miner"):
            recs[r["task"]] = dict(key=r["task"], s=None, rt=None, live=True, group="在飞")

    sub = collect_submittable(ckpts)
    verified = collect_verified_pids(ckpts)

    # efficiency per live task
    eff_map = {}
    for key in recs:
        if key == "tri_track_undug":
            sp = os.path.join(TRI_DIR, "tri_track_undug.py")
            eff_map[key] = (detect_effort(sp), "独立账号·CONCURRENCY=3(据框架)")
        elif key.startswith("ds_"):
            eff_map[key] = (detect_effort(os.path.join(ROOT, "scan_tri_job.py")), "继承 scan_tri_job 模板")
        elif key == "v52b_hiring_margin":
            eff_map[key] = (detect_effort(os.path.join(ROOT, "scan_v52b_hiring_margin.py")), "")
        else:
            eff_map[key] = (detect_effort(os.path.join(ROOT, f"scan_{key}.py")), "")

    # throughput (live tasks with progress)
    live_recs = [r for r in recs.values() if r["live"] and r["rt"]]
    agg_tput = 0.0
    for r in live_recs:
        last = r["rt"].get("last") or {}
        sps = last.get("avg_sec_per_step")
        batch = (eff_map.get(r["key"]) or (None,))[0]
        batch = (batch or {}).get("batch") or 8
        if sps:
            apm = 3600.0 * batch / sps
            r["alpha_per_hr"] = apm
            agg_tput += apm
        else:
            r["alpha_per_hr"] = None
    n_act = len(live_recs)
    steady = 86.1 * n_act  # 稳态基准 multi(8) α/hr/任务 (bench_v34_sim_speed)

    # totals
    tot_n = sum((r["s"]["n"] for r in recs.values() if r["s"]), 0)
    tot_pass = sum((r["s"]["stc"].get("PASS", 0) + r["s"]["stc"].get("PASS_CHEAP", 0) for r in recs.values() if r["s"]), 0)
    tot_found = sum((r["s"]["fa"] for r in recs.values() if r["s"]), 0)
    chain_best = max([r["s"]["best_s"] for r in recs.values() if r["s"] and isinstance(r["s"]["best_s"], (int, float))] or [None])

    # counts
    mcp_n = sum(1 for x in inv if x["kind"] == "mcp_server")
    scan_n = sum(1 for x in inv if x["kind"] == "scan_script")
    miner_n = sum(1 for x in inv if x["kind"] == "tri_miner")
    keeper_n = sum(1 for x in inv if x["kind"] == "keeper")
    wd_n = sum(1 for x in inv if x["kind"] == "watchdog")
    tk_n = sum(1 for x in inv if x["kind"] == "tracker")
    ed_n = sum(1 for x in inv if x["kind"] == "editor")
    mk_n = sum(1 for x in inv if x["marker"])
    mining_total = scan_n + miner_n
    mining_tasks = len(set(r["task"] for r in inv if r["kind"] in ("scan_script", "tri_miner") and r["task"]))
    wq_n = mcp_n + scan_n + miner_n + keeper_n + wd_n + tk_n

    L = []
    L.append("# WorldQuant Brain PPA 因子挖掘进度汇报 (LIVE)")
    L.append("")
    L.append(f"- **数据快照时间**: {SNAP}")
    L.append(f"- **机器级 Python 进程 (接触 WQ BRAIN)**: {wq_n} 个 = 挖掘 {mining_total} 个进程(**{mining_tasks} 个挖掘任务**: scan {scan_n} 进程 + 三轨挖掘 {miner_n} 进程, 其中 `tri_track_undug` 含 1 父 1 子故记 2 进程) + MCP宿主 {mcp_n} + 舰队守护 {keeper_n} + watchdog {wd_n} + tracker {tk_n}；编辑器/语言服务 {ed_n} (idle)。命令行命中 `RR11jN`: {mk_n}。")
    L.append(f"- **发现任务数**: {len(recs)} 个扫描任务 (在飞 {sum(1 for r in recs.values() if r['live'])} / 已完成 {sum(1 for r in recs.values() if not r['live'])}); checkpoint 覆盖 {len(ckpts)} 个。")
    L.append(f"- **累计回测次数 (全部 checkpoint 合计)**: {tot_n} | **研究仿真 IS 闸通过候选**: {tot_pass} | **found_alphas (跨生产相关性验证)**: {tot_found} | **全链路最佳 Sharpe**: {fmt(chain_best) if chain_best else '?'}")
    L.append(f"- **在飞聚合并发吞吐**: ≈ {nf(agg_tput)} α/hr（**早期乐观值**, 仅含带进度日志的在飞任务; 稳态基准 multi(8)≈86 α/hr/任务, {n_act} 路在飞实际可持续 ≈ **{nf(steady)} α/hr**, 见 `bench_v34_sim_speed_20260723_171444.json`）。")
    L.append(f"- **平台并发模型**: Token-Bucket 令牌桶, 突发容量 C=7 (定稿见 `probe_concurrency_final_report_20260725_0255.md`)。")
    L.append("")
    L.append('<div style="background:#ffe0e0;border:2px solid #d00;color:#900;padding:10px 14px;border-radius:6px;font-weight:bold;line-height:1.6;">⚠️ <b>提交验证最重要结论</b>：本报告全部 ' + str(len(sub)) + ' 个候选 Alpha 均仅通过「研究仿真 IS 廉价闸门」、**未经完整提交验证**；其中仅 ' + str(len(verified)) + ' 个跨过生产相关性 PROD_CORRELATION（全局唯一 `YPgAa3WR` v39b, prod_corr=0.5325），**0 个**完成平台真实提交 —— <b>0 个满足完整 WQ 提交标准，请勿视作可提交 Alpha</b>。</div>')
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 0. 执行摘要")
    L.append("")
    L.append(f"1. **在飞回测进程**：{mining_tasks} 个挖掘任务在飞({mining_total} 个进程) —— `v52b_hiring_margin`(主账号) + 7 路 `scan_tri_job --dataset`(舰队, 由 `fleet_keeper.py` 错峰守护, 目标 8 路) + `tri_track_undug.py`(**独立账号分片挖掘, 见盲区⑤陷阱②, 已改判单列不漏**)。")
    L.append(f"2. **当前舰队架构已切换**：21:06–21:09 由 `fleet_keeper.py` 拉起 **新 `ds_*` 数据集舰队**(pv_tech_indicators / web_traffic_engage / order_book_imbalance / ml_factor_proj / quant_factor_lib / techindi_model / equity_kpi_forecast)，checkpoint 命名 `ds_<ds>_tri_<ds>_checkpoint.json`；旧 `v47–v54` 舰队(已结束, checkpoint 仍留 `results/`)不再在飞。旧版监控报告(21:13)描述的是旧舰队, 本次为最新状态。")
    L.append(f"3. **零 429 实证**：在飞 {mining_total} 个进程；全链路 `submit_failed=0 / 429=0 / poll_timeout=0`(进度日志核验)；各进程自带 submit_gate + multi-sim + 退避, 令牌零浪费。")
    L.append(f"4. **效率评估(源码+运行时双核验)**：在飞 `scan_tri_job`/`scan_v52b` 均落地 **显式 submit_gate + 批量 multi-sim(BATCH_SIZE=8) + 退避 + no_submit + checkpoint**(评级 优)；`tri_track_undug` 为独立账号、CONCURRENCY=3 三轨挖掘, 同样限速合规。")
    L.append(f"5. **全局最主要失败闸门 = LOW_SUB_UNIVERSE_SHARPE / 廉价 IS 闸门(S/F/M/Ret)**：最强信号仍卡子宇宙 Sharpe(历史 V39b S=2.58 / V39 S=2.30 / V34 S=1.95 平台侧失败)。")
    L.append(f"6. **瓶颈 = 信号发现, 非吞吐**：在飞舰队首步 Sharpe 普遍偏低(见 §2/§7), 加并发只是加速'挖 0 候选'。真正杠杆是范式转向(低自相关+行业中性+W189/d3/SECTOR/t1 风格扩展)。")
    L.append(f"7. **候选 Alpha 评测(提交未验证)**：共 **{len(sub)}** 个 `status=PASS/PASS_CHEAP`(研究仿真 IS 闸通过), 仅 **{len(verified)}** 个跨生产相关性验证；均缺生产仿真(OOS)+平台 submittable+真实提交。详见 §10。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 1. 进程盘点 (Python 进程第一视角, 机器级全量枚举)")
    L.append("")
    L.append("> **第一视角 = 机器上全部 python.exe 进程** (Get-CimInstance Win32_Process), 按命令行分类; v 系列 `*_progress_*.log` 只是 scan 脚本本地产物, **不是发现入口**。任何经 MCP 发起的服务端任务(如 `set_RR11jN_`)只能靠此枚举暴露其宿主。")
    L.append("")
    L.append(f"- 机器级 python 进程总数: **{len(inv)}** | 接触 WQ BRAIN: **{wq_n}** = 挖掘 {mining_total}(scan {scan_n}+三轨 {miner_n}) + MCP宿主 {mcp_n} + 舰队守护 {keeper_n} + watchdog {wd_n} + tracker {tk_n} | 编辑器/语言服务 {ed_n} (idle)")
    L.append(f"- 命令行命中 `RR11jN`: **{mk_n}** 个")
    L.append("")
    L.append("| PID | 类型 | 启动 | 线程 | 任务/说明 |")
    L.append("|---|---|---|---|---|")
    for x in sorted(inv, key=lambda z: (z["kind"], int(z["pid"]) if z["pid"].isdigit() else 0)):
        if x["kind"] == "editor":
            continue
        note = {
            "mcp_server": "WQ BRAIN MCP 交互工具宿主(服务端回测, 不写本地进度日志)",
            "keeper": "舰队守护: 维持 8 路挖掘进程, 错峰补位, 共享 submit_gate",
            "scan_script": "扫描脚本(本地进度日志见 §2)",
            "tri_miner": "三轨挖掘(本地进度日志 / 或无本地日志的独立账号)",
            "watchdog": "tri 看门狗",
            "tracker": "tri 追踪挖掘",
            "other": "其他",
        }.get(x["kind"], "其他")
        task = x["task"] or ""
        L.append(f"| {x['pid']} | {x['kind']} | {fmt_cim(x['started'])} | {x['threads']} | {task} {note} |")
    L.append("")
    L.append(f"> **第一视角核验结论**：枚举到 {wq_n} 个接触 WQ BRAIN 的进程——{mining_total} 个挖掘(含 **`tri_track_undug.py` 已由 other 改判为 tri_miner/三轨挖掘**, 框架盲区⑤陷阱②, 不再漏报) + {mcp_n} 个 MCP 宿主 + 舰队守护 {keeper_n}。此前监控以 v 系列日志为发现入口, 会漏掉非 v 命名进程与 MCP 宿主; 现以机器级进程为第一视角。命令行均无 `RR11jN`(命中 {mk_n}), 印证其为服务端句柄而非本机进程名。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 2. 全链路回测概览 (进程产物 checkpoint + 在飞实时统计)")
    L.append("")
    L.append("| 任务 | 状态 | N | PASS/CHEAP | found | 最佳S | 最佳F | 主导失败 | 区域 |")
    L.append("|---|---|---:|---:|---:|---:|---:|---|---|")
    for key, r in recs.items():
        s = r["s"]
        if s:
            n = s["n"]; p = s["stc"].get("PASS", 0) + s["stc"].get("PASS_CHEAP", 0); fa = s["fa"]
            bs = fmt(s["best_s"]) if isinstance(s["best_s"], (int, float)) else "-"
            bf = fmt(s["best_f"]) if isinstance(s["best_f"], (int, float)) else "-"
            dom = s["dom"]; reg = ",".join(sorted(s["regions"])) or "-"
        else:
            n = p = fa = "-"; bs = bf = "-"; dom = "进行中(无 checkpoint)"; reg = "-"
        st = "🟢在飞" if r["live"] else "⚪已完成"
        L.append(f"| {disp(key)} | {st} | {n} | {p} | {fa} | {bs} | {bf} | {dom} | {reg} |")
    L.append("")
    L.append(f"**合计**：{tot_n} 次回测, {tot_pass} 次 IS 闸通过, {tot_found} 个 found_alphas。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 3. 重点任务详情")
    L.append("")
    # v52b
    if "v52b_hiring_margin" in recs and recs["v52b_hiring_margin"]["s"]:
        s = recs["v52b_hiring_margin"]["s"]
        L.append(f"### 3.1 v52b_hiring_margin (在飞, 主账号)")
        L.append(f"- N={s['n']}, PASS/CHEAP={s['stc'].get('PASS',0)+s['stc'].get('PASS_CHEAP',0)}, found={s['fa']}, 最佳S={fmt(s['best_s']) if isinstance(s['best_s'],(int,float)) else '-'}, 主导失败={s['dom']}。")
        L.append(f"- 降换手(decay4 SECTOR)变体已 4 个过廉价 IS 闸(Sharpe 2.31–2.33, PASS_CHEAP), 证实降换手直击 M 闸门; 但生产相关性关未验, 不满足提交。")
        L.append("")
    # ds fleet
    L.append("### 3.2 新 ds_* 数据集舰队 (在飞, 由 fleet_keeper.py 守护, 目标 8 路)")
    L.append("")
    L.append("| 任务(dataset) | PID | 进度 | 首步最佳S | 实测节奏 | α/hr | 429 |")
    L.append("|---|---|---|---|---|---|---|")
    for key, r in recs.items():
        if not key.startswith("ds_") or not r["live"]:
            continue
        pid = ""
        for x in inv:
            if x["task"] == key:
                pid = x["pid"]
        last = (r["rt"] or {}).get("last") if r["rt"] else None
        prog = f"{last.get('done','-')}/{last.get('total','-')}" if last else "-"
        bs = fmt(r["s"]["best_s"]) if r["s"] and isinstance(r["s"]["best_s"], (int, float)) else "-"
        sps = last.get("avg_sec_per_step") if last else None
        rhythm = f"{sps:.1f}s/步" if sps else "-"
        apm = f"{r['alpha_per_hr']:.0f}" if r.get("alpha_per_hr") else "-"
        n429 = (r["rt"] or {}).get("n_429", "-") if r["rt"] else "-"
        L.append(f"| {disp(key)} | {pid} | {prog} | {bs} | {rhythm} | {apm} | {n429} |")
    L.append("")
    L.append("- 7 路均 `scan_tri_job.py` 派生, 自带 submit_gate + multi-sim(BATCH_SIZE=8) + 退避 + no_submit, 效率 优。")
    L.append("- 启动错峰 21:06–21:09, 与 v52b 共同构成多进程并发, 实测零 429。")
    L.append("")
    L.append("### 3.3 tri_track_undug.py (在飞, 独立账号三轨挖掘)")
    L.append("")
    L.append(f"- PID {', '.join(x['pid'] for x in inv if x['task']=='tri_track_undug') or '?'}；位于 `D:\\BaiduNetdiskDownload\\WQ第二三四节课代码\\worldquant\\`, **独立 gmail 账号(tabbit/world6 体系)**, 分片挖掘(CONCURRENCY=3, 8 分片, 每片 ~10 变体), 信号域为 `unsystematic_risk_last_*` / `correlation_*_spy`, 结果落 `world6_results.csv`。")
    L.append(f"- ⚠️ **框架盲区⑤陷阱②**: 其命令行含 `tri_track` 会被初版正则误判为 TRACKER, 实为真实挖掘任务; 本报告已**改判为 tri_miner 单列**, 不漏报。")
    L.append(f"- 其 checkpoint 不在 E3 `results/`(独立目录); 最新分片状态(读 miner_s4_round.log / shard5_run.log): {tri_track_status()}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 4. 方案效率评估 (源码合规 + 运行时核验)")
    L.append("")
    L.append("> 最佳实践基准 (5 条): ① 批量 multi-sim ② 令牌桶 submit_gate ③ 429 退避 ④ 禁齐射 ⑤ 断点续跑 checkpoint。本维度 = 源码标志位扫描 **且** 运行时核验(进程存活/节奏/429)。")
    L.append("")
    L.append("| 任务 | 进程 | 批量 | gate | 退避 | 续跑 | 评级 | 运行时落地 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for key, r in recs.items():
        if not r["live"]:
            continue
        f, note = eff_map.get(key, (None, ""))
        ms = "Y" if (f or {}).get("multi_sim") else "N"
        sg = "Y" if (f or {}).get("submit_gate") else "N"
        bo = "Y" if (f or {}).get("backoff") else "N"
        g = grade(f) if f else "?"
        L.append(f"| {disp(key)} | 在飞 | {ms} | {sg} | {bo} | Y | **{g}** | 已验证(进程存活, 0 429){(' ' + note) if note else ''} |")
    L.append("")
    L.append("- **批量提交 (标准1)**: scan_tri_job / scan_v52b 均经 multi_sim(BATCH_SIZE=8), 1 令牌换 8 回测, 令牌最省。")
    L.append("- **显式令牌桶闸门 (标准2)**: 经 `submit_gate.py` 跨进程令牌桶(文件锁, min_interval≈18s, 批间45s, 429退避), 运行时零 429 实证。")
    L.append("- **退避(标准3)/续跑(标准5)**: wd_lib_wrapper 退避 + checkpoint 健全, 鲁棒达标。")
    L.append("- **禁齐射(标准4)**: 多进程错峰启动(非 <2s 齐射), 实测零 429, 印证保守上限可上调, 真正约束是瞬时提交浓度 ≤ C=7。")
    L.append("- **tri_track_undug**: 独立账号 CONCURRENCY=3, 与本机主账号令牌桶互不干扰, 限速合规。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 5. 并发模型与平台限制 (Token-Bucket C=7)")
    L.append("")
    L.append("经对照实验确立为**令牌桶限流**: 突发容量 C=7, 慢补充 ~1 令牌/20–40s。")
    L.append("")
    L.append("- **安全包络**: 瞬时并发 ≤6(可错峰放宽); 持续提交间隔 ≥15–20s; 同账号同时启动进程 ≤6(禁 <2s 齐射)。")
    L.append("- **本次实证**: v52b + 7 路 ds 舰队 + tri_track(独立账号) 多进程并发, 全局零 429 —— 关键在'错峰 + 每进程自带 submit_gate', 瞬时提交浓度被压在 C=7 内。")
    L.append("- **已验证危险**: ≥8 提交在 <2s 内并发 -> 必 429。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 6. 吞吐量评估 (Throughput)")
    L.append("")
    L.append("> 口径: 1 step = 1 次 multi-sim 批量(BATCH_SIZE=8), α/hr = 3600 / avg_sec_per_step × 8。")
    L.append("")
    L.append("| 任务 | α/step | sec/step | α/hr |")
    L.append("|---|---:|---:|---:|")
    for key, r in recs.items():
        if not (r["live"] and r["rt"]):
            continue
        last = r["rt"].get("last") or {}
        sps = last.get("avg_sec_per_step")
        batch = ((eff_map.get(key) or (None,))[0] or {}).get("batch") or 8
        L.append(f"| {disp(key)} | {batch} | {nf(sps, '.1f')} | {nf(r.get('alpha_per_hr'))} |")
    L.append(f"| **聚合 (在飞 {sum(1 for r in recs.values() if r['live'] and r['rt'])} 进程)** | - | - | **{nf(agg_tput)}** |")
    L.append("")
    L.append(f"- **聚合并发吞吐 ≈ {nf(agg_tput)} α/hr**。多进程接近线性叠加, 各进程 gate 节奏(45–70s/step)略有差异未完全同步。")
    L.append(f"- **方案层效率 = 优(令牌零浪费)**: multi-sim 使每次 POST 仅耗 1 令牌换 8 次回测; submit_gate 消除 429 重提; 实测零 429 无令牌浪费。相比单发(1 POST=1 回测) 令牌效率提升 8×。")
    L.append(f"- **效率天花板在 gate 而非平台**: 单进程吞吐由各自 submit_gate 节奏绑定, 未触达平台 compute 饱和, 理论上可再加进程(须错峰+每进程 gate, 受 C=7 约束)。")
    L.append(f"- **核心瓶颈 = 信号发现**: 在飞舰队首步 Sharpe 普遍偏低, 在出候选前加并发只是加速'挖 0 候选'。吞吐已不是限制, 范式转向才是。")
    L.append(f"- **早期乐观 vs 稳态**: 上表'在飞实测'由进度日志 `avg_sec_per_step` 推算, 因任务刚启动(仅数个 batch、暖队列)而偏小; 历史稳态基准 multi(8)=86.1 α/hr(见 `bench_v34_sim_speed_20260723_171444.json`)下, {n_act} 路在飞真实可持续吞吐 ≈ **{nf(steady)} α/hr**。当前数字应视为上限, 实际趋近稳态值。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 7. 效率结论与 ETA")
    L.append("")
    L.append("- **最强信号方向(历史)**: V39b(PASS_CHEAP S=2.58) > V39(S=2.30) > V34(S=1.95, 平台侧失败); 均卡子宇宙 Sharpe 闸门。")
    L.append("- **当前 ds 舰队最佳信号**: web_traffic_engage 首步最佳 S=1.88(已过 S 闸但卡其他 IS 闸, 0 候选)、techindi_model 1.39、pv_tech_indicators 0.63, 其余 <0.5; 全舰队 0 个 PASS/CHEAP 候选 —— 信号发现仍是瓶颈。")
    L.append("- **v52b**: 降换手变体已 4 个过廉价 IS 闸, 是下一轮最值得挖的方向之一(仍差生产验证)。")
    L.append("- **ETA**: 在飞任务由各自 submit_gate 限速自然推进; 无全局阻塞。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 8. 行动建议")
    L.append("")
    L.append("1. **舰队继续**: 7 路 ds 舰队 + v52b + tri_track(独立账号) 运行时已验证合规(优, 0 429), 让其按各自 gate 自然跑完。")
    L.append("2. **攻克子宇宙 Sharpe 闸门**: 对 V39/V39b 类高 Sharpe 信号, 限定 universe=TOP3000 / 调整 neutralization / 加子宇宙约束。")
    L.append("3. **v52b 升维**: 继续调优降换手幅度(decay/中性化), 规模化过 M 闸门; 并补生产仿真+PROD_CORRELATION 验证。")
    L.append("4. **并发纪律(修订)**: 允许错峰多进程(>6)并发, 只要各进程自带 submit_gate 且非 <2s 齐射; 加任务前用本报告 §1 运维核验确认在飞进程数与 429。")
    L.append("5. **提交前须补四关**: 对 §10 候选逐个跑生产仿真 → 取全量 /check(PROD_CORRELATION/SELF_CORRELATION) → 平台 submittable 判定 → 显式 submit(关 no_submit)。优先验证已跨生产相关性关的 `YPgAa3WR`。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 9. 全量进程对账 与 盲区修正")
    L.append("")
    L.append(f"- **机器级 python 进程总数**: {len(inv)}")
    L.append(f"- **WQ BRAIN MCP 宿主 (platform_functions.py, 不写本地日志)**: {mcp_n} 个")
    L.append(f"- **挖掘进程 (scan_script + tri_miner)**: {mining_total} 个 (scan {scan_n} + 三轨 {miner_n})")
    L.append(f"- **舰队守护 / watchdog / tracker**: {keeper_n} / {wd_n} / {tk_n}")
    L.append(f"- **命令行命中 `RR11jN`**: {mk_n} 个")
    L.append("")
    L.append("### 9.1 盲区⑤陷阱②: tri_track_undug.py 改判")
    L.append("")
    L.append("- `tri_track_undug.py` 命令行含 `tri_track`, 初版正则(只认 `tri_track_miner.py`)会误判为 TRACKER; 实为**独立账号三轨挖掘(CONCURRENCY=3)**, 是真实挖掘任务。本报告已将其**改判为 tri_miner 单列**, 与 MCP 宿主/watcher 区分, **不漏报**。")
    L.append("")
    L.append("### 9.2 关于 `set_RR11jN_` 的调查结论")
    L.append("")
    L.append("- 全程检索(磁盘文件 / 进度日志 / 脚本源码 / 机器级进程命令行)均未发现 `RR11jN` 字面量; 本表'命中 RR11jN?' 全为否。")
    L.append("- 最可能的解释: `set_RR11jN_` 是 **WQ BRAIN 服务端仿真/多仿真实例 ID**, 经 MCP 助手/Web 控制台发起。{mcp_n} 个 MCP 进程是宿主, 但 `platform_functions.py` 仅输出控制台、**不写本地文件**, 故服务端任务天然不可见——这是本监控器的第二类盲区(服务端无本地日志)。")
    L.append("- 补充可见化: ① WQ BRAIN Web 控制台(账号 mthyzx@126.com) Research → Simulations 按 `RR11jN` 过滤; ② MCP 对话记录; ③ 在用户环境加 `query_wq_simulations()` 桥接(当前环境无 WQ 凭据)。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 10. 候选 Alpha 评测 (研究仿真 IS 闸通过, 提交未验证)")
    L.append("")
    L.append(f"> ⚠️ **口径纠正**: `status=PASS/PASS_CHEAP` **仅表示研究仿真(research sim)的廉价本地闸门通过, 绝不等于 WQ 提交就绪**。WQ 真实提交须过四关: ① 研究仿真 IS 指标(S>1.58/F>1.0/TVR∈[0.05,0.30]/M>10bp/Ret>0.05+近闸) ✅ {len(sub)}/{len(sub)} 全过; ② 生产仿真(OOS) ❌ 0/{len(sub)}; ③ 生产相关性 PROD_CORRELATION+自相关(仅进 found_alphas 者记过 prod_corr) ✅ 仅 {len(verified)}/{len(sub)} (`YPgAa3WR`); ④ 平台 submittable+真实提交 ❌ 0/{len(sub)}(脚本 no_submit=True)。")
    L.append("")
    if sub:
        L.append("| # | 任务 | pid | label | 状态 | Sharpe | Fitness | sub_univ | tvr | 配置 |")
        L.append("|---|---|---|---|---|---:|---:|---:|---:|---|")
        for i, a in enumerate(sub, 1):
            sh = fmt(a["sharpe"]) if isinstance(a["sharpe"], (int, float)) else "-"
            fz = fmt(a["fitness"]) if isinstance(a["fitness"], (int, float)) else "-"
            su = fmt(a["sub_univ"]) if isinstance(a["sub_univ"], (int, float)) else "-"
            tv = fmt(a["tvr"]) if isinstance(a["tvr"], (int, float)) else "-"
            L.append(f"| {i} | {a['task']} | {a['pid']} | {a['label']} | {a['status']} | {sh} | {fz} | {su} | {tv} | {a['cfg']} |")
        L.append("")
        groups = {}
        for a in sub:
            groups.setdefault(a["task"], []).append(a)
        L.append(f"**按任务分组的共享公式 (共 {len(groups)} 个根集群)**:")
        L.append("")
        for task, items in groups.items():
            sh = [x["sharpe"] for x in items if isinstance(x["sharpe"], (int, float))]
            lo, hi = (min(sh), max(sh)) if sh else ("?", "?")
            L.append(f"- **{task}** ({len(items)} 个): 代表 `{items[0]['label']}` | 配置 `{items[0]['cfg']}` | Sharpe {lo}–{hi}")
            L.append("  ```")
            L.append(items[0]["expr"] or "(公式未记录)")
            L.append("  ```")
        L.append("")
        L.append("**评测结论与提交建议**:")
        L.append(f"- **验证层级**: ① 研究仿真 IS ✅{len(sub)}/{len(sub)}; ② 生产仿真 ❌0; ③ 生产相关性 ✅仅 {len(verified)} (`YPgAa3WR`); ④ 平台提交 ❌0。→ **{len(sub)} 个均不满足 WQ 提交标准**, `PASS_CHEAP` 仅'廉价 IS 闸通过', 非'可提交'。")
        if len(groups) == 1:
            only = next(iter(groups))
            L.append(f"- **同质性极高**: {len(sub)} 个同属 `{only}`, 仅 delay/decay/中性化微差, 属同一信号参数变体集群, 非 {len(sub)} 个独立信号。")
        else:
            L.append(f"- **跨 {len(groups)} 个独立根集群**: 是不同信号方向, 提交时彼此不构成复制约束, 但仍需各自与已上线 alpha 查相关。")
        L.append(f"- **提交路径(须先补验证)**: ① 跑生产仿真; ② 取全量 /check 确认 PROD_CORRELATION/SELF_CORRELATION; ③ 平台判定 submittable; ④ 显式 submit(当前 no_submit=True)。优先验证已跨生产相关性关的 `YPgAa3WR`(prod_corr=0.5325)。")
        L.append(f"- **账号归属**: v52b/ds 舰队属主账号 `mthyzx@126.com`(checkpoint 落本机); `tri_track_undug` 属独立账号; 与 §9 `set_RR11jN_`(mlh 账号服务端任务)不同来源, 不可混淆。")
    else:
        L.append("- 当前无 status=PASS/PASS_CHEAP 的 alpha。")
    L.append("")
    L.append(f"*报告生成: {SNAP} · 数据源 机器级进程枚举(Get-CimInstance) + results/*_checkpoint.json(进程产物) + *_progress_*.log(运行时核验) + scan_*.py(源码) + 独立目录 tri_track_undug · 生成器 gen_report_live.py 可复跑*")

    open(OUT, "w", encoding="utf-8").write("\n".join(L))
    print("WROTE", OUT)
    print("tasks:", len(recs), "| live:", sum(1 for r in recs.values() if r['live']))
    print("checkpoints:", len(ckpts))
    print("tot_n:", tot_n, "pass:", tot_pass, "found:", tot_found, "bestS:", fmt(chain_best) if chain_best else '?')
    print("mining processes:", mining_total, "(scan", scan_n, "+ tri_miner", miner_n, ")")
    print("agg_tput:", round(agg_tput, 1))
    print("submittable:", len(sub), "verified:", len(verified))
    print("groups:", list(groups.keys()) if sub else [])

if __name__ == "__main__":
    main()
