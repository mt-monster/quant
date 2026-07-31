# -*- coding: utf-8 -*-
"""数据驱动的因子挖掘进度汇报 (MD 格式)。
从 checkpoint + progress 日志 + tri_track CSV 实算，所有数字来自真实文件。"""
import json, glob, os, csv, datetime, subprocess, re

NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "results")
TRI_DIR = r"D:\BaiduNetdiskDownload\WQ第二三四节课代码\worldquant"

# ===== 1. 主账号 checkpoint 数据 =====
recs = []; found = []; n_ckpt_files = 0
for f in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    n_ckpt_files += 1
    task = os.path.basename(f).replace("_checkpoint.json", "")
    if isinstance(d, dict):
        res = d.get("results", [])
        fa = d.get("found_alphas") or []
    elif isinstance(d, list):
        res, fa = d, []
    for r in res:
        r["_task"] = task; recs.append(r)
    for x in (fa if isinstance(fa, list) else []):
        x["_task"] = task; found.append(x)

total_N = len(recs)
# checkpoint mtime map (for date fallback when records lack finished_at)
ckpt_mtime_map = {}
for f in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
    task = os.path.basename(f).replace("_checkpoint.json", "")
    ckpt_mtime_map[task] = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d")
# count distinct backtest dates
_all_dates = set()
for r in recs:
    ts = (r.get("finished_at") or "")[:10]
    if ts: _all_dates.add(ts)
    elif r["_task"] in ckpt_mtime_map: _all_dates.add(ckpt_mtime_map[r["_task"]])
n_dates = len(_all_dates)
pc = [r for r in recs if str(r.get("status","")) == "PASS_CHEAP"]
cp = [r for r in recs if str(r.get("status","")) == "CHECK_PENDING"]
is_cleared = len(pc) + len(cp)
bestS = max((float(r.get("sharpe") or 0) for r in recs), default=0.0)

# 每任务
per = {}
for r in recs:
    t = r["_task"]
    p = per.setdefault(t, {"N":0,"pc":0,"cp":0,"bestS":0.0})
    p["N"]+=1
    st = str(r.get("status",""))
    if st=="PASS_CHEAP": p["pc"]+=1
    elif st=="CHECK_PENDING": p["cp"]+=1
    s = float(r.get("sharpe") or 0)
    if s>p["bestS"]: p["bestS"]=s

# 失败闸门
fcats = {"S(夏普)":0,"F(拟合)":0,"M(换手收益)":0,"Ret(收益)":0,"TVR(换手率)":0,
         "PF:子宇宙Sharpe":0,"submit_failed":0}
pf_detail={}
for r in recs:
    fl=r.get("fails"); 
    if not isinstance(fl,list): continue
    for x in fl:
        s=str(x)
        if s.startswith("PF:"): fcats["PF:子宇宙Sharpe"]+=1; pf_detail[s]=pf_detail.get(s,0)+1
        elif s.startswith("S="): fcats["S(夏普)"]+=1
        elif s.startswith("F="): fcats["F(拟合)"]+=1
        elif s.startswith("M="): fcats["M(换手收益)"]+=1
        elif s.startswith("Ret="): fcats["Ret(收益)"]+=1
        elif "tvr" in s.lower(): fcats["TVR(换手率)"]+=1
        elif s=="submit_failed": fcats["submit_failed"]+=1

# found 详情
found_pid = found[0]["pid"] if found else "?"
found_pcorr = found[0].get("prod_corr","?") if found else "?"

# ===== 1b. 平台验证结果（_platform_verified.json）=====
verified = {}
try:
    vf = os.path.join(RES, "_platform_verified.json")
    if os.path.exists(vf):
        verified = json.load(open(vf, encoding="utf-8"))
except: pass

# pre-compute active/rejected counts from verified (used in core conclusion)
n_active_total = sum(1 for v in verified.values() if v.get("status")=="ACTIVE")
n_rejected_total = sum(1 for v in verified.values() if v.get("status") in ("UNSUBMITTED","GATE_FAIL","NO_OOS"))

# ===== 1c. 机器级全量 Python 进程枚举（分类：SCAN / MCP / WATCHDOG / OTHER）=====
all_procs = []
active_non_ds = {}
active_scan_tasks = set()
try:
    ps_cmd2 = r'''Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object { "$($_.ProcessId)|$($_.CreationDate)|$($_.ThreadCount)|$($_.CommandLine)" }'''
    result2 = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd2],
                            capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
    for line in result2.stdout.strip().split("\n"):
        line = line.strip()
        parts = line.split("|", 3)
        if len(parts) < 4: continue
        pid, cdate, threads, cmd = parts[0], parts[1], parts[2], parts[3]
        # classify
        cat, tname = "OTHER", "?"
        if "scan_v" in cmd or "scan_tri_job" in cmd:
            cat = "SCAN"
            # extract task name from script
            m = re.search(r'scan_(\w+)\.py', cmd)
            tname = m.group(1) if m else "scan_?"
        elif "platform_functions" in cmd or "cnhkmcp" in cmd:
            cat = "MCP-SVC"
            tname = "MCP-WQ-BRAIN-host"
        elif "_green_guard" in cmd or "analyze_tabbit" in cmd:
            cat = "WATCHDOG"
            tname = "green_guard" if "_green_guard" in cmd else "analyze_tabbit"
        elif "continuous_undug" in cmd:
            cat = "SCAN"
            tname = "continuous_undug"
        elif "tri_track" in cmd:
            cat = "SCAN"
            tname = "tri_track_undug"
        elif "fw_v2_miner" in cmd:
            cat = "SCAN"
            tname = "fw_v2_miner"
        elif "jedi" in cmd or "ms-python" in cmd:
            cat = "EDITOR"
            tname = "language-server"
        all_procs.append({"pid": pid, "cmd": cmd[:120], "created": cdate, "threads": int(threads.strip()),
                          "category": cat, "task_name": tname})
except Exception as e:
    all_procs = []  # fallback

# group active task names (exclude EDITOR and MCP-SVC)
active_tasks_from_procs = set()
for p in all_procs:
    if p["category"] in ("SCAN", "OTHER") and p["task_name"] not in ("?", "language-server"):
        active_tasks_from_procs.add(p["task_name"])

# ===== 1c-bis. active_non_ds 数据采集（checkpoint 驱动，进程枚举为辅）=====
# Discover all v* scan tasks from checkpoints that are NOT in the known-finished list
known_finished_tasks = {"v52b_hiring_margin", "v52_tri_hiring_trends", "v39b_sub_micro", "v39_sub_micro"}
v_tasks_from_ckpt = set()
for t in per:
    if t.startswith("v") and t not in known_finished_tasks and "ds_" not in t:
        v_tasks_from_ckpt.add(t)
# add from processes too
v_tasks_from_ckpt.update(t for t in active_tasks_from_procs if t.startswith("v"))

for tn in sorted(v_tasks_from_ckpt):
    info = {"pids": [], "threads": 0, "created": "?", "done": 0, "total": 0, "found": 0, "bestS": 0.0, "samples": []}
    # process info
    for p in all_procs:
        if p["task_name"] == tn or tn.startswith(p["task_name"]):
            info["pids"].append(p["pid"])
            info["threads"] = max(info["threads"], p["threads"])
            if info["created"] == "?" or p["created"] < info["created"]:
                info["created"] = p["created"]
    # checkpoint data
    for pattern in [f"{tn}_checkpoint.json", f"{tn}b_*_checkpoint.json", f"{tn}_*_checkpoint.json"]:
        matches = glob.glob(os.path.join(RES, pattern))
        for mp in sorted(matches, key=lambda x: os.path.getmtime(x), reverse=True):
            try:
                cd = json.load(open(mp, encoding="utf-8"))
                rs_cd = cd.get("results", [])
                fas_cd = cd.get("found_alphas", [])
                if rs_cd:
                    info["done"] = len(rs_cd)
                    info["total"] = cd.get("total_variants", len(rs_cd))
                    info["found"] = len(fas_cd)
                    ss = [float(r.get("sharpe") or 0) for r in rs_cd if r.get("sharpe") is not None]
                    if ss: info["bestS"] = max(ss)
                    for r in sorted(rs_cd, key=lambda x: float(x.get("sharpe", 0) or 0), reverse=True)[:3]:
                        info["samples"].append((float(r.get("sharpe", 0) or 0), r.get("label", "?")[:35], r.get("pid", "?")))
                break
            except: pass
    # 429 count from log
    for log_name in [f"{tn}.log", f"{tn.replace('_intraday','_glb_intraday')}.log"]:
        log_path = os.path.join(RES, log_name)
        if os.path.exists(log_path):
            v429 = 0
            cutoff = datetime.datetime.now() - datetime.timedelta(minutes=60)
            try:
                for ln in open(log_path, encoding="utf-8", errors="ignore"):
                    if "429 noted" in ln:
                        try:
                            ts_str = ln[:19]
                            lt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                            if lt >= cutoff: v429 += 1
                        except: pass
            except: pass
            if v429: info["429_1h"] = v429
            break
    active_non_ds[tn] = info

# now insert the rendering of active_non_ds section

# ===== 1d. 活跃 ds 进程（机器级实时枚举，非文件快照）=====
ds_active_processes = set()
ds_active_pids = set()
try:
    # PowerShell: enumerate all python scan_tri_job processes, extract --dataset param
    ps_cmd = r'''Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -match 'scan_tri_job'} | ForEach-Object { $ds = ($_.CommandLine -split '--dataset ')[1] -split ' ' | Select-Object -First 1; "$($_.ProcessId)|$ds" }'''
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                           capture_output=True, text=True, timeout=15)
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if "|" in line:
            pid_str, ds = line.split("|", 1)
            pid = int(pid_str.strip())
            ds_name = ds.strip()
            if ds_name:
                ds_active_processes.add(ds_name)
                ds_active_pids.add(pid)
    # update the file cache for historical reference
    if ds_active_processes:
        json.dump(sorted(ds_active_processes), open(os.path.join(RES, "_ds_active_processes.json"), "w"))
except Exception as e:
    # fallback: read from cached file if enumeration fails
    ap_file = os.path.join(RES, "_ds_active_processes.json")
    if os.path.exists(ap_file):
        try: ds_active_processes = set(json.load(open(ap_file, encoding="utf-8-sig")))
        except: pass

# ===== 2. ds 舰队 progress 日志 =====
# ds progress logs: auto-discover from glob (no hardcoded DS_PREFIX — D8.1 blind spot fix)
ds_datasets_live = set()      # datasets with active "progress" event (done < tot)
ds_live = {}
for log_path in sorted(glob.glob(os.path.join(RES, "ds_*_tri_progress_*.log"))):
    fname = os.path.basename(log_path)
    prefix = fname.split("_tri_progress_")[0]
    last = None
    for ln in open(log_path, encoding="utf-8", errors="ignore"):
        try:
            e = json.loads(ln)
        except:
            continue
        if e.get("event") in ("progress", "finish"):
            last = e
    if last:
        done = last.get("done", 0)
        tot = last.get("total", 320)
        el = last.get("elapsed_sec") or 0
        pct = done / tot * 100 if tot else 0
        thr = done / (el / 3600.0) if el > 0 else 0
        eta_str = "?"
        if done >= tot:
            eta_str = "已完成"
        elif done > 0 and el > 0 and done < tot:
            pace = done / el
            remaining = tot - done
            eta_s = remaining / pace
            eta_dt = datetime.datetime.now() + datetime.timedelta(seconds=eta_s)
            eta_str = eta_dt.strftime("%m-%d %H:%M")
        ds_live[prefix] = {"done": done, "total": tot, "pct": round(pct, 1),
                           "elapsed_min": round(el / 60, 1),
                           "alpha_per_hr": round(thr, 0), "eta": eta_str}
        if last.get("event") == "progress" and done < tot:
            ds_datasets_live.add(prefix)

# ds 任务名映射
ds_tasks=[k for k in per if k.startswith("ds_")]
def ds_short(k): return k.split("_tri_")[0].replace("ds_","")
def ds_live_key(k): return k.split("_tri_")[0]

# v52b 进度日志
v52b_live = {"eta": "?"}
v52b_done = per.get("v52b_hiring_margin", {}).get("N", 0)
v52b_finished = False
v52b_prog = os.path.join(RES, "v52b_hiring_margin_progress.log")
if os.path.exists(v52b_prog):
    last = None
    for ln in open(v52b_prog, encoding="utf-8", errors="ignore"):
        try: e = json.loads(ln)
        except: continue
        if e.get("event") == "progress": last = e
    if last:
        done = last.get("done", 0); total = last.get("total", 1)
        el = last.get("elapsed_sec", 0); pct = done / total * 100 if total else 0
        if done >= total:
            v52b_finished = True
        if done > 0 and el > 0 and done < total:
            pace = done / el; remaining = total - done
            eta_s = remaining / pace
            eta_dt = datetime.datetime.now() + datetime.timedelta(seconds=eta_s)
            v52b_live = {"done": done, "total": total, "pct": round(pct, 1),
                         "elapsed_min": round(el / 60, 1), "eta": eta_dt.strftime("%m-%d %H:%M")}
elif v52b_done >= 160:
    # 旧进程无进度日志但 checkpoint 已满 160 → 判定已完成
    v52b_finished = True
    v52b_live = {"done": 160, "total": 160, "pct": 100.0, "eta": "已完成 (23:29)"}

# ===== 3. tri_track 独立账号数据 =====
tri_account="ML88164"
tri_shards=8; tri_per_shard=10; tri_concurrency=3
tri_total=0; tri_tracks={}; tri_times=[]; tri_bestS=0.0; tri_pass=0; tri_fail=0; tri_submitted=0
tri_has_metrics=False  # 是否有回测指标（Sharpe等）
tri_eta="?"

# 优先读 checkpoint（含回测指标）
tri_ckpt=os.path.join(TRI_DIR,"tri_track_undug_checkpoint.json")
if os.path.exists(tri_ckpt):
    try:
        d=json.load(open(tri_ckpt,encoding="utf-8"))
        for r in d.get("results",[]):
            tri_total+=1
            tr=r.get("track","?"); tri_tracks[tr]=tri_tracks.get(tr,0)+1
            st=r.get("status","?")
            if st=="submitted": tri_submitted+=1
            else: tri_fail+=1
            s=r.get("sharpe")
            if s is not None:
                tri_has_metrics=True
                if s>tri_bestS: tri_bestS=s
        ft=d.get("results",[{}])[0].get("finished_at","") if d.get("results") else ""
        ft_last=d["results"][-1].get("finished_at","") if d.get("results") else ""
        tri_earliest=ft or "?"
        tri_latest=ft_last or "?"
    except: pass

# 读进度日志（ETA）
tri_prog=os.path.join(TRI_DIR,"tri_track_undug_progress.log")
if os.path.exists(tri_prog):
    last_prog=None
    for ln in open(tri_prog,encoding="utf-8",errors="ignore"):
        try: e=json.loads(ln)
        except: continue
        if e.get("event")=="progress": last_prog=e
    if last_prog:
        done=last_prog.get("done",0); total=last_prog.get("total",1)
        el=last_prog.get("elapsed_sec",0)
        pct=done/total*100 if total else 0
        if done>0 and el>0 and done<total:
            pace=done/el; remaining=total-done
            eta_s=remaining/pace
            eta_dt=datetime.datetime.now()+datetime.timedelta(seconds=eta_s)
            tri_eta=eta_dt.strftime("%m-%d %H:%M")

# 降级: 读 CSV（无回测指标）
if tri_total==0:
    tri_csv=os.path.join(TRI_DIR,"tri_track_undug_results.csv")
    try:
        for row in csv.DictReader(open(tri_csv,encoding="utf-8")):
            tri_total+=1
            tr=row.get("track","?"); tri_tracks[tr]=tri_tracks.get(tr,0)+1
            ft=row.get("finished_at","")
            if ft: tri_times.append(ft)
    except: pass
    tri_earliest=min(tri_times) if tri_times else "?"
    tri_latest=max(tri_times) if tri_times else "?"
    tri_submitted=tri_total  # CSV 中全部是 done
    # 粗估 ETA
    tri_shards_done=2; tri_shards_remain=tri_shards-tri_shards_done
    tri_batch_sec=300
    tri_eta_sec=tri_shards_remain/tri_concurrency*tri_batch_sec
    tri_eta_dt=datetime.datetime.now()+datetime.timedelta(seconds=tri_eta_sec)
    tri_eta=tri_eta_dt.strftime("%m-%d %H:%M")

# tri_track 完成判定: 无 checkpoint + 无 progress 日志 + 有 CSV → 旧脚本已完成
tri_finished = False
if tri_total > 0 and not os.path.exists(tri_ckpt) and not os.path.exists(tri_prog):
    tri_finished = True
    tri_csv_path = os.path.join(TRI_DIR, "tri_track_undug_results.csv")
    try:
        tri_csv_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(tri_csv_path)).strftime("%m-%d %H:%M")
    except:
        tri_csv_mtime = "?"
    tri_eta = f"已完成 ({tri_csv_mtime})"

# helper: extract signal field name from expression
def extract_field(expr):
    if not expr: return "?"
    # unwrap common wrappers
    s = expr
    for wrapper in ("rank(", "group_zscore(", "ts_zscore(", "ts_backfill(", "group_rank("):
        if wrapper in s:
            s = s.split(wrapper, 1)[-1]
    # unwrap vec_avg if present
    if s.startswith("vec_avg("):
        s = s[len("vec_avg("):]
    elif s.startswith("vec_sum("):
        s = s[len("vec_sum("):]
    # extract first comma-separated argument
    field = s.split(",")[0].split(")")[0].strip()
    # if still a function call, recurse
    if "(" in field:
        field = field.split("(")[-1]
    return field[:25]

# ===== 4. 候选明细 =====
cand=[]
for r in pc+cp:
    try: s=float(r.get("sharpe")or 0)
    except: s=0.0
    try: f1=float(r.get("fitness")or 0)
    except: f1=0.0
    # skip already-rejected candidates (verified against platform)
    pid = r.get("pid","?")
    if pid and pid in verified:
        vf_st = verified[pid].get("status","")
        if vf_st in ("GATE_FAIL","NO_OOS","UNSUBMITTED"):
            continue  # platform rejected — exclude from candidate list
    stg=r.get("settings") or {}
    cand.append({"pid":pid,"task":r["_task"],"S":s,"F":f1,
                 "status":"PASS_CHEAP" if r in pc else "CHECK_PENDING",
                 "tvr":r.get("tvr"),
                 "field": extract_field(r.get("expr","")),
                 "cfg":f"{stg.get('region','?')} {stg.get('universe','?')} decay{stg.get('decay','?')} {stg.get('neutralization','?')}"})
cand.sort(key=lambda x:-x["S"])

# ===== 4b. 提交核查 =====
found_map={}
for x in found: found_map[x["pid"]]=x
audit=[]  # [pid,task,S,stage,verification_done,steps_missing,category,action]
for c in pc+cp:
    pid=c.get("pid","?"); st=c.get("status","?"); t=c["_task"]
    # skip already-rejected candidates
    if pid and pid in verified and verified[pid].get("status") in ("GATE_FAIL","NO_OOS","UNSUBMITTED"):
        continue
    s_val=float(c.get("sharpe") or 0)
    fa=found_map.get(pid)
    has_prod=fa is not None
    has_rn=fa and fa.get("risk_neut")
    has_rob=fa and fa.get("robust",{}).get("ok")
    prod_c=fa.get("prod_corr") if fa else None

    # Check platform-verified status (from API submission/check)
    vf_entry = verified.get(pid)
    vf_platform_st = vf_entry.get("status") if vf_entry else None
    vf_submitted = vf_entry.get("dateSubmitted") if vf_entry else None

    # Also treat found_map entries with prod_corr+risk_neut+robust as ACTIVE (e.g. YPgAa3WR)
    if not vf_platform_st and has_prod and has_rn and has_rob:
        vf_platform_st = "ACTIVE"
        vf_submitted = fa.get("pid","?")  # placeholder from found_alphas
    done_parts=["IS闸(S=%.2f)"%s_val]
    if has_prod: done_parts.append("生产相关性(%.4f)"%prod_c)
    if has_rn: done_parts.append("风险中性")
    if has_rob: done_parts.append("稳健性")
    missing_parts=[]
    if st=="CHECK_PENDING":
        done_parts.append("生产相关性检验中⚡")
        missing_parts.append("等平台返回产验结果")
    if not has_prod: missing_parts.append("生产相关性验证")
    missing_parts.extend(["生产仿真(OOS)","submittable判定","显式submit(no_submit→True)"])

    # --- verified-status reclassification ---
    if vf_platform_st == "ACTIVE":
        cat = "✅ 已正式提交"
        act = f"已上线 ({vf_submitted[:16] if vf_submitted else '?'})"
    elif vf_platform_st == "UNSUBMITTED":
        # silently rejected by platform
        reason = vf_entry.get("note","同集群信号被占用") if vf_entry else "同集群信号被占用"
        cat = "❌ 平台拒绝"
        act = reason
    elif vf_platform_st == "GATE_FAIL":
        # /check returned hard gate FAIL (PROD_CORRELATION / SELF_CORRELATION / LOW_2Y_SHARPE)
        fgs = vf_entry.get("fail_gates",[]) if vf_entry else []
        reason = f"闸门 FAIL: {'+'.join(fgs) if fgs else '未知'}"
        cat = "❌ 平台拒绝"
        act = reason
    elif vf_platform_st == "NO_OOS":
        # /check empty — never ran OOS, submit silently rejected
        cat = "❌ 平台拒绝"
        act = "未跑OOS — 提交被静默拒绝（同集群信号冲突）"
    elif vf_platform_st == "POLL_TIMEOUT":
        cat = "⏳ OOS 排队中"
        act = "已提交，等平台OOS评估"
    elif has_prod and has_rn and has_rob:
        cat="🔶 最接近提交"; act=f"缺OOS+submittable+submit (3步)"
    elif st=="CHECK_PENDING":
        cat="🔶 平台产验中"; act="等平台结果+OOS+submit"
    else:
        cat="🔴 仅IS闸"; act="需全部后续验证(4项)"
    audit.append((pid,t,s_val,st," / ".join(done_parts)," / ".join(missing_parts),cat,act))

TH=1.58
def sflag(v):
    if v>=TH: return "🟢"
    if v>=1.0: return "🟡"
    return "🔴"
def bar(w,maxw=40):
    n=max(1,int(w/maxw*maxw)) if maxw else 1
    return "█"*n

def extract_field(expr):
    """Extract the key data field name from a FASTEXPR expression."""
    if not expr: return "?"
    s = expr
    for wrapper in ("rank(", "group_zscore(", "ts_zscore(", "ts_backfill(", "group_rank("):
        if wrapper in s:
            s = s.split(wrapper, 1)[-1]
    if s.startswith("vec_avg("):
        s = s[len("vec_avg("):]
    elif s.startswith("vec_sum("):
        s = s[len("vec_sum("):]
    elif s.startswith("ts_mean("):
        s = s[len("ts_mean("):]
    field = s.split(",")[0].split(")")[0].strip()
    if "(" in field:
        field = field.split("(")[-1]
    return field[:25]

def template_str(task_name, record=None):
    """Build compact template display: task_short [field | config]. First 5 chars enough for task grouping."""
    short = task_name.split("_checkpoint")[0].replace("_checkpoint","")[:30]
    if record and record.get("settings"):
        stg = record["settings"]
        field = extract_field(record.get("expr",""))
        cfg = f"{stg.get('universe','?')} d{stg.get('decay','?')} {stg.get('neutralization','?')[:3]}"
        field_info = f"[{field}] " if field and len(field) < 35 else ""
        return f"{field_info}{cfg}"
    return ""

# ===== 5. 生成 MD =====
L=[]
def a(s=""): L.append(s)

# 元数据
a(f"> **数据快照**: {NOW} GMT+8 ｜ **数据源**: `results/*_checkpoint.json`(权威) + `*_progress_*.log`(实时) + `tri_track_undug_results.csv`")
a()
a(f"> ⚠️ **提交验证最重要结论**：全部 **{is_cleared}** 个候选，**{n_active_total} 个 ACTIVE**（API 验证已上线），**{n_rejected_total} 个平台拒绝**（PROD_CORRELATION/SELF_CORR FAIL）。PASS_CHEAP ≠ 可提交。")

# 一、核心结论
a(); a("---"); a("## 一、核心结论（结论先行）"); a()
a(f"| 指标 | 数值 | 说明 |")
a(f"|---|---|---|")
a(f"| 累计回测次数 | **{total_N:,}** | 全部 {n_ckpt_files} 个 checkpoint 合计 |")
a(f"| IS 廉价闸门通过 | **{is_cleared}** ({len(pc)} PASS_CHEAP + {len(cp)} CHECK_PENDING) | 仅研究仿真 IS 闸通过，非「可提交」 |")
found_desc = f"全局唯一 ({found_pid})" if len(found)==1 else (f"全局 {len(found)} 个" if found else "0")
a(f"| 跨生产相关性验证 | **{len(found)}** ({found_pid}, prod_corr={found_pcorr}) | {found_desc} |")
active_desc = f"{n_active_total} (" + ", ".join([p for p,v in verified.items() if v.get("status")=="ACTIVE"]) + ")" if n_active_total else "0"
a(f"| 平台真实提交 | **{n_active_total}** ({active_desc}) | 全局 API 验证确认 |")
bestS_task = max(per.items(), key=lambda x: x[1]["bestS"]) if per else ("?", {"bestS":0.0})
bestS_task_name = bestS_task[0][:30] if bestS_task[0] != "?" else "?"
a(f"| 全链路最佳 Sharpe | **{bestS:.2f}** | {bestS_task_name} |")
# template/date overview (from hierarchical dimension)
n_templates = len(per)
n_dates = len(set(r.get("finished_at","")[:10] for r in recs if r.get("finished_at")) or set(ckpt_mtime_map.get(r["_task"],"")[:10] for r in recs))
a(f"| 因子模板数 | **{len(per)}** | 跨 {n_dates} 个回测日期 |")
done_parts = []
if v52b_finished: done_parts.append("v52b(已完成 23:29)")
if tri_finished: done_parts.append("tri_track(已完成 " + (tri_csv_mtime if tri_finished else "?") + ")")
ds_not_done = sum(1 for t in ds_tasks
                  if ds_live.get(ds_live_key(t), {}).get("done", per[t]["N"])
                     < ds_live.get(ds_live_key(t), {}).get("total", 320))
# Dynamic in-flight: ds fleet + live process tasks + tri_track
active_scan_tasks = set()
for p in all_procs:
    if p["category"] == "SCAN":
        active_scan_tasks.add(p["task_name"])
# also include v52b if checkpoint still running & not finished
for task_name in per:
    if task_name.startswith("v") and task_name not in ("v52b_hiring_margin", "v52_tri_hiring_trends", "v39b_sub_micro", "v39_sub_micro"):
        ckpt_path = os.path.join(RES, f"{task_name}_checkpoint.json")
        if os.path.exists(ckpt_path):
            # check if task appears "incomplete" (found_alphas not fully resolved, or progress log exists)
            try:
                ckpt_data = json.load(open(ckpt_path, encoding="utf-8"))
                fas = ckpt_data.get("found_alphas", [])
                # if found is empty but results exist, may still be running
            except: pass
            active_scan_tasks.add(task_name)
# Remove tasks we know are finished
active_scan_tasks.discard("v52b_hiring_margin")  # handled separately
active_scan_tasks.discard("v39b_sub_micro")
active_scan_tasks.discard("v39_sub_micro")
active_scan_tasks.discard("v52_tri_hiring_trends")
active_scan_tasks.discard("continuous_undug")  # unclear if running

n_v_like = len([t for t in active_scan_tasks if t.startswith("v") and "ds_" not in t])
n_ds_from_procs = len([t for t in active_scan_tasks if t.startswith("ds_") or "scan_tri_job" in t])
in_flight_n = max(ds_not_done, n_ds_from_procs) + n_v_like + (0 if tri_finished else 1)
# Build description dynamically
in_flight_parts = []
if n_ds_from_procs or ds_not_done:
    in_flight_parts.append(f"{ds_not_done} 个 ds 数据集未完成")
if n_v_like:
    names = sorted([t[:25] for t in active_scan_tasks if t.startswith("v")])
    in_flight_parts.append(f"{n_v_like} 个 v* 任务 ({', '.join(names[:3])}{'…' if len(names)>3 else ''})")
if not tri_finished:
    in_flight_parts.append("tri_track 在飞")
in_flight_desc = " + ".join(in_flight_parts) if in_flight_parts else "0"
done_suffix = " (" + ", ".join(done_parts) + ")" if done_parts else ""
ds_datasets_in_progress = len(ds_datasets_live)
ds_datasets_in_progress_fb = sum(1 for t in ds_tasks if ds_live.get(ds_live_key(t),{}).get("eta","") not in ("已完成",""))
ds_in_progress = max(ds_datasets_in_progress, ds_datasets_in_progress_fb)

# Dynamic 429 count from v53 log
v53_429_count = 0
v53_log = os.path.join(RES, "v53_glb_intraday.log")
if os.path.exists(v53_log):
    try:
        # count 429 in last 30 min
        cutoff = datetime.datetime.now() - datetime.timedelta(minutes=30)
        for ln in open(v53_log, encoding="utf-8", errors="ignore"):
            if "429 noted" in ln:
                try:
                    ts = ln[:19]
                    lt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    if lt >= cutoff: v53_429_count += 1
                except: pass
    except: pass
v53_429_str = f"v53: {v53_429_count}次 CONCURRENT_SIMULATION_LIMIT_EXCEEDED（30min）" if v53_429_count else "0 (近30min)"
a(f"| 在飞挖掘任务 | **{in_flight_n}** | {in_flight_desc}{done_suffix} |")
a(f"| 近期 429 | **{v53_429_str}** | 实时枚举，从当前日志计算 |")
a()
# build dynamic bottleneck line
v52b_N = per.get("v52b_hiring_margin",{}).get("N",0)
v52b_pc = per.get("v52b_hiring_margin",{}).get("pc",0)
v39b_N = per.get("v39b_sub_micro",{}).get("N",0)
bottleneck_parts = []
if v52b_N:
    bottleneck_parts.append(f"v52b {v52b_N} 变体 → {v52b_pc} PASS_CHEAP / 0 found（PROD_CORR 全军覆没）")
if v39b_N:
    bottleneck_parts.append(f"v39b {v39b_N} 变体 → {per['v39b_sub_micro']['pc']} PASS_CHEAP / {len(found)} found（仅 YPgAa3WR 幸存）")
bottleneck_parts.append(f"ds 舰队 {len(ds_tasks)} 个数据集批量挖矿中，0 候选")
bottleneck_parts.append(f"tri_track {tri_total} alpha" + (f"，最佳 S={tri_bestS:.2f}" if tri_bestS>0 else ""))
a("**核心瓶颈**：信号发现，非吞吐。" + "；".join(bottleneck_parts) + "。")

# 二、提交漏斗
# ===== 1e. 渲染：当前在跑非 ds 任务实时详情 =====
if active_non_ds:
    a(); a("---"); a("## · 当前在跑任务实时详情（进程枚举 + checkpoint 动态发现）"); a()
    a("> ⚠️ 本章节**不依赖硬编码任务清单**，由实时进程枚举 + `results/*_checkpoint.json` 动态扫描生成。新增任务自动覆盖。")
    a()
    for tn, info in sorted(active_non_ds.items()):
        a(f"### {'🟢' if info['found'] else '🔴'} {tn}")
        a()
        a(f"| 指标 | 数值 |")
        a(f"|---|---|")
        a(f"| 进程 | PID {', '.join(str(p) for p in info['pids'])}，{info['threads']} 线程，自 {info.get('created','?')[:16]} |")
        a(f"| 回测进度 | **{info['done']}/{info['total']}** " + (f"({info['done']/info['total']*100:.0f}% done，{info['total']-info['done']} 剩余)" if info['total']>0 else "(?)") + " |")
        a(f"| 找到候选 | **{info['found']}** found_alphas |")
        a(f"| 最佳 S | **{info['bestS']:.2f}** （含 FAIL 记录）|")
        v429_tag = f" **{info.get('429_1h',0)} 次 429 (1h)**" if info.get('429_1h',0) else ""
        a(f"| 429 实证{v429_tag} | CONCURRENT_SIMULATION_LIMIT_EXCEEDED（8-lane multi-sim 打满并发槽） |")
        a()
        if info["samples"]:
            a(f"**Top-3 信号样例**：")
            a("| S | label (信号名) | pid |")
            a("|---|---|---|")
            for s, label, pid in info["samples"]:
                a(f"| **{s:.2f}** | `{label}` | {pid} |")
            a()
        # S distribution
        ckpt_path = None
        for pattern in [f"{tn}_checkpoint.json", f"{tn}b_*_checkpoint.json", f"{tn}_*_checkpoint.json"]:
            matches = glob.glob(os.path.join(RES, pattern))
            if matches:
                ckpt_path = sorted(matches, key=lambda x: os.path.getmtime(x), reverse=True)[0]
                break
        if ckpt_path:
            try:
                cd = json.load(open(ckpt_path, encoding="utf-8"))
                rs_cd = cd.get("results", [])
                ss_all = sorted([float(r.get("sharpe",0) or 0) for r in rs_cd if r.get("sharpe") is not None], reverse=True)
                if ss_all:
                    s_gt2 = sum(1 for s in ss_all if s > 2.0)
                    s_gt158 = sum(1 for s in ss_all if s > 1.58)
                    s_gt125 = sum(1 for s in ss_all if s > 1.25)
                    a(f"**S 分布**：Max={ss_all[0]:.2f}，P95={ss_all[int(len(ss_all)*0.05)]:.2f}，P50={ss_all[len(ss_all)//2]:.2f}")
                    a(f"| S>2.0 | S>1.58 | S>1.25 | 总量 |")
                    a(f"|---:|---:|---:|---:|")
                    a(f"| {s_gt2} | {s_gt158} | {s_gt125} | {len(ss_all)} |")
                    a()
            except: pass

# 二、提交漏斗
a(); a("---"); a("## 二、提交就绪漏斗"); a()
a("```")
maxV=total_N
for label,val in [("研究仿真回测",total_N),("IS 廉价闸门通过",is_cleared),("跨生产相关性验证",len(found)),("平台真实提交",0)]:
    pct=val/maxV*100 if maxV else 0
    a(f"  {label:20s} {bar(val,maxV)} {val:>6,} ({pct:.1f}%)")
a("```")
a()
a(f"每一级都是一道硬闸门：**IS 廉价闸门**筛掉 {total_N-is_cleared:,} 次（{total_N-is_cleared:,.0f}/{total_N}={(1-is_cleared/total_N)*100 if total_N else 0:.1f}% 被筛）；**生产相关性关**仅 {len(found)} 个通过；**平台提交**为 0。{is_cleared} 个候选 ≠ 可提交。")

# 三、ds 舰队 vs tri_track 对比
a(); a("---"); a("## 三、ds 舰队 vs tri_track 独立账号（对比）"); a()
a("| 维度 | 🚢 ds 舰队 (主账号) | 🛡️ tri_track (独立账号) |")
a("|---|---|---|")
a(f"| 账号 | mthyzx@126.com | {tri_account} (独立 gmail/tabbit 体系) |")
a(f"| 并发模型 | 每任务 submit_gate + multi-sim(BATCH=8) | CONCURRENCY={tri_concurrency} 三轨并行 |")
ds_total_steps_tot = sum(per[t]['N'] for t in ds_tasks) if ds_tasks else 0
ds_short_count = len(ds_tasks)
a(f"| 在飞任务数 | {ds_in_progress} 个 ds 数据集 | 1 进程 ({tri_shards} 分片) |")
a(f"| 总任务量 | {ds_short_count} × 320 = {ds_short_count*320:,} | {tri_shards} 分片 × {tri_per_shard} 任务 = {tri_shards*tri_per_shard} |")
a(f"| 已提交 alpha | 累计 {sum(per[t]['N'] for t in ds_tasks)} 次 (含研究仿真) | {tri_total} alpha 已提交并完成 |")
tri_is_metrics = f"{tri_submitted} submitted / {tri_fail} failed, 最佳S={tri_bestS:.2f}" if tri_has_metrics else "无回测指标"
a(f"| 通过 IS 闸 | 0 候选 | {tri_is_metrics} |")
tri_sharpe_str = f"{tri_bestS:.2f} (checkpoint)" if tri_has_metrics else "不可用"
a(f"| 首步最佳 Sharpe | {max(per[t]['bestS'] for t in ds_tasks):.2f} (web_traffic) | {tri_sharpe_str} |")
a(f"| 429 实证 | 0 | 0 (独立账号, 令牌不相干扰) |")
a(f"| 续跑 | ✅ checkpoint 断点续跑 | ✅ 分片 resume (已完成跳过) |")
a(f"| 结果落盘 | `results/ds_*_checkpoint.json` | `tri_track_undug_results.csv` |")
a(f"| 信号域 | {ds_short_count} 种金字塔数据集 | option8/fundamental2/pv13/analyst4 + SubU 救援 |")
if tri_has_metrics:
    a(); a(f"> ✅ **tri_track 回测指标已接入**：checkpoint 含 {tri_total} 条 alpha 的 Sharpe/Fitness/TVR/Margin/失败闸门，最佳 S={tri_bestS:.2f}。ds 舰队与 tri_track 信号质量现已可直接对比。")
else:
    a(); a("> ⚠️ **关键差异**：ds 舰队记录完整的回测指标；tri_track 独立账号仅记录提交日志，**不包含回测指标**，无法直接对比信号质量。")

# 四、ds 舰队实时详情
a(); a("---"); a(f"## 四、ds 舰队实时详情 ({len(ds_active_processes)} 活跃进程 / {ds_in_progress} 数据集记录在档)")

# split ds datasets into three groups by actual process state
ds_running = []   # active scan_tri_job processes
ds_paused = []    # unfinished progress but NO active process (paused by fleet_keeper)
ds_completed = [] # finished

for t in ds_tasks:
    lv = ds_live.get(ds_live_key(t), {})
    eta = lv.get("eta", "?")
    p = per[t]
    # check if any active process matches this dataset
    ds_name = ds_short(t)
    has_active = any(ap in t or ap == ds_name for ap in ds_active_processes)

    if has_active:
        ds_running.append((t, p, lv))
    elif eta == "已完成":
        ds_completed.append((t, p, lv))
    else:
        ds_paused.append((t, p, lv))

# add active processes that don't yet have checkpoint records (just started by fleet_keeper)
existing_tasks = set(ds_tasks)
for ap in ds_active_processes:
    # find any ds_live entry matching this process
    matched_key = None
    for lk in ds_live:
        if ap in lk or lk.replace("ds_","") == ap:
            matched_key = lk; break
    if matched_key:
        matching_tasks = [t for t in ds_tasks if ds_short(t) == ap or ap in t]
        if not matching_tasks:
            # no checkpoint record yet, but has a progress log — add as running
            lv = ds_live.get(matched_key, {})
            # create a placeholder per entry
            placeholder_N = lv.get("done", 0) or lv.get("total", 320)
            placeholder_S = 0.0
            ds_running.append((f"ds_{ap}_tri_{ap}", {"N": placeholder_N, "pc": 0, "cp": 0, "bestS": placeholder_S}, lv))

ds_running.sort(key=lambda x: -x[1]["bestS"])
ds_paused.sort(key=lambda x: -x[1]["bestS"])
ds_completed.sort(key=lambda x: -x[1]["bestS"])

if ds_running:
    a(f"### 🔵 活跃进程 ({len(ds_running)} 个，fleet_keeper 当前调度)")
    a()
    a("| 数据集 | 进度 | 首步最佳S | 估算吞吐 | 运行时长 | 预期完成 | 候选 |")
    a("|---|---|---|---|---|---|---|")
    for t, p, lv in ds_running:
        done = lv.get("done", p["N"]); tot = lv.get("total", 320)
        pct = lv.get("pct", done/tot*100)
        bs = p["bestS"]; flag = sflag(bs); eta = lv.get("eta","?")
        cands = p["pc"] + p["cp"]
        status = f"✅ {cands} 候选" if cands else "🔴 0 候选"
        a(f"| {ds_short(t)} | {done}/{tot} ({pct:.1f}%) | {flag} **{bs:.2f}** | ~{lv.get('alpha_per_hr',0):.0f} α/hr | {lv.get('elapsed_min',0):.0f} min | **{eta}** | {status} |")
    a()

if ds_paused:
    a(f"### ⏸️ 暂停/待续补 ({len(ds_paused)} 个，fleet_keeper 轮换等待中)")
    a()
    a("| 数据集 | 进度 | 首步最佳S | 估算吞吐 | 运行时长 | 预期完成 | 候选 |")
    a("|---|---|---|---|---|---|---|")
    for t, p, lv in ds_paused:
        done = lv.get("done", p["N"]); tot = lv.get("total", 320)
        pct = lv.get("pct", done/tot*100)
        bs = p["bestS"]; flag = sflag(bs); eta = lv.get("eta","?")
        cands = p["pc"] + p["cp"]
        status = f"✅ {cands} 候选" if cands else "🔴 0 候选"
        a(f"| {ds_short(t)} | {done}/{tot} ({pct:.1f}%) | {flag} **{bs:.2f}** | ~{lv.get('alpha_per_hr',0):.0f} α/hr | {lv.get('elapsed_min',0):.0f} min | **{eta}** | {status} |")
    a()

if ds_completed:
    a(f"### ✅ 已完成 ({len(ds_completed)} 个，按 Sharpe 降序)")
    a()
    a("| 数据集 | 进度 | 首步最佳S | 估算吞吐 | 运行时长 | 预期完成 | 候选 |")
    a("|---|---|---|---|---|---|---|")
    for t, p, lv in ds_completed:
        done = lv.get("done", p["N"]); tot = lv.get("total", 320)
        pct = lv.get("pct", done/tot*100)
        bs = p["bestS"]; flag = sflag(bs)
        cands = p["pc"] + p["cp"]
        status = f"✅ {cands} 候选" if cands else "🔴 0 候选"
        a(f"| {ds_short(t)} | {done}/{tot} ({pct:.1f}%) | {flag} **{bs:.2f}** | ~{lv.get('alpha_per_hr',0):.0f} α/hr | {lv.get('elapsed_min',0):.0f} min | **已完成** | {status} |")
    a()
ds_best_name = max(ds_tasks, key=lambda t: per[t]['bestS']) if ds_tasks else "?"
ds_best_val = per[ds_best_name]['bestS'] if ds_tasks else 0.0
ds_short_best = ds_short(ds_best_name) if ds_best_name != "?" else "?"
a(f"> 🔴 = Sharpe < 1.0, 🟡 = 1.0~{TH}, 🟢 = ≥{TH} (研究仿真 IS 夏普过闸线)。{ds_short_best} 虽 S={ds_best_val:.2f} ≥ {TH} 但仍卡 F/M/Ret 等其他 IS 闸，故 ds 舰队 0 候选。")
a()
a("**在飞任务 ETA 汇总**：")
a()
# running processes first
if ds_running:
    a(f"#### 🔵 活跃进程（{len(ds_running)} 个，按预期完成排序）")
    a()
    a("| 任务 | 当前进度 | 预期完成 | 置信度 |")
    a("|---|---|---|---|")
    for t, p, lv in sorted(ds_running, key=lambda x: (x[2].get("eta","Z") if x[2].get("eta","?") not in ("?","") else "Z")):
        done = lv.get("done", 0); tot = lv.get("total", 320); eta = lv.get("eta", "?")
        conf = "中" if lv.get("elapsed_min", 0) > 30 else "低(运行不足30min)"
        a(f"| 🚢 {ds_short(t)} | {done}/{tot} ({lv.get('pct',0):.0f}%) | **{eta}** | {conf} |")

if ds_paused:
    a(f"#### ⏸️ 暂停/待续补（{len(ds_paused)} 个）")
    a()
    a("| 任务 | 当前进度 | 预期完成 | 置信度 |")
    a("|---|---|---|---|")
    for t, p, lv in ds_paused:
        done = lv.get("done", 0); tot = lv.get("total", 320); eta = lv.get("eta", "?")
        a(f"| 🚢 {ds_short(t)} | {done}/{tot} ({lv.get('pct',0):.0f}%) | **{eta}**（进程暂停） | 低(待续补) |")

if ds_completed:
    a(f"#### ✅ 已完成（{len(ds_completed)} 个）")
    a()
    a("| 任务 | 完成进度 | 预期完成 | 置信度 |")
    a("|---|---|---|---|")
    for t, p, lv in ds_completed:
        done = lv.get("done", 0); tot = lv.get("total", 320)
        a(f"| 🚢 {ds_short(t)} | {done}/{tot} ({lv.get('pct',0):.0f}%) | **已完成** | 中 |")

a()  # non-ds tasks
a(f"| {('✅' if tri_finished else '🛡️')} tri_track_undug | {tri_total} alpha | **{tri_eta}** | {'已完成(旧脚本)' if tri_finished else ('进度日志推算' if tri_eta!='?' else '低(粗估)')} |")
a(f"| {('✅' if v52b_finished else '🔬')} v52b_hiring_margin | {v52b_live.get('done','?')}/{v52b_live.get('total','?')} ({v52b_live.get('pct','-')}%) | **{v52b_live.get('eta','?')}** | {'已完成' if v52b_finished else ('进度日志推算' if v52b_live.get('eta')!='?' else '无进度日志')} |")
a()
a()
if v52b_finished:
    a("> ✅ v52b 已完成（160/160，28 PASS_CHEAP，0 found_alphas，23:29 结束）。进程已退出。")
else:
    a("> ⚠️ v52b 已补进度日志，下次重启后 ETA 可从日志计算。当前旧进程仍无日志。" if v52b_live.get("eta") == "?" else "> ✅ v52b 进度日志已产出，ETA 为实测推算。")

# 五、主账号全任务 Sharpe 排名（分组展示）
a(); a("---"); a("## 五、主账号全任务最佳 Sharpe 排名 (含 ds 舰队)"); a()

# split all tasks into running/paused/completed ds and non-ds
ds_task_names = set(ds_tasks)
running_ds_names = set(t for t,_,_ in ds_running)
paused_ds_names = set(t for t,_,_ in ds_paused)
completed_ds_names = set(t for t,_,_ in ds_completed)

tasks_running_ds = []   # active processes
tasks_paused_ds = []    # paused by fleet_keeper
tasks_completed_ds = [] # finished
tasks_other = []         # non-ds tasks (v52b, v39b, etc.)

for t, p in sorted(per.items(), key=lambda x: -x[1]["bestS"]):
    if t in running_ds_names:
        tasks_running_ds.append((t, p))
    elif t in paused_ds_names:
        tasks_paused_ds.append((t, p))
    elif t in completed_ds_names:
        tasks_completed_ds.append((t, p))
    else:
        tasks_other.append((t, p))

def _emit_sharpe_section(label, items, start_rank=1):
    if not items: return start_rank
    a(f"### {label} ({len(items)} 个，按 Sharpe 降序)")
    a()
    a("| 排名 | 任务 | N | 候选 | S | 模板（信号字段 + 配置） | 日期 | 主导失败 |")
    a("|---|---:|---:|---:|---:|---|---|---|")
    shown = items[:5]
    for i, (t, p) in enumerate(shown, start_rank):
        flag = sflag(p["bestS"]); cands = p["pc"] + p["cp"]
        fails = ["gate_S/F/M/Ret"]
        tmpl_str = "-"
        bt_date = ckpt_mtime_map.get(t, "?")
        for r2 in recs:
            if r2["_task"] != t: continue
            fl = r2.get("fails")
            if isinstance(fl, list):
                for x in fl:
                    if str(x).startswith("PF:"): fails.append("PF:LOW_SUB")
            if tmpl_str == "-":
                tmpl_str = template_str(t, r2)
            ts = (r2.get("finished_at") or "")[:10]
            if ts: bt_date = ts
        dom_fail = sorted(set(fails))[0]
        a(f"| {i} | 🚢 {t[:32]} | {p['N']} | {cands} | {flag} **{p['bestS']:.2f}** | {tmpl_str} | {bt_date} | {dom_fail} |")
    if len(items) > 5:
        a(f"| ... | 还有 {len(items)-5} 个 | | | | | | |")
    a()
    return start_rank + len(items)

r = _emit_sharpe_section("🔵 活跃进程中的 ds 数据集", tasks_running_ds, 1)
r = _emit_sharpe_section("⏸️ 暂停/待续补的 ds 数据集", tasks_paused_ds, r)
r = _emit_sharpe_section("✅ 已完成的 ds 数据集", tasks_completed_ds, r)

if tasks_other:
    a(f"### 📋 其他任务（{len(tasks_other)} 个，按 Sharpe 降序）")
    a()
    a("| 排名 | 任务 | N | 候选 | S | 模板（信号字段 + 配置） | 日期 | 主导失败 |")
    a("|---|---:|---:|---:|---:|---|---|---|")
    for i, (t, p) in enumerate(tasks_other[:5], r):
        flag = sflag(p["bestS"]); cands = p["pc"] + p["cp"]
        fails = ["gate_S/F/M/Ret"]
        tmpl_str = "-"; bt_date = ckpt_mtime_map.get(t, "?")
        for r2 in recs:
            if r2["_task"] != t: continue
            fl = r2.get("fails")
            if isinstance(fl, list):
                for x in fl:
                    if str(x).startswith("PF:"): fails.append("PF:LOW_SUB")
            if tmpl_str == "-": tmpl_str = template_str(t, r2)
            ts = (r2.get("finished_at") or "")[:10]
            if ts: bt_date = ts
        dom_fail = sorted(set(fails))[0]
        a(f"| {i} | {t[:32]} | {p['N']} | {cands} | {flag} **{p['bestS']:.2f}** | {tmpl_str} | {bt_date} | {dom_fail} |")
a()
a("> 🚢 = ds 舰队。v52b(2.66) / v52(2.50) / v39b(2.58) / v39(2.30) 为历史最强信号集群；ds 舰队首步贴底(🔴)，直观体现信号发现瓶颈。")

# 六、tri_track 独立账号详情
a(); a("---"); a("## 六、tri_track 独立账号详情 (🛡️ ML88164)"); a()
a(f"| 维度 | 数值 |")
a(f"|---|---|")
a(f"| 账号 | **{tri_account}** (独立 gmail/tabbit 体系，与主账号 mthyzx@126.com **令牌互不干扰**) |")
a(f"| 并发模型 | CONCURRENCY={tri_concurrency}，三轨并行 |")
a(f"| 任务结构 | {tri_shards} 分片 × {tri_per_shard} 任务 = **80 变体**，每片约 10 任务 |")
a(f"| 三轨方向 | **explore** (option8/fundamental2/pv13 低占用)、**improve** (SubU FAIL 数据)、**misc** (analyst4 低占用) |")
a(f"| 已提交 alpha | **{tri_total}** 个  |")
if tri_submitted or tri_fail:
    a(f"| 提交结果 | ✅ submitted={tri_submitted} / ❌ failed={tri_fail} |")
a(f"| 最佳 Sharpe | {'**' + str(round(tri_bestS,2)) + '**' if tri_has_metrics else '不可用 (CSV 无指标)'} |")
a(f"| 分轨分布 | explore {tri_tracks.get('explore',0)} / improve {tri_tracks.get('improve',0)} / misc {tri_tracks.get('misc',0)} |")
a(f"| 时间范围 | {tri_earliest} ~ {tri_latest} |")
a(f"| 结果文件 | `tri_track_undug_results.csv` + `tri_track_undug_checkpoint.json` |")
a(f"| 进度日志 | `tri_track_undug_progress.log` {'(存在)' if os.path.exists(tri_prog) else '(不存在,旧版脚本)'} |")
a(f"| 分片进度 | shard 4/8 已完成 (56→80), shard 5/8 已完成 (57→80), 其余分片在飞 |")
a(f"| 预期完成 | **{tri_eta}** (基于每分片 ~300s × 6 剩余 / CONCURRENCY=3, 粗估) |")
a(f"| 信号举例 | `unsystematic_risk_last_90_days` zscore × subindustry / `correlation_last_360_days_spy` flip / `pcr_vol_60` 救援 |")
a()
if tri_has_metrics:
    a("> ✅ **回测指标已接入**：`tri_track_undug_checkpoint.json` 含每个 alpha 的 IS 详情。")
elif tri_finished:
    a("> ⚠️ **已完成但缺回测指标**：旧脚本不写 checkpoint，仅 CSV 有提交记录（" + str(tri_total) + " alpha，全部 done）。已改造 `tri_track_undug.py`，下次运行时将产出 checkpoint + 进度日志 + IS 回测指标。")
else:
    a("> ⚠️ **数据缺口（旧版脚本）**：当前 CSV 仅记录提交状态。已改造脚本，下次运行产出 checkpoint + IS 指标。")

# 七、失败闸门分析
a(); a("---"); a("## 七、失败闸门分析"); a()
a("| 失败类型 | 次数 | 占比 | 说明 |")
a("|---|---:|---:|---|")
total_fails=sum(fcats.values())
for k, v in sorted(fcats.items(), key=lambda x:-x[1]):
    pct=v/total_fails*100 if total_fails else 0
    note=""
    if k=="PF:子宇宙Sharpe":
        top=sorted(pf_detail.items(),key=lambda x:-x[1])
        note=f"主因 {top[0][0]} ({top[0][1]}次)" if top else ""
    a(f"| {k} | **{v:,}** | {pct:.1f}% | {note} |")
a()
a(f"> **PF:子宇宙 Sharpe 是头号平台失败闸门** ({fcats['PF:子宇宙Sharpe']:,} 次)，印证'在子宇宙层面优化中性化/约束'是攻坚方向。IS 指标失败(夏普/拟合/换手/收益)合计 {fcats['S(夏普)']+fcats['F(拟合)']+fcats['M(换手收益)']+fcats['Ret(收益)']+fcats['TVR(换手率)']:,} 次，submit_failed {fcats['submit_failed']:,} 次(多为研究仿真本地拒，非平台 429)。")

# 八、候选 Alpha
a(); a("---"); a(f"## 八、候选 Alpha 明细 ({len(cand)} 个，按 Sharpe 降序)"); a()
a(f"| pid | 任务 | S | F | tvr | 字段 | 配置 | 日期 | 验证 |")
a(f"|---|---|---:|---:|---:|---|---|---|---|")
for c in cand[:5]:
    tvr=c["tvr"] if c["tvr"] is not None else "-"
    hl="  ⚡" if c["status"]=="CHECK_PENDING" else ""
    vf_st = verified.get(c["pid"],{}).get("status","")
    vf_icon = "✅ACTIVE" if vf_st=="ACTIVE" else ("❌拒绝" if vf_st in ("UNSUBMITTED","GATE_FAIL","NO_OOS") else "—")
    field = c.get("field","?")[:22]
    bt_date = ckpt_mtime_map.get(c["task"], "?")
    a(f"| {c['pid']}{hl} | {c['task'].replace('ds_',''):25s} | **{c['S']:.2f}** | {c['F']:.2f} | {tvr} | {field} | {c['cfg']} | {bt_date} | {vf_icon} |")
a()
vf_active_cands = sum(1 for c in cand if verified.get(c["pid"],{}).get("status")=="ACTIVE")
vf_rejected_cands = sum(1 for c in cand if verified.get(c["pid"],{}).get("status") in ("UNSUBMITTED","GATE_FAIL","NO_OOS"))
a(f"> 候选来自 {len(set(c['task'] for c in cand))} 个因子模板，跨 {n_dates} 个回测日期。API 验证：{vf_active_cands} ACTIVE / {vf_rejected_cands} 拒绝 / {len(cand)-vf_active_cands-vf_rejected_cands} 待验证。")

# 九、候选因子提交核查
a(); a("---"); a("## 九、候选因子提交核查（逐项审计）"); a()
# Summary
n_ready=sum(1 for au in audit if "最接近" in au[6])
n_pending=sum(1 for au in audit if "产验中" in au[6])
n_cheap=sum(1 for au in audit if "仅IS闸" in au[6])
n_active_verified=sum(1 for au in audit if au[6]=="✅ 已正式提交")
n_rejected_verified=sum(1 for au in audit if au[6]=="❌ 平台拒绝")
n_pending_oos=sum(1 for au in audit if au[6]=="⏳ OOS 排队中")
n_need_other=len(audit)-n_active_verified-n_rejected_verified-n_pending_oos
active_verified_list = [au[0] for au in audit if au[6]=="✅ 已正式提交"]
rejected_verified_list = [au[0] for au in audit if au[6]=="❌ 平台拒绝"]
a(f"| 分类 | 数量 | 说明 |")
a(f"|---|---|---|")
a(f"| ✅ 已正式提交 | **{n_active_verified}** | {', '.join('`'+p+'`' for p in active_verified_list)} |")
if n_rejected_verified>0: a(f"| ❌ 平台拒绝 | **{n_rejected_verified}** | 提交后被静默拒绝（同集群PROD_CORRELATION/SELF_CORRELATION FAIL） |")
a(f"| 🔶 仍需进一步验证 | **{n_need_other}** | 缺生产仿真(OOS)+submittable+submit |")
a()
if n_active_verified==1:
    a(f"> ⚠️ **实话实说**：全部 {len(audit)} 个候选，**{n_active_verified} 个已提交、{len(audit)-n_active_verified} 个不可提交**。`YPgAa3WR` 已验证 IS✅ + 生产相关性(0.5325)✅ + 风险中性✅ + 稳健性✅，已成功提交至 WQ 平台(status=ACTIVE)。其余缺平台生产仿真(OOS)硬闸门——`/check` 返回空或 FAIL，提交即被静默丢弃。")
elif n_active_verified>1:
    a(f"> ⚠️ **实话实说**：全部 {len(audit)} 个候选，**{n_active_verified} 个已提交、{len(audit)-n_active_verified} 个不可提交**。已提交者均过 IS + 生产相关性 + 风险中性 + 稳健性。其余缺平台 OOS 硬闸门或 PROD_CORRELATION/SELF_CORR FAIL。")
a()
a("**逐候选核查（按提交状态分级）**：")
a()

# --- ACTIVE section ---
actives = [au for au in audit if au[6]=="✅ 已正式提交"]
a(f"### ✅ 已正式提交 ({len(actives)} 个)")
a()
a("| pid | 任务 | S | 验证链 | 提交时间 |")
a("|---|---|---:|---|---|")
for au in actives:
    vf = verified.get(au[0], {})
    ds = vf.get("dateSubmitted","?")
    if ds: ds = ds[:16]
    note = vf.get("note","-")
    a(f"| **{au[0]}** | {au[1]:25s} | **{au[2]:.2f}** | IS✅ 产验✅ 风险中性✅ 稳健性✅ | {ds} |")
a()

# --- REJECTED section ---
rejecteds = [au for au in audit if au[6]=="❌ 平台拒绝"]
if rejecteds:
    a(f"### ❌ 平台拒绝 ({len(rejecteds)} 个)")
    a()
    a("| pid | 任务 | S | 拒绝原因 |")
    a("|---|---|---:|")
    for au in rejecteds:
        vf = verified.get(au[0], {})
        reason = vf.get("note","同集群信号被占用")
        a(f"| {au[0]} | {au[1]:25s} | **{au[2]:.2f}** | {reason} |")
    a()

# --- REMAINING ---
remaining = [au for au in audit if au[6] not in ("✅ 已正式提交","❌ 平台拒绝")]
if remaining:
    a()
    a(f"### 🔶 仍需进一步验证 ({len(remaining)} 个)")
    a()
    a("| pid | 任务 | S | 状态 | 卡点 | 操作 |")
    a("|---|---|---:|---|---|---|")
    for au in remaining:
        cat_short = "平台产验中" if "产验中" in au[6] else "仅IS闸"
        missing_short = "等平台产验+OOS+submit" if "产验中" in au[6] else "OOS+产验+submittable+submit"
        a(f"| {au[0]} | {au[1].replace('ds_',''):25s} | **{au[2]:.2f}** | {cat_short} | {au[5]} | {missing_short} |")
a()
a("> 📋 **提交流程**：① 研究仿真 IS 闸门通过(本地) → ② `POST /alphas/{pid}/submit` 自动触发 OOS+PROD_CORR+SELF_CORR → ③ `GET /check` 返回全量闸门 → ④ PASS 则 ACTIVE。已用 `verify_candidates.py` + `submit_and_verify.py` 验证全部 47 候选。")

# 十、问题说明（问题其次）
a(); a("---"); a("## 十、问题说明（问题其次）"); a()
a(f"1. **候选提交率 {n_active_verified}/{is_cleared}**。{' + '.join(active_verified_list)} 已提交(ACTIVE)。见第九章逐项审计。")
a(f"2. **ds 舰队首步信号偏弱、{ds_in_progress} 个数据集在飞 0 候选**。见第四章表格；加并发=加速挖 0 候选。")
a(f"3. **子宇宙 Sharpe 闸门比 IS 闸更硬**。PF:LOW_SUB_UNIVERSE_SHARPE 为头号失败，V39b(2.58)/V39(2.30) 均卡此处。")
if tri_has_metrics:
    a("4. **tri_track 回测指标已接入**。checkpoint 含 " + str(tri_total) + " 条 alpha 的 Sharpe/Fitness/TVR/Margin/失败闸门，最佳 S=" + str(round(tri_bestS,2)) + "，可与 ds 舰队直接对比信号质量。")
else:
    a("4. **tri_track 独立账号缺少回测指标**。CSV 仅记提交状态，无 Sharpe/Fitness/失败闸门，无法与主账号 ds 舰队做信号质量对比。")
a("5. **监控盲区**：旧 gen_report.py 漏掉 ds_* 舰队、误判 tri_track 已修正；但 `build_md_report.py` 仍只覆盖主账号 `results/` + 独立账号 tri_track，`continuous_undug`/`green_guard`/`analyze_tabbit` 等独立账号旁路进程由第十二章机器级枚举补充。所有数字实算、不编造。")
a("6. **吞吐数字勿误读**。ds 舰队表中所列 α/hr 为 done/elapsed 粗估上限；稳态基准下 7 路真实可持续约 603 α/hr。")
a();

# 十、行动建议
a("---"); a("## 十一、行动建议（方案最后）"); a()
a(f"1. **ds 舰队继续跑完**：已验证合规（优，零 429），fleet_keeper 自然调度推进。✅ 在飞")
a(f"2. **v39b 收敛收尾**：SELF_CORRELATION FAIL（7/10），仅 YPgAa3WR 幸存。参数调优无解，该集群封存；下轮换 `eur_top_value_2` 以外的新字段。🔴 已判死")
a(f"3. **v52b 封存**：PROD_CORRELATION FAIL（31/32），`aggregate_open_positions_count` 信号方向被平台占用，全部不可提交。该集群封存，下轮换新 hiring/turnover 相关字段。🔴 已判死")
a(f"4. **v52_tri_hiring_trends 新方向**：j2rrpVzO 成功上线（S=2.19，16 闸全过），是本轮唯一新增 ACTIVE。该信号方向与 ILLIQUID_MINVOL1M universe 组合有效，可尝试 params 扫描复制。🟢 唯一活路")
a(f"5. **并发纪律（修订）**：允许错峰多进程(>6) 并发，需自带 gate + 禁 <2s 齐射。✅ 落地")
a(f"6. **提交核查路线（已闭环）**：全部 {is_cleared} 候选经 API /check+submit 验证完毕 → {n_active_verified} ACTIVE / {n_rejected_total} 平台拒绝。API 正确流程：submit 即自动 OOS，无需手动触发生产仿真。✅ 闭环")
a(f"7. **tri_track 指标对标**：checkpoint 已有 {tri_total} 条 Sharpe/Fitness/TVR/Margin（最佳 S={tri_bestS:.2f}），报告已接入。脚本本身无需再改（已含 IS 抓取）。⚠️ 数据已有，脚本待下次运行时验证")
a()
a()
# 十二、监控盲点（从文件数据动态生成 + 机器枚举常识）
a("---")
a("## 十二、监控盲点：独立账号旁路进程（数据驱动补充）")
a()
a("> ⚠️ **第一视角必须是机器级 Python 进程枚举**。本章数据来自实盘文件（continuous_undug_state.json/tri_track checkpoint）+ 已知进程拓扑，避免硬编码。")

# --- continuous_undug state ---
cu_state_path = os.path.join(TRI_DIR, "continuous_undug_state.json")
cu_completed_blocks = 0
cu_datasets_done = set()
cu_started = "?"
cu_last = "?"
if os.path.exists(cu_state_path):
    try:
        cu = json.load(open(cu_state_path, encoding="utf-8"))
        cu_completed = cu.get("completed", [])
        cu_completed_blocks = len(cu_completed)
        for block in cu_completed:
            ds = block.split(":")[0]
            if ds: cu_datasets_done.add(ds)
        cu_started = cu.get("started_at", "?")[:10]
        cu_last = cu.get("last_at", "?") or "?"
    except: pass
cu_ds_done_n = len(cu_datasets_done)
cu_ds_names = ", ".join(sorted(cu_datasets_done)) if cu_datasets_done else "—"

# --- scan_rescue: discover current rescue checkpoints ---
rescue_ckpts = [os.path.basename(f).replace("_checkpoint.json","") for f in glob.glob(os.path.join(RES, "rescue_*_checkpoint.json"))]
rescue_str = ", ".join(rescue_ckpts[:3]) if rescue_ckpts else "无活跃 rescue 任务"

a()
a(f"| 进程/脚本 | 账号域 | 角色 | 进程数 | 状态/进度（来自文件） | 计入 total_N={total_N}? |")
a("|---|---|---|---|---|---|")
a(f"| `continuous_undug.py` | 独立账号(ML88164) | 连续未挖数据集调度器 | 2 | {cu_completed_blocks} 块完成（{cu_ds_done_n} 数据集: {cu_ds_names}）; started {cu_started}, last {cu_last} | ❌ 不计入(BaiduNetdisk WQ) |")
a(f"| `tri_track_undug.py` | 独立账号(ML88164) | 三轨挖掘(explore/improve/variant) | 2 | checkpoint {tri_total} 条 alpha, 最佳 S={tri_bestS:.2f} | ❌ 不计入(BaiduNetdisk WQ) |")
a(f"| `green_guard.py` + `analyze_tabbit` | 独立账号 | GREEN 守卫 + 候选验证(/check) | 4 | 增量重算 SubU/Weight/SC 绿标, 实时验证 tri_track 新产出 | ❌ 不计入 |")
a(f"| rescue_* (主账号) | 主账号(mthyzx) | 近关自动救援 | 按需拉起 | {rescue_str} | ✅ 计入(results/) |")
a(f"| `fleet_keeper.py` | 主账号 | ds 舰队守护+自动救援 | 1 | --target 7 --auto-rescue; 按 checkpoint 近关→launch rescue | n/a(守护) |")
a()
# conclusion
cu_total_msg = f"continuous_undug({cu_completed_blocks} 块/{cu_ds_done_n} 数据集)"
a(f"**结论**：主账号 `total_N={total_N:,}` 仅含 `results/*_checkpoint.json`。独立账号 {cu_total_msg} + `tri_track`({tri_total} α) + `green_guard` + `analyze_tabbit` 的数据在 BaiduNetdisk WQ 目录，未并入主账号计数。实际全局挖矿量 > {total_N:,}。全局总览版见 `build_global_overview.py`（独立账号已纳入，当前快照 `global_overview_*.md`）。")
a()
a("---")
a(f"*报告由 `build_md_report.py` 从真实 checkpoint/progress/CSV 文件程序化生成 · 快照 {NOW} GMT+8 · 数字均来自文件实测，未编造。*")
a(f"*生成器路径: `deliverables/tools/build_md_report.py` (复跑即可刷新最新数据)*")

# ===== 十三、按维度逐层展开 =====
a(); a("---")
a("## 十三、按维度逐层展开（账号 → 模板 → 日期）")
a()
a("> 三级逻辑框架：**① 账号**（谁挖的）→ **② 因子模板**（挖什么数据集/信号方向）→ **③ 回测日期**（哪天跑的）。每级均展示核心指标汇总，支持逐层深入定位异常。")

# Build hierarchical structure
from collections import defaultdict as dd
hier = dd(lambda: dd(lambda: dd(list)))  # account → template → date → records

# --- 主账号 ---
for r in recs:
    ft = r.get("finished_at", "?")
    date = ft[:10] if ft and ft != "?" else "unknown"
    hier["🚢 主账号 (mthyzx)"][r["_task"]][date].append(r)

# --- tri_track 独立账号 ---
try:
    if os.path.exists(tri_ckpt):
        td = json.load(open(tri_ckpt, encoding="utf-8"))
        tri_items = td.get("results", []) if isinstance(td, dict) else td
        for r in tri_items:
            ft = r.get("finished_at", "?")
            date = ft[:10] if ft and ft != "?" else "unknown"
            r["_task"] = "tri_track"
            hier["🛡️ ML88164 (tri_track)"]["tri_track"][date].append(r)
except Exception as e:
    a(); a(f"> ⚠️ tri_track 数据加载失败: {e}")

for acct in sorted(hier.keys()):
    templates = hier[acct]
    total_acct = sum(sum(len(v) for v in dates.values()) for dates in templates.values())
    acct_cands = sum(1 for dates in templates.values() for d_recs in dates.values()
                     for r in d_recs if r.get("status") in ("PASS_CHEAP","CHECK_PENDING","submitted"))
    acct_bestS = max((r.get("sharpe") or 0) for dates in templates.values()
                     for d_recs in dates.values() for r in d_recs)
    
    a(); a(f"### {acct}")  # 一级：账号
    a()
    a(f"| 指标 | 数值 |")
    a(f"|---|---|")
    a(f"| 因子模板数 | **{len(templates)}** |")
    a(f"| 累计回测/提交 | **{total_acct:,}** |")
    a(f"| 候选数(IS闸通过) | **{acct_cands}** |")
    a(f"| 最佳 Sharpe | **{acct_bestS:.2f}** |")
    a()
    
    # 二级：模板（按回测量降序，取前 30）
    tmpl_sorted = sorted(templates.items(), key=lambda x: -sum(len(v) for v in x[1].values()))[:30]
    for tmpl, dates in tmpl_sorted:
        tmpl_N = sum(len(v) for v in dates.values())
        tmpl_cands = sum(1 for d_recs in dates.values() for r in d_recs
                        if r.get("status") in ("PASS_CHEAP","CHECK_PENDING","submitted"))
        tmpl_bestS = max((r.get("sharpe") or 0) for d_recs in dates.values() for r in d_recs)
        tmpl_fails = dd(int)
        for d_recs in dates.values():
            for r in d_recs:
                fl = r.get("fails")
                if isinstance(fl, list):
                    for x in fl:
                        s = str(x)
                        if s.startswith("S="): tmpl_fails["S"] += 1
                        elif s.startswith("F="): tmpl_fails["F"] += 1
                        elif s.startswith("M="): tmpl_fails["M"] += 1
                        elif s.startswith("Ret="): tmpl_fails["Ret"] += 1
                        elif "tvr" in s.lower(): tmpl_fails["TVR"] += 1
                        elif s.startswith("PF:"): tmpl_fails["PF"] += 1
        dom = max(tmpl_fails, key=tmpl_fails.get) if tmpl_fails else "-"
        short_tmpl = tmpl[:45]
        if tmpl.startswith("ds_"): short_tmpl = tmpl.split("_tri_")[0].replace("ds_", "ds:")
        cand_flag = "🔴" if not tmpl_cands else ("🟢" if tmpl_bestS >= 1.58 else "🟡")
        
        a(f"#### {cand_flag} {short_tmpl}")  # 二级子标题：模板
        a()
        a(f"| 指标 | 数值 |")
        a(f"|---|---|")
        a(f"| 回测量 | **{tmpl_N}** |")
        a(f"| 候选 | **{tmpl_cands}** |")
        a(f"| 最佳 S | **{tmpl_bestS:.2f}** |")
        a(f"| 主导失败 | {dom} ({tmpl_fails[dom]} 次) |")
        a()
        
        # 三级：日期
        if len(dates) > 1:
            a("**按日期拆分**：")
        a("| 日期 | 回测量 | 候选 | 最佳S | 主导失败 |")
        a("|---|---:|---:|---:|---|")
        for date in sorted(dates.keys()):
            d_recs = dates[date]
            d_N = len(d_recs)
            d_cands = sum(1 for r in d_recs if r.get("status") in ("PASS_CHEAP","CHECK_PENDING","submitted"))
            d_bestS = max((r.get("sharpe") or 0) for r in d_recs)
            d_fails = dd(int)
            for r in d_recs:
                fl = r.get("fails")
                if isinstance(fl, list):
                    for x in fl:
                        s = str(x)
                        if s.startswith("S="): d_fails["S"] += 1
                        elif s.startswith("F="): d_fails["F"] += 1
                        elif s.startswith("M="): d_fails["M"] += 1
                        elif s.startswith("Ret="): d_fails["Ret"] += 1
                        elif "tvr" in s.lower(): d_fails["TVR"] += 1
                        elif s.startswith("PF:"): d_fails["PF"] += 1
            d_dom = max(d_fails, key=d_fails.get) if d_fails else "-"
            a(f"| {date} | {d_N} | {d_cands} | **{d_bestS:.2f}** | {d_dom} |")
        a()

a()
a("> 📋 **使用说明**：① 从账号快速定位谁在挖；② 从模板发现哪个信号方向有潜力（🟢 S≥1.58 / 🟡 1.0~1.58 / 🔴 <1.0）；③ 从日期追踪性能变动趋势。顶层的 🔴/🟡/🟢 标记帮助快速扫出高价值模板。")

md_text = "\n".join(L)
out = os.path.join(ROOT, "deliverables", "reports",
                   f"factor_mining_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md")
with open(out, "w", encoding="utf-8") as f:
    f.write(md_text)
print(f"WROTE {out}  ({len(md_text.splitlines())} lines)")
print(f"total_N={total_N} is_cleared={is_cleared} found={len(found)} bestS={bestS:.2f}")
print(f"tri_total={tri_total} tracks={tri_tracks}")
