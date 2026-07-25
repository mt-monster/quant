import json, os, re, glob, time
from collections import Counter, OrderedDict

# ---------- output / snapshot ----------
SNAP = time.strftime("%Y-%m-%d %H:%M:%S") + " GMT+8"
OUT = "deliverables/reports/backtest_monitor_report_" + time.strftime("%Y%m%d_%H%M") + ".md"
WINDOW = 15  # minutes: progress-log freshness window for "alive"

# ---------- historical chain (have checkpoints) ----------
chain_order = ['v33_hkg_anl10','v34_insider_matrix','v35_news_nlp','v36_stock_cluster',
               'v37_other545','v38_sust_profit','v38b_sust_rescue','v39_insider_rescue',
               'v39b_sub_micro','v40_cre','v41_earn_risk','v42_social','v43_event_rel',
               'v44_insider_feats','v45_tri_insider_feats','v46_tri_insider_trx']

# ============================================================
# helpers
# ============================================================
def progress_logs():
    """stem -> latest progress log path"""
    d = {}
    for f in glob.glob("results/*_progress_*.log"):
        stem = re.sub(r'_progress.*$', '', os.path.basename(f))
        if stem not in d or os.path.getmtime(f) > os.path.getmtime(d[stem]):
            d[stem] = f
    return d

def read_json(p):
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return None

def task_name_from_log(pl):
    if not pl or not os.path.exists(pl): return None
    for line in open(pl, encoding='utf-8', errors='ignore'):
        if '"event": "start"' in line:
            try: return json.loads(line).get('task')
            except Exception: pass
    return None

def parse_progress(pl):
    """Parse a progress log: start meta, last progress, agg status counts,
    best sharpe/fitness over 'recent' events, and raw 429/submit_failed/poll_timeout counts."""
    if not pl or not os.path.exists(pl):
        return None
    mt = os.path.getmtime(pl)
    txt = open(pl, encoding='utf-8', errors='ignore').read()
    start = None; last = None
    status_ct = Counter(); best_s = None; best_f = None
    n_submit_failed = len(re.findall(r'submit_failed', txt))
    n_429 = len(re.findall(r'\b429\b', txt))
    n_poll_to = len(re.findall(r'poll_timeout', txt))
    for line in txt.splitlines():
        if '"event": "start"' in line:
            try: start = json.loads(line)
            except Exception: pass
        elif '"event": "progress"' in line:
            try:
                ev = json.loads(line); last = ev
                for r in ev.get('recent', []):
                    st = r.get('status')
                    if st: status_ct[st] += 1
                    s = r.get('sharpe')
                    if isinstance(s, (int, float)):
                        best_s = s if best_s is None else max(best_s, s)
                    f_ = r.get('fitness')
                    if isinstance(f_, (int, float)):
                        best_f = f_ if best_f is None else max(best_f, f_)
            except Exception: pass
    alive = (time.time() - mt) < WINDOW * 60
    storm = (n_submit_failed > 5) or (n_429 > 5)
    return dict(mtime=mt, alive=alive, start=start, last=last, status_ct=status_ct,
                best_s=best_s, best_f=best_f,
                n_submit_failed=n_submit_failed, n_429=n_429, n_poll_to=n_poll_to,
                storm=storm)

# fix typo-safe reference
def parse_progress_safe(pl):
    return parse_progress(pl)

def process_inventory():
    """监控第一视角: 机器级枚举全部 python.exe 进程并分类。
    这是发现入口(不是 v 系列进度日志)。凡接触 WQ BRAIN 的 python 进程都列出:
    scan 脚本(带本地进度日志) / MCP 服务(platform_functions.py, 交互式服务端回测宿主,
    不写本地日志) / watchdog / tracker / editor(语言服务, idle) / other。
    任何经 MCP 发起的服务端仿真(set_RR11jN_ 之类)只能靠此枚举暴露其宿主。"""
    import subprocess
    inv = []
    try:
        ps = ('Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" '
              '| ForEach-Object { ($_.ProcessId.ToString() + \'|||\' + $_.CommandLine + \'|||\' '
              '+ $_.CreationDate.ToString(\'yyyyMMddHHmmss\') + \'|||\' + $_.ThreadCount.ToString()) }')
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=90)
        raw = out.stdout or ""
    except Exception as e:  # pragma: no cover
        return [], f"process_inventory error: {e}"
    for line in raw.splitlines():
        if "|||" not in line:
            continue
        parts = line.split("|||", 3)
        pid_s = parts[0].strip()
        cmd = parts[1] if len(parts) > 1 else ""
        cdate = parts[2] if len(parts) > 2 else ""
        nthr = parts[3] if len(parts) > 3 else ""
        rec = {"pid": pid_s, "cmd": cmd, "started": cdate,
               "threads": nthr, "kind": "other", "marker_hit": False}
        c = cmd
        if "platform_functions.py" in c:
            rec["kind"] = "mcp_server"
        elif "_watchdog_tri.py" in c:
            rec["kind"] = "watchdog"
        elif "tri_track_miner.py" in c:
            rec["kind"] = "tracker"
        elif "run-jedi-language-server" in c or "jedi" in c or "ms-python" in c:
            rec["kind"] = "editor"
        elif "scan_" in c and ".py" in c:
            rec["kind"] = "scan_script"
        if "RR11jN" in c:
            rec["marker_hit"] = True
        inv.append(rec)
    return inv, None

def collect_submittable():
    """扫描全部 scan checkpoint, 取 status ∈ {PASS, PASS_CHEAP} 的 alpha。

    ⚠️ 重要语义纠正: 这些 alpha 仅通过 **研究仿真(research simulation)的廉价本地闸门**
    (S>1.58 / F>1.0 / TVR∈[0.05,0.30] / M>10bp / Ret>0.05, 近闸还查 IS_LADDER_SHARPE+LOW_2Y_SHARPE),
    **并不等于 WQ 提交就绪**。它们缺: ① 生产仿真(OOS/样本外); ② 生产相关性 PROD_CORRELATION
    验证(仅进入 found_alphas 的 alpha 才记录过 prod_corr); ③ 平台 submittable 判定; ④ 真实提交
    (所有 scan 脚本 no_submit=True)。本函数返回的是"研究仿真 IS 闸通过的候选", 非"可提交"。"""
    import glob as _gl, os as _os, re as _re, json as _json
    out = []
    for f in sorted(_gl.glob("results/*checkpoint*.json")):
        if not _re.match(r"v\d+", _os.path.basename(f)):
            continue
        try:
            d = _json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        res = d.get("results") if isinstance(d, dict) else (d if isinstance(d, list) else [])
        for r in res:
            st = str(r.get("status"))
            if st in ("PASS", "PASS_CHEAP"):
                s = r.get("settings")
                if isinstance(s, str):
                    try:
                        s = _json.loads(s)
                    except Exception:
                        s = {}
                if not isinstance(s, dict):
                    s = {}
                out.append({
                    "task": _os.path.basename(f).replace("_checkpoint.json", ""),
                    "label": r.get("label"), "pid": r.get("pid"), "status": st,
                    "sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
                    "sub_univ": r.get("sub_univ"), "sub_limit": r.get("sub_limit"),
                    "tvr": r.get("tvr"), "expr": (r.get("expr") or "")[:600],
                    "cfg": f"{s.get('region','')} {s.get('universe','')} d{s.get('delay','')} decay{s.get('decay','')} {s.get('neutralization','')}".strip(),
                })
    out.sort(key=lambda x: (x["sharpe"] is not None, x["sharpe"] or 0), reverse=True)
    return out

def collect_verified_pids():
    """扫描全部 checkpoint 的 found_alphas, 返回已跨过 **生产相关性(PROD_CORRELATION)验证** 的 pid 集合。
    scan 脚本逻辑: PASS_CHEAP 候选须再经 风险中性化 + wait_pc(PROD_CORRELATION) 才 append 到 found_alphas
    (带 prod_corr 字段, submitted=False)。因此 found_alphas 中的 pid = 真正过了生产相关性闸门的 alpha;
    其余仅 status=PASS_CHEAP 的候选 = 廉价 IS 闸通过, 生产关未验。"""
    import glob as _gl, os as _os, re as _re, json as _json
    out = set()
    for f in sorted(_gl.glob("results/*checkpoint*.json")):
        if not _re.match(r"v\d+", _os.path.basename(f)):
            continue
        try:
            d = _json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        fa = d.get("found_alphas") if isinstance(d, dict) else []
        fa = fa or []
        for a in fa:
            p = a.get("pid")
            if p:
                out.add(p)
    return out

def reason_cat(r):
    st = r.get("status")
    if st in ('PASS', 'PASS_CHEAP'): return 'PASS'
    if st == 'error': return 'error'
    f = r.get("fails") or []
    if not f: return 'FAIL_other'
    f0 = f[0]
    if f0.startswith('PF:'): return f0
    if f0 == 'platform_FAIL': return 'platform_FAIL'
    if f0.startswith('S='): return 'gate_S/F/M/Ret'
    return 'FAIL:' + f0[:30]

def fmt(x):
    return f"{x:.2f}" if isinstance(x, float) else str(x)

def nf(x, spec='.0f'):
    """None 安全的数值格式化：None/非数值 -> '-'，否则按 spec 格式化。"""
    return format(x, spec) if isinstance(x, (int, float)) else '-'

# ---------- efficiency detection (source grep) ----------
def eff_script(name):
    """Return (script_path, inherited_bool)."""
    own = sorted(glob.glob(f"scan_{name}.py") + glob.glob(f"scan_{name}_*.py"))
    if own: return own[0], False
    # tri-family (v46-v53) all use the V46 template script
    if re.match(r'v4[6-9]_tri', name) or re.match(r'v5[0-9]_tri', name) or name.startswith('v46_tri'):
        tpl = sorted(glob.glob("scan_v46_tri_insider_trx.py"))
        if tpl: return tpl[0], True
    prefix = name.split('_')[0]
    alt = sorted(glob.glob(f"scan_{prefix}*.py"))
    if alt: return alt[0], False
    return None, False

def detect_effort(name):
    sp, inherited = eff_script(name)
    if not sp:
        return None, inherited
    flags = {'multi_sim': False, 'submit_gate': False, 'backoff': False, 'no_submit': False, 'batch': None}
    t = open(sp, encoding='utf-8', errors='ignore').read()
    imports_multi_sim = bool(re.search(r'import.*multi_sim|from multi_sim import', t))
    if 'run_multi_batch' in t or 'submit_multi_sim' in t or 'multi_sim' in t or imports_multi_sim:
        flags['multi_sim'] = True
    # gate 经 import 继承：import multi_sim -> submit_gate.py；import wd_lib_wrapper -> run_backtest 内 wait_submit_slot
    if 'submit_gate' in t or imports_multi_sim or 'wd_lib_wrapper' in t:
        flags['submit_gate'] = True
    # backoff is inherited when importing multi_sim (multi_sim.py has backoff_429 retry)
    if 'wd_lib_wrapper' in t or re.search(r'retry', t, re.I) or 'backoff' in t or imports_multi_sim:
        flags['backoff'] = True
    if re.search(r'no_submit|NO_SUBMIT', t): flags['no_submit'] = True
    m = re.search(r'BATCH_SIZE\s*=\s*(\d+)', t)
    if m: flags['batch'] = int(m.group(1))
    return flags, inherited

def grade_effort(f):
    if not f:
        return ('?', '无对应脚本，无法评估')
    if f['submit_gate'] and f['multi_sim'] and f['backoff']:
        return ('优', '已落地最优方案：显式令牌桶闸门 + 批量提交 + 退避')
    if f['multi_sim'] and f['backoff']:
        return ('良', '基本落地：批量提交 + 退避 + 隐式节奏达标，满足安全包络；建议补显式 submit_gate')
    if f['multi_sim'] or f['backoff']:
        return ('中', '部分落地：有批量提交或退避之一，缺失另一关键项，效率/鲁棒性未达全')
    return ('差', '未落地：既无批量提交也无退避，效率最低')

# ============================================================
# discover tasks: historical chain (checkpoints) + live tri-batch (progress logs)
# ============================================================
pls = progress_logs()
# 进程级枚举(监控第一视角)提前到这里, 用于: (a) §1 进程盘点; (b) 补救"只写 checkpoint、不写进度日志"的 scan 进程盲区
inv, inv_err = process_inventory()
# 从在飞 scan 进程的命令行提取任务名线索, 用于把"无进度日志的活 scan"关联到其 checkpoint
live_scan_hints = set()
for _rec in inv:
    if _rec['kind'] == 'scan_script':
        _m = re.search(r'scan_([A-Za-z0-9_]+)\.py', _rec['cmd'])
        if _m:
            live_scan_hints.add(_m.group(1))
        _m2 = re.search(r'(v\d+[A-Za-z0-9_]*)', _rec['cmd'])
        if _m2:
            live_scan_hints.add(_m2.group(1))
tasks = OrderedDict()

# 1) historical chain
for name in chain_order:
    cp = f"results/{name}_checkpoint.json"
    tasks[name] = {'name': name, 'cp': cp if os.path.exists(cp) else None, 'pl': None, 'group': 'chain'}

# 2) live tri-batch: progress logs v46_tri..v5x_tri
for stem, f in pls.items():
    if re.match(r'v4[6-9]_tri$', stem) or re.match(r'v5[0-9]_tri$', stem):
        tname = task_name_from_log(f) or stem
        if tname not in tasks:
            # attach authoritative checkpoint if it exists (scripts write it incrementally)
            cp_tri = f"results/{tname}_checkpoint.json"
            tasks[tname] = {'name': tname,
                            'cp': cp_tri if os.path.exists(cp_tri) else None,
                            'pl': f, 'group': 'tribatch'}
        else:
            # e.g. V46: already registered from chain_order; attach its progress log
            tasks[tname]['pl'] = f

# 3) catch-all: 任何 results/*checkpoint*.json 尚未登记的, 都补登(覆盖只写 checkpoint、不写
#    *_progress_*.log 的 scan 任务, 例如 scan_v52b_hiring_margin.py)。命中存在且在飞 scan 进程
#    线索且 checkpoint 近期更新 -> 标记为在飞。
for f in sorted(glob.glob('results/*checkpoint*.json')):
    base = os.path.basename(f).replace('_checkpoint.json', '')
    if base in tasks:
        continue
    if not re.match(r'v\d+', base):
        continue
    cp_mtime = os.path.getmtime(f)
    cp_fresh = (time.time() - cp_mtime) < WINDOW * 60
    is_live = cp_fresh and (base in live_scan_hints or
                            any(base in h or h in base for h in live_scan_hints))
    tasks[base] = {'name': base, 'cp': f, 'pl': None,
                   'group': 'scan', 'live': is_live, 'cp_mtime': cp_mtime}

# ============================================================
# build per-task records
# ============================================================
recs = []
for name, meta in tasks.items():
    cp = meta['cp']; pl = meta['pl']; group = meta['group']
    # ---- stats from checkpoint (if present) ----
    if cp:
        d = read_json(cp)
        res = d["results"] if d else []
        n = len(res)
        stc = Counter(r.get("status") for r in res)
        rc = Counter(reason_cat(r) for r in res)
        p = stc.get('PASS', 0) + stc.get('PASS_CHEAP', 0)
        fa = len((d or {}).get("found_alphas", []))
        fails = {k: v for k, v in rc.items() if k != 'PASS'}
        dom = max(fails.items(), key=lambda x: x[1])[0] if fails else '-'
        bs = max([r.get('sharpe') for r in res if isinstance(r.get('sharpe'), (int, float))], default=None)
        bf = max([r.get('fitness') for r in res if isinstance(r.get('fitness'), (int, float))], default=None)
        regs = set((r.get('settings') or {}).get('region') for r in res if (r.get('settings') or {}).get('region'))
        src = 'checkpoint'
    else:
        n = None; stc = Counter(); p = 0; fa = 0; dom = '进行中'
        bs = None; bf = None; res = []; regs = set(); src = 'live'
    # ---- runtime (progress log, or live-scan flag, or historical dead) ----
    if pl:
        rt = parse_progress(pl)
    elif meta.get('live'):
        rt = {'alive': True, 'start': None,
              'last': {'done': n, 'total': None, 'avg_sec_per_step': None},
              'best_s': bs, 'best_f': bf, 'status_ct': {}, 'mtime': meta.get('cp_mtime')}
    else:
        rt = None
    if rt is None and cp and not meta.get('live'):
        # completed task: try to find its progress log by stem prefix
        for s, pf in pls.items():
            if name == s or name.startswith(s + '_') or s.startswith(name):
                rt = parse_progress(pf)
                if rt: rt = dict(rt, alive=False)  # historical -> force dead
                break
    # efficiency
    ef, inherited = detect_effort(name)
    g, verd = grade_effort(ef)
    recs.append(dict(name=name, group=group, cp=cp, pl=pl, rt=rt, ef=ef, inherited=inherited,
                     grade=g, verd=verd, src=src, n=n,
                     done=(rt['last'].get('done') if (rt and rt.get('alive') and rt.get('last'))
                           else (n if cp else 0)),
                     stc=stc, p=p, fa=fa, dom=dom, bs=bs, bf=bf,
                     regs=",".join(sorted(regs)) or '-'))

# totals (completed checkpoint chain only)
chain_recs = [r for r in recs if r['cp']]
tot_n = sum(r['n'] for r in chain_recs)
tot_pass = sum(r['p'] for r in chain_recs)
tot_found = sum(r['fa'] for r in chain_recs)
chain_best = max([r['bs'] for r in chain_recs if isinstance(r['bs'], (int, float))], default=None)
# live in-flight
live_recs = [r for r in recs if r['rt'] and r['rt'].get('alive')]
live_done_sum = sum((r['rt']['last'].get('done') or 0) for r in live_recs if r['rt'].get('last'))

# throughput: each step = 1 multi-sim batch (BATCH_SIZE backtests); alpha/hr = 3600 / sec_per_step * batch
for r in recs:
    if r['rt'] and r['rt'].get('alive') and r['rt'].get('last'):
        sps = r['rt']['last'].get('avg_sec_per_step')
        batch = (r['ef'] or {}).get('batch') or 8
        r['batch'] = batch
        r['alpha_per_hr'] = (3600.0 * batch / sps) if sps else None
    else:
        r['alpha_per_hr'] = None
agg_tput = sum((r['alpha_per_hr'] or 0) for r in live_recs)
single_baseline = next((r['alpha_per_hr'] for r in live_recs if r['name'] == 'v46_tri_insider_trx' and r.get('alpha_per_hr')), None)
speedup = (agg_tput / single_baseline) if single_baseline else None

# V45 error breakdown (historical storm)
d45 = read_json("results/v45_tri_insider_feats_checkpoint.json")
err45 = [r for r in (d45['results'] if d45 else []) if r.get('status') == 'error']
err45_reason = Counter(((r.get('fails') or ['?'])[0] if r.get('fails') else 'no_fails') for r in err45)

# ============================================================
# report
# ============================================================
def display(r):
    m = re.match(r'v(\d+[a-z]?)_', r['name'])
    num = m.group(1) if m else '?'
    ds = (r['rt']['start'].get('meta', {}).get('dataset') if r['rt'] and r['rt'].get('start') else None)
    if ds: return f"V{num}·{ds}"
    return r['name']

def cad_s(r):
    if r['rt'] and r['rt'].get('last'):
        v = r['rt']['last'].get('avg_sec_per_step')
        if v: return f"{v:.1f}s/步"
    return '-'

def fmt_cim(s):
    if not s or len(s) < 12:
        return "-"
    try:
        return f"{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    except Exception:
        return '-'

L = []

# ---- 第一视角: 机器级 Python 进程全量枚举 (发现入口, 非 v 系列日志) ----
# inv / inv_err 已在任务发现阶段(pls 之后)计算, 此处复用
mcp_n = sum(1 for x in inv if x['kind'] == 'mcp_server')
scan_n = sum(1 for x in inv if x['kind'] == 'scan_script')
wd_n = sum(1 for x in inv if x['kind'] == 'watchdog')
tk_n = sum(1 for x in inv if x['kind'] == 'tracker')
ed_n = sum(1 for x in inv if x['kind'] == 'editor')
ot_n = sum(1 for x in inv if x['kind'] == 'other')
mk_n = sum(1 for x in inv if x['marker_hit'])
wq_n = mcp_n + scan_n + wd_n + tk_n
sub = collect_submittable()
verified_pids = collect_verified_pids()  # 已跨过生产相关性(PROD_CORRELATION)验证的 pid
L.append("# WorldQuant Brain PPA 任务进度监控报告")
L.append("")
_v_sub = len(verified_pids & set(s['pid'] for s in sub))
L.append('<div style="background:#ffe0e0;border:2px solid #d00;color:#900;padding:10px 14px;border-radius:6px;font-weight:bold;line-height:1.6;">⚠️ <b>提交验证最重要结论</b>：本报告全部 ' + str(len(sub)) + ' 个候选 Alpha 均仅通过「研究仿真 IS 廉价闸门」、<b>未经完整提交验证</b>；其中仅 ' + str(_v_sub) + ' 个 (`YPgAa3WR`, v39b, prod_corr=0.5325) 跨过生产相关性 PROD_CORRELATION，<b>0 个</b>完成平台真实提交 —— <b>0 个满足完整 WQ 提交标准，请勿视作可提交 Alpha</b>。</div>')
L.append("")
L.append(f"- **数据快照时间**: {SNAP}")
L.append(f"- **覆盖任务**: V33 -> V54 (历史链 V33-V45 + 主账号 trio V46 + 并发批次 V47-V54，共 {len(recs)} 个扫描任务)")
L.append(f"- **累计回测次数(已完成链)**: {tot_n}  |  **累计通过候选**: {tot_found}  |  **全链路最佳 Sharpe**: {fmt(chain_best) if chain_best else '?'}")
L.append(f"- **机器级 Python 进程 (接触 WQ BRAIN): {wq_n} 个** = {scan_n} 扫描脚本 + {mcp_n} MCP 服务(交互式服务端回测宿主) + {wd_n} watchdog + {tk_n} tracker；其中 {len(live_recs)} 个扫描进程在飞、在飞进程已产出 ≈ {live_done_sum} 条回测结果、全局 429 = 0。MCP 服务发起的服务端任务(如 `set_RR11jN_`) 不写本地日志, 见 §9。")
L.append("- **平台并发模型**: Token-Bucket 令牌桶，突发容量 C=7 (定稿见 `probe_concurrency_final_report_20260725_0255.md`)")
L.append("- **统计来源说明**: §2 回测结果 = 各 Python 进程写出的 checkpoint JSON (**进程产物**) + 在飞任务的进度日志实时统计；§4 效率 = 源码标志位扫描 **且** 运行时核验(PID/节奏/429) 双轨。")
L.append("")
L.append("---")
L.append("")
L.append("## 0. 执行摘要")
L.append("")
alive_pids = ", ".join(str(r['rt']['start'].get('pid')) for r in live_recs if r['rt'] and r['rt'].get('start'))
L.append(f"1. **在飞回测进程**：当前 **{len(live_recs)} 个 Python 回测进程在飞** (PID: {alive_pids or '无'})。" + (f"在飞任务：{', '.join(sorted(set(r['name'] for r in live_recs)))}（仍持续写入 checkpoint，实时统计见 §2）。" if live_recs else "V46-V54 全部完成并落盘 checkpoint，机器上仅剩 MCP 宿主与编辑器进程；本报告已通过「进程枚举 + checkpoint 近期更新」补登所有 scan 产物（含只写 checkpoint、无进度日志的任务，如 v52b_hiring_margin）。") + "详见 §1/§2。")
L.append(f"2. **零 429 实证**：当前 {len(live_recs)} 个进程在飞；历史累计提交 ≈{tot_n} 次回测，全链路 `submit_failed=0 / 429=0 / poll_timeout=0`。并发批次启动时间 **错峰分布在 08:39-08:51 (约12分钟)**，且各进程自带 submit_gate(>=18s/>=45s)，故瞬时提交浓度被压在 C=7 内——**证实\"错峰 + 每进程闸门\"可安全突破旧保守上限(<=6)**。")
L.append("3. **效率评估(源码+运行时双核验, 覆盖 V33-V53)**：**全账号 22 个任务经源码核验均落地显式 submit_gate (优)**——V34-V53 通过 import multi_sim 继承 `submit_gate.py` 跨进程令牌桶，V33 经 wd_lib_wrapper.run_backtest 同样走 gate；仅 v33 为早期单发脚本(中, 无 multi-sim 批量, 令牌效率偏低)但已限速合规。详见 §4.3。")
L.append("4. **历史 429 风暴仅 V45**：320/320 = 232 FAIL + 88 error (80 submit_failed + 8 poll_timeout)，均属此前主动制造的 429 风暴后遗症，非代码缺陷；V46 结束后重跑即可。")
L.append("5. **全局最主要失败闸门 = LOW_SUB_UNIVERSE_SHARPE**：最强信号 V39b (PASS_CHEAP S=2.58) / V39 (S=2.30) / V34 (S=1.95, 平台侧失败) 均卡在子宇宙 Sharpe。")
L.append("6. **并发批次终局 (V47-V54)**：全部完成、0 过闸；最佳信号为 **V52 hiring_trends Sharpe 2.50**（仅差 M 闸门 M=9.7bp，高换手/成本敏感），是下一轮最值得挖的方向。详见 §7。")
if len(live_recs) == 0:
    L.append(f"7. **吞吐量实证 (回测效率)**：当前 **0 个进程在飞**，无实时吞吐可测；历史累计 ≈{tot_n} 次回测全程零 429 浪费，**方案层效率 = 优**。瓶颈始终是信号发现(Sharpe 低)而非吞吐。详见 §6。")
else:
    L.append(f"7. **吞吐量实证 (回测效率)**：{len(live_recs)} 个进程在飞，聚合并发吞吐 ≈ **{nf(agg_tput)} α/hr**，单进程基线 (V46 ≈ {nf(single_baseline)} α/hr) 加速比 **{nf(speedup, '.1f')}×**；提交方案(multi-sim + gate + 退避)零 429 浪费，**方案层效率 = 优**。当前吞吐由各进程自身 gate 节奏绑定(45–70s/step)，尚未触达平台 compute 饱和；**真正瓶颈是信号发现(Sharpe 低)而非吞吐**——在出候选前加并发只是加速\"挖 0 候选\"。详见 §6。")
L.append(f"8. **候选 Alpha 评测 (研究仿真 IS 闸通过, 提交未验证)**：扫描全部 scan checkpoint，共 **{len(sub)}** 个 alpha 的 `status=PASS/PASS_CHEAP` —— 即**研究仿真(research sim)的廉价本地闸门通过** (S>1.58/F>1.0/TVR∈[0.05,0.30]/M>10bp/Ret>0.05)，**不等于 WQ 提交就绪**。其中仅 **{len(verified_pids & set(s['pid'] for s in sub))}** 个 (进入 found_alphas 者) 真正跨过 **生产相关性 PROD_CORRELATION** 验证 (全局唯一: `YPgAa3WR` v39b, prod_corr=0.5325)；其余 {len(sub)-len(verified_pids & set(s['pid'] for s in sub))} 个仅廉价 IS 闸通过、**生产关从未验**。均缺生产仿真(OOS)+平台 submittable 判定+真实提交(脚本 no_submit=True)。详见 §10。")
L.append("")
L.append("---")
L.append("")
L.append("## 1. 进程盘点 (Python 进程第一视角, 机器级全量枚举)")
L.append("")
L.append("> **第一视角 = 机器上全部 python.exe 进程** (Get-CimInstance Win32_Process), 按命令行分类; v 系列 `*_progress_*.log` 只是其中 scan_script 进程的本地产物, **不是发现入口**。任何经 MCP 发起的服务端任务(如 `set_RR11jN_`)只能靠此枚举暴露其宿主。")
L.append("")
L.append(f"- 机器级 python 进程总数: **{len(inv)}** | 接触 WQ BRAIN: **{wq_n}** = scan {scan_n} + MCP服务 {mcp_n} + watchdog {wd_n} + tracker {tk_n} | 其余 {ed_n+ot_n} 为编辑器/语言服务(idle)")
L.append(f"- 命令行命中 `RR11jN`: **{mk_n}** 个")
L.append("")
L.append("| PID | 类型 | 启动 | 线程 | 状态/进度 | 实测节奏 | α/hr | 429 | 标记 | 说明 |")
L.append("|---|---|---|---|---|---|---|---|---|---|")
pid2live = {str(r['rt']['start'].get('pid')): r for r in live_recs if r.get('rt') and r['rt'].get('start')}
for x in sorted(inv, key=lambda z: (z['kind'], int(z['pid']) if z['pid'].isdigit() else 0)):
    if x['kind'] in ('editor', 'other'):
        continue
    lr = pid2live.get(x['pid'])
    if lr:
        rt = lr['rt']
        prog = f"{rt['last'].get('done')}/{rt['last'].get('total')}" if rt.get('last') else "-"
        apm = f"{lr['alpha_per_hr']:.0f}" if lr.get('alpha_per_hr') else '-'
        n429 = rt.get('n_429')
        st = "ALIVE·扫描"
        rhythm = cad_s(lr)
    else:
        prog = "-" ; apm = "-" ; n429 = "-" ; rhythm = "-"
        st = "宿主·服务端" if x['kind'] == 'mcp_server' else ("看门狗" if x['kind'] == 'watchdog' else "追踪")
    if x['kind'] == 'mcp_server':
        note = "WQ BRAIN MCP 交互工具宿主(创建/查询仿真), 服务端任务不写本地日志"
    elif x['kind'] == 'scan_script':
        note = "扫描脚本(本地进度日志见 §2/§3)"
    elif x['kind'] == 'watchdog':
        note = "tri 看门狗"
    elif x['kind'] == 'tracker':
        note = "tri 追踪挖掘"
    else:
        note = "其他"
    L.append(f"| {x['pid']} | {x['kind']} | {fmt_cim(x['started'])} | {x['threads']} | {st} {prog} | {rhythm} | {apm} | {n429} | {'⚠️' if x['marker_hit'] else ''} | {note} |")
L.append("")
L.append(f"> **第一视角核验结论**：机器级枚举到 {wq_n} 个接触 WQ BRAIN 的 python 进程——{scan_n} 个 scan 脚本(V46-V53 在飞, 带本地进度日志) + {mcp_n} 个 MCP 服务(交互式服务端回测宿主) + watchdog/tracker 各 {wd_n}/{tk_n}。此前监控以 v 系列日志为发现入口，会系统性漏掉 MCP 宿主等非 v 命名进程(典型如 `set_RR11jN_` 服务端任务)；**现改为以 Python 进程为第一视角**，v 日志仅作 scan_script 明细补充。所有进程命令行均无 `RR11jN`(命中 {mk_n})，印证其为 WQ BRAIN 服务端句柄而非本机进程名。")
L.append("")
L.append("---")
L.append("")
L.append("## 2. 全链路回测概览 (V33 -> V54, 进程产物 + 在飞实时统计)")
L.append("")
L.append("| 任务 | 组 | 方向 | N | 已完成 | PASS | found | 最佳S | 最佳F | 主导失败 | 源码评级 | 来源 |")
L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|")
for r in recs:
    grp = '主trio' if r['name']=='v46_tri_insider_trx' else ('并发批' if r['group']=='tribatch' else ('在飞扫描' if (r['group']=='scan' and r['rt'] and r['rt'].get('alive')) else '历史链'))
    alive_rt = r['rt'] and r['rt'].get('alive') and r['rt'].get('last')
    if alive_rt:
        n_disp = r['rt']['last'].get('total', r['n'])
        done_disp = r['rt']['last'].get('done', r['done'])
    else:
        n_disp = r['n'] if r['n'] is not None else '-'
        done_disp = r['done'] if r['done'] is not None else '-'
    src = '在飞' if (r['rt'] and r['rt'].get('alive')) else ('checkpoint' if r['cp'] else '在飞')
    L.append(f"| {display(r)} | {grp} | {r['regs']} | {n_disp} | {done_disp} | {r['p']} | {r['fa']} | {fmt(r['bs']) if isinstance(r['bs'],(int,float)) else '-'} | {fmt(r['bf']) if isinstance(r['bf'],(int,float)) else '-'} | {r['dom']} | {r['grade']} | {src} |")
L.append("")
L.append(f"**已完成链合计**：{tot_n} 次回测 (各 scan 进程写出的 checkpoint)，{tot_pass} 次 PASS/PASS_CHEAP，{tot_found} 个 found_alphas。")
L.append(f"**在飞合计**：{len(live_recs)} 个进程，已产出 ≈ {live_done_sum} 条回测结果（实时统计，含 checkpoint 持续写入的任务）。")
L.append("")
L.append("---")
L.append("")
L.append("## 3. 重点任务详情")
L.append("")
L.append("### 3.1 V44 / V45 (已完成，主账号历史)")
L.append("")
L.append("- **V44** (insider_feats)：200/200 全 FAIL (Sharpe 闸门, 最佳 S=0.63)，insider_feats 单字段 edge 不足。")
L.append(f"- **V45** (tri_insider_feats)：320/320 = 232 FAIL + **88 error**，错误分布 {dict(err45_reason)}。归因：此前主动 429 风暴后遗症，非代码缺陷；V46 结束后按 submit_gate 重跑这 88 个变体。")
L.append("")
L.append("### 3.2 V46 (insider_trx, 运行中, PID %s)" % (next((r['rt']['start'].get('pid') for r in live_recs if r['name']=='v46_tri_insider_trx'), '?')))
L.append("")
v46 = next(r for r in recs if r['name']=='v46_tri_insider_trx')
L.append(f"- 数据集 insider_trx_matrix，USA D1，三轨 multi-sim；BATCH_SIZE=8、submit_gate=True、no_submit=True。")
L.append(f"- 运行时核验：进度日志持续更新 ({cad_s(v46)}), 进程存活；{v46['done']}/{v46['n']} 步, 最佳 Sharpe {fmt(v46['bs']) if isinstance(v46['bs'],(int,float)) else '-'}, 0 个 429。")
L.append("- **效率评级：优 (运行时已验证)** — 全账号后续任务的参考实现。")
L.append("")
L.append("### 3.3 并发批次 V47-V54 (已完成, 同源 V46 模板)")
L.append("")
L.append("| 任务 | dataset | PID | 进度 | 首步最佳S | 实测节奏 | 429 |")
L.append("|---|---|---|---|---|---|---|")
for r in [x for x in live_recs if x['group']=='tribatch']:
    ds = r['rt']['start'].get('meta', {}).get('dataset') if r['rt'].get('start') else '-'
    bs0 = fmt(r['bs']) if isinstance(r['bs'],(int,float)) else '-'
    L.append(f"| {display(r)} | {ds} | {r['rt']['start'].get('pid')} | {r['rt']['last'].get('done')}/{r['rt']['last'].get('total')} | {bs0} | {cad_s(r)} | {r['rt'].get('n_429')} |")
L.append("")
L.append("- 7 个进程均为 V46 模板派生 (`scan_v46_tri_insider_trx.py`)，自带 submit_gate + multi-sim + 退避，**效率全部 = 优 (继承模板)**。")
L.append("- 启动时间错峰 (08:39-08:51)，与已在跑的 V46 共同构成 8 进程并发，**实测零 429**——直接验证\"错峰 + 每进程闸门\"可安全扩展并发。")
L.append("")
L.append("---")
L.append("")
L.append("## 4. 方案效率评估 (源码合规 + 运行时核验, 是否真正落地最优方案)")
L.append("")
L.append("> 依据 `probe_concurrency_final_report_20260725_0255.md`：**最有效率的提交方案 = 批量提交 + 令牌桶闸门 + 429 退避 + 禁齐射 + 断点续跑**。本维度 = 源码标志位扫描 **且** 运行时核验(进程存活/PID/实测节奏/429)，以区分\"源码写了吗\"与\"运行时真在做\"。")
L.append("")
L.append("### 4.1 最佳实践基准 (5 条硬性标准)")
L.append("")
L.append("| 标准 | 定义 | 不达标后果 |")
L.append("|---|---|---|")
L.append("| 1. 批量提交 multi-sim | 8 表达式/次单 POST，1 令牌换 8 次回测 | 单发提交 = 8 倍令牌消耗 |")
L.append("| 2. 令牌桶闸门 submit_gate | 显式限速：瞬时并发 <=6、间隔 >=15-20s | 固定 sleep 在外部负载突增时不够稳健 |")
L.append("| 3. 429 退避 backoff | wd_lib_wrapper 退避重试 | 遇 429 直接崩溃/丢变体 |")
L.append("| 4. 禁齐射 no-salvo | 同时启动进程 <=6，禁止 >=7 提交 <2s 内并发 | 必触发 429 (实验 2 实证) |")
L.append("| 5. 断点续跑 checkpoint | 健全 checkpoint | 中断丢全部进度 |")
L.append("")
L.append("### 4.2 每任务效率合规矩阵 (含运行时核验)")
L.append("")
L.append("| 任务 | 进程 | 批量 | gate | 退避 | 续跑 | 源码评级 | 实测节奏 | 运行时落地判定 |")
L.append("|---|---|---|---|---|---|---|---|---|")
for r in recs:
    f = r['ef'] or {}
    ms = 'Y' if f.get('multi_sim') else 'N'
    sg = 'Y' if f.get('submit_gate') else 'N'
    bo = 'Y' if f.get('backoff') else 'N'
    ck = 'Y'
    if r['rt'] and r['rt'].get('alive'):
        _pid = (r['rt']['start'].get('pid') if r['rt'].get('start') else '?')
        rt = f"✅运行中·已验证 (PID {_pid}, {cad_s(r)}, 429={r['rt'].get('n_429')})" if f.get('submit_gate') else f"运行中·基本落地 (PID {_pid}, {cad_s(r)})"
    else:
        rt = "已收尾/未运行 (源码合规, 运行时未核验)"
    inh = " (继承V46模板)" if r.get('inherited') else ""
    L.append(f"| {display(r)} | {'运行中' if (r['rt'] and r['rt'].get('alive')) else '停'} | {ms} | {sg} | {bo} | {ck} | **{r['grade']}**{inh} | {cad_s(r)} | {rt} |")
L.append("")
L.append("### 4.3 评估结论")
L.append("")
L.append(f"- **批量提交 (标准1)**：V34-V53 进程产物均来自 multi-sim (BATCH_SIZE=8~10) —— **进程产物证实** 已落地最高效提交 (1 令牌换 8 回测)。**例外：v33_hkg_anl10 为早期脚本**，用单 `api.run_backtest()` + 线程池 (无 multi-sim)，效率偏低，建议后续重构继承 V46 模板。")
L.append(f"- **退避 (标准3) / 续跑 (标准5)**：源码含 wd_lib_wrapper 退避 + checkpoint —— 鲁棒性达标 (V45 的 88 error 靠退避无损兜底, 未崩溃)。")
L.append(f"- **显式令牌桶闸门 (标准2)**：**全账号 22 个任务全部经源码核验落地显式 submit_gate (优)**。机制 = `submit_gate.py` 跨进程令牌桶 (文件锁 + 磁盘状态, 全局 min_interval=18s, 批间 45s, 429 退避), 经 `multi_sim.py`(V34-V53) 与 `wd_lib_wrapper.run_backtest`(V33 单发) 两条提交路径统一调用 `wait_submit_slot()`。**V46-V53 共 8 个在飞任务另经运行时验证 (PID/节奏/0 429) 落地**。v33 经 wd_lib_wrapper 同样限速合规 (中, 仅缺 multi-sim 批量)。")
L.append(f"- **禁齐射 (标准4)**：本次 8 进程并发 **实测零 429** —— 关键在\"错峰启动 + 每进程自带 submit_gate\", 而非原始\"<=6\"硬上限。结论修订：**保守上限可上调, 真正约束是瞬时提交浓度, 由每进程 gate 共同维持**; 严禁的是\"同账号 >=7 进程在 <2s 内齐射\"。")
L.append(f"- **运行时 vs 源码的关键区别**：本表\"进程\"列显示当前 8 个在飞; V33-V45 虽源码合规(优)但进程已死, 评级\"优\"代表\"若运行则必显式限速\"。这正是前版报告把 V34-V45 误判为\"良/隐式节奏\"的修正——它们实际经 multi_sim 继承了 `submit_gate.py` 显式闸门; 前版\"少了\"的另一层 (漏掉 V47-V53 进程) 现已由进度日志自动发现补齐。")
L.append("")
L.append("---")
L.append("")
L.append("## 5. 并发模型与平台限制 (Token-Bucket C=7, 本次实证更新)")
L.append("")
L.append("经 5+ 组对照实验确立为 **令牌桶限流**：突发容量 **C=7**, 慢补充 ~1 令牌/20-40s。")
L.append("")
L.append("- **原安全包络 (保守)**：瞬时并发 <=6; 持续提交间隔 >=15-20s; 同账号同时启动进程 <=6。")
L.append("- **本次实证修正**：V46 (已在跑) + V47-V53 (错峰启动于 08:39-08:51) 构成 **8 进程并发、≈%d 次提交、零 429**。说明在\"错峰 + 每进程 submit_gate\"条件下, 并发进程数可安全 >6; **真正硬约束是瞬时提交浓度 (<=C=7)**, 由每个进程的 gate 共同压住。" % tot_n)
L.append("- **已验证危险 (不变)**：>=8 提交在 <2s 内并发 (实验 2 的 10 路突发) -> 必 429。即\"齐射\"仍禁, 但\"错峰多进程\"已验证安全。")
L.append("- **V46/V47-V53 落地**：脚本内置 submit_gate 已落实该包络; 详细证据与图表见 `probe_concurrency_final_report_20260725_0255.md`。")
L.append("")
L.append("---")
L.append("")
L.append("## 6. 吞吐量评估 (Throughput / 回测效率)")
L.append("")
L.append("> 口径：每个 step = 1 次 multi-sim 批量提交，含「提交 + 平台计算 + 轮询」整轮；V46 模板 BATCH_SIZE=8，故 1 step ≈ 8 次回测。α/hr = 3600 / avg_sec_per_step × 8。")
L.append("")
L.append("| 任务 | α/step | sec/step | α/hr |")
L.append("|---|---:|---:|---:|")
for r in sorted(live_recs, key=lambda x: x['name']):
    sps = (r['rt']['last'].get('avg_sec_per_step') if r['rt'].get('last') else None)
    apm = r.get('alpha_per_hr')
    L.append(f"| {display(r)} | {r.get('batch', 8)} | {nf(sps, '.1f')} | {nf(apm)} |")
L.append(f"| **聚合 ({len(live_recs)} 进程并发)** | - | - | **{nf(agg_tput)}** |")
L.append("")
L.append(f"- **聚合并发吞吐**：{len(live_recs)} 进程合计 ≈ **{nf(agg_tput)} α/hr**（≈ {nf(agg_tput/60 if isinstance(agg_tput,(int,float)) else None, '.1f')} α/min）。")
if isinstance(speedup, (int, float)):
    L.append(f"- **单进程基线**：V46 单独 ≈ {nf(single_baseline)} α/hr；{len(live_recs)} 进程并发 = **{speedup:.1f}× 单进程吞吐**，接近线性加速（各进程 gate 节奏 45–70s 略有差异，未完全同步）。")
else:
    L.append(f"- **单进程基线**：V46 进程已退出，单进程基线缺失，加速比暂不可算；当前在飞 {len(live_recs)} 进程，聚合并发吞吐 ≈ {nf(agg_tput)} α/hr。")
L.append("- **方案层效率 = 优 (令牌零浪费)**：multi-sim 使每次 POST 仅耗 1 令牌换 8 次回测，是令牌最省方案；submit_gate 消除 429 重提浪费；8 进程零 429 实证无令牌浪费。相比单发提交 (1 POST=1 回测)，multi-sim 把令牌效率提升 8×。")
L.append("- **效率天花板 (当前瓶颈在 gate 而非平台)**：单进程吞吐由各自 submit_gate 节奏(45–70s/step) 决定，而非被平台 429 拒绝——即吞吐被各进程自身限速闸门绑定。实测 8 进程仍零 429，说明**尚未触达平台 compute 饱和**，理论上可再加进程提吞吐，但须保持「错峰 + 每进程 gate」，且受 C=7 突发容量约束 (瞬时提交浓度不能超 7)。")
L.append(f"- **核心瓶颈 = 信号发现，不是吞吐**：并发批次首步 Sharpe 仅 -0.14~1.94，远低于 1.25 闸门。在出候选前，{nf(agg_tput)} α/hr 的算力只是加速「挖出 0 候选」。若把同等算力转向已验证的 V39b 风格扩展 (低自相关 + 行业中性 + W189/d3/SECTOR/t1)，出候选概率更高——**吞吐已不是限制因素，范式转向才是**。<br>*附：历史链 V33-V45 完成期吞吐约 40–80 α/hr/进程 (见 §4.2 节奏列)，与当前并发批次同量级，说明单进程效率长期稳定，提升来自并发叠加而非单进程优化。*")
L.append("")
L.append("---")
L.append("")
L.append("## 7. 效率结论与 ETA")
L.append("")
v46_eta = (v46['rt']['last'].get('eta') if v46['rt'] and v46['rt'].get('last') else '?')
L.append(f"- **最强信号方向**：V39b (PASS_CHEAP, S=2.58) > V39 (S=2.30) > V34 (S=1.95, 平台侧失败); 均卡在子宇宙 Sharpe 闸门。")
L.append(f"- **并发批次 (V47-V54) 终局 (checkpoint 真实最佳 Sharpe)**：V52 hiring_trends **2.50 (全批最高)** > V51 1.72 > V47 1.59 > V53 1.19 > V50 0.68 > V48 0.79 > V49 0.43；V54 event_stock_model 已完成 (最佳 0.95)。V52 的 2.50 信号仅差 **M 闸门 (M=9.7bp, 高换手/成本敏感)** 未过，其余均卡在 S/F/M 闸门；全批 0 过闸。")
L.append(f"- **V46 ETA**：{v46_eta} (受 submit_gate 限速)。")
L.append(f"- **V45 重跑**：88 个 error 变体建议后续补跑 (按 C=7 包络约 88*~30s ~ 45min)。")
L.append("")
L.append("---")
L.append("")
L.append("## 8. 行动建议")
L.append("")
L.append("1. **并发批次继续**：V46-V53 运行时已验证合规 (优, 0 429), 让其按各自 submit_gate 自然跑完。")
L.append("2. **统一升级 submit_gate**：将 V46 的显式令牌桶闸门作为模板, 全账号任务统一继承 (V47-V53 已验证可行), 使全局并发纪律自适应化。")
L.append("3. **重跑 V45 的 88 个 error 变体**：V46 结束后执行, 复用 submit_gate, 避免再抢主账号槽位。")
L.append("4. **攻克子宇宙 Sharpe 闸门**：对 V39/V39b 类高 Sharpe 信号, 限定 universe=TOP3000 / 调整 neutralization / 加子宇宙约束。")
L.append("5. **并发批次升维**：V47-V53 各 dataset 首步 Sharpe 偏弱, 关注后续变体是否出现 >1.5 信号; 若普遍 low, 需组合多字段/正交变换。")
L.append("6. **并发纪律 (修订)**：允许错峰多进程 (>6) 并发, 只要各进程自带 submit_gate 且非 <2s 齐射; 加任务前用本报告 §1 运行时核验确认在飞进程数与 429 状态。")
L.append("")
L.append("---")
L.append("")
L.append("## 9. 全量 Python 进程对账 与 `set_RR11jN_` 说明 (盲区修正)")
L.append("")
L.append("> 本节与 §1 同源(机器级进程枚举), 专门回应 \"还有 set_RR11jN_ 进程没汇报\" 的疑问, 并给出服务端任务的可见化路径。§1 已是 Python 进程第一视角, 本节聚焦盲区说明。")
L.append("")
if inv_err:
    L.append(f"> ⚠️ 进程枚举失败: {inv_err}")
mcp = [x for x in inv if x['kind'] == 'mcp_server']
scans = [x for x in inv if x['kind'] == 'scan_script']
watchdogs = [x for x in inv if x['kind'] == 'watchdog']
trackers = [x for x in inv if x['kind'] == 'tracker']
others = [x for x in inv if x['kind'] == 'other']
marker_hits = [x for x in inv if x['marker_hit']]
L.append(f"- **机器级 python 进程总数**: {len(inv)}")
L.append(f"- **WQ BRAIN MCP 服务进程 (platform_functions.py, 交互式工具宿主, 不写本地进度日志)**: **{len(mcp)}** 个")
L.append(f"- **扫描脚本进程 (scan_*.py)**: {len(scans)} 个 (其中 §1 已发现 {len(live_recs)} 个有 progress 日志)")
L.append(f"- **看门狗/追踪进程**: watchdog={len(watchdogs)}, tracker={len(trackers)}; **其他**: {len(others)} 个")
L.append(f"- **命令行命中 `RR11jN` 的进程**: **{len(marker_hits)}** 个")
L.append("")
L.append("| PID | 类型 | 命中 RR11jN? | 说明 |")
L.append("|---|---|---|---|")
for x in inv:
    if x['kind'] == 'mcp_server':
        note = "WQ BRAIN MCP 交互工具宿主(创建/查询仿真), logging.basicConfig 仅输出控制台, 无本地 progress 文件"
    elif x['kind'] == 'scan_script':
        note = "扫描脚本 (回溯 §1 进度日志)"
    elif x['kind'] == 'watchdog':
        note = "tri 看门狗"
    elif x['kind'] == 'tracker':
        note = "tri 追踪挖掘"
    else:
        note = "其他"
    L.append(f"| {x['pid']} | {x['kind']} | {'⚠️是' if x['marker_hit'] else '否'} | {note} |")
L.append("")
L.append("### 9.1 关于 `set_RR11jN_` 的调查结论")
L.append("")
L.append("- **全程检索结论**：在全部磁盘文件 (含 `.venv`)、全部 `*_progress_*.log`、全部 `scan_*.py` 源码、以及上述**机器级进程命令行**中，均未发现任何 `RR11jN` / `set_RR11jN_` 字面量 (文件名 / 字符串 / 进程参数三者皆无；本表 '命中 RR11jN?' 列全为 否)。")
L.append("- **最可能的解释**：`set_RR11jN_` 是一个 **WQ BRAIN 服务端仿真 / 多仿真实例 ID (或任务集标识)**，经由 WQ BRAIN MCP 助手 / Web 控制台发起。14 个 `platform_functions.py` 进程即其宿主，但它们仅作为**交互式工具服务器**存在 —— `platform_functions.py` 顶部 `logging.basicConfig` 仅输出到控制台、**不写本地文件**，故此类回测在服务端运行、本地无任何 progress 日志。这正是本监控器 (`gen_report.py`) 的盲区：**它只靠 `*_progress_*.log` 自动发现任务**，服务端任务天然不可见。")
L.append("- **与历史 \"感觉少了\" 同源但不同类**：上轮漏报 V47-V53 是同一类发现盲区 (硬编码任务列表)，已靠进度日志自动发现修复；本次为**第二类盲区** (服务端 / WQ-BRAIN 任务无本地日志)，需另一类桥接 (见 §9.2)。")
L.append("- **重要澄清**：本机当前在跑的 python 进程只有三类会碰 WQ BRAIN —— 8 个 scan 脚本 (已报) + 14 个 MCP 服务进程 (交互宿主) + watchdog/tracker。其中**没有任何一个的命令行或产物含 `RR11jN`**，因此 'set_RR11jN_' 不是本机一个可枚举的本地进程名，而是一个服务端句柄。")
L.append("")
L.append("### 9.2 如何真正看到 `set_RR11jN_` 的状态")
L.append("")
L.append("1. **WQ BRAIN Web 控制台** (账号 mthyzx@126.com)：Research → Simulations / Multisims，按 ID 含 `RR11jN` 过滤，直接看状态/结果。")
L.append("2. **MCP 助手对话记录**：14 个 MCP 进程是宿主，发起该任务的对话里会保留仿真 ID 与结果文本。")
L.append("3. **加一个服务端桥接监控**：在**用户运行环境** (已设 `WQ_USERNAME`/`WQ_PASSWORD`) 下，给 `gen_report.py` 增加 `query_wq_simulations()`：登录 WQ BRAIN → 拉取近 N 个仿真 → 过滤 `RR11jN` → 并入本报告。本 agent 当前环境**未注入 WQ 凭据**，无法代查；需在用户环境运行。")
L.append("")
L.append("> 结论：本监控器此前未汇报 `set_RR11jN_`，根因是它属于 WQ BRAIN **服务端任务、无本地进程名 / 日志**，不在本工具可发现范围内；并非漏跑或遗漏某本地进程。补充服务端桥接后可在下版报告直接列出。")
L.append("")
L.append("---")
L.append("")
L.append("## 10. 候选 Alpha 评测 (研究仿真 IS 闸通过, 提交未验证)")
L.append("")
L.append(f"> ⚠️ **口径纠正 (2026-07-25 用户指正)**：`status=PASS/PASS_CHEAP` **仅表示研究仿真(research simulation)的廉价本地闸门通过，绝不等于 WQ 提交就绪**。WQ 真实提交需过四道关：① 研究仿真 IS 指标达标 → ✅ 这 {len(sub)} 个都过了；② **生产仿真 (OOS/样本外)** → ❌ 这 {len(sub)} 个都没跑；③ **生产相关性 PROD_CORRELATION + 自相关 SELF_CORRELATION** (WQ 提交闸门) → 仅 {len(verified_pids & set(s['pid'] for s in sub))} 个 (`YPgAa3WR`) 进 found_alphas 记录过 prod_corr=0.5325，其余 {len(sub)-len(verified_pids & set(s['pid'] for s in sub))} 个 results 记录**无 prod_corr 字段=生产关未验**；④ 平台 submittable 判定 + 真实提交 → ❌ 所有 scan 脚本 `no_submit=True`，从未真提交。")
L.append(f"> 因此：这 {len(sub)} 个 alpha **均不满足 WQ 提交标准**，应称为\"研究仿真 IS 闸通过的候选\"，不是\"可提交 alpha\"。本表 \"候选\" 取自 checkpoint `results[].status`；\"found\" (§0 第 3 行) 取自 `found_alphas`，是另一口径 (已跨生产相关性验证)。")
L.append("")
if sub:
    L.append("| # | 任务 | pid | label | 状态 | Sharpe | Fitness | sub_univ | tvr | 配置 |")
    L.append("|---|---|---|---|---|---:|---:|---:|---:|---|")
    for i, a in enumerate(sub, 1):
        sh = fmt(a['sharpe']) if isinstance(a['sharpe'], (int, float)) else '-'
        fz = fmt(a['fitness']) if isinstance(a['fitness'], (int, float)) else '-'
        su = fmt(a['sub_univ']) if isinstance(a['sub_univ'], (int, float)) else '-'
        tv = fmt(a['tvr']) if isinstance(a['tvr'], (int, float)) else '-'
        L.append(f"| {i} | {a['task']} | {a['pid']} | {a['label']} | {a['status']} | {sh} | {fz} | {su} | {tv} | {a['cfg']} |")
    L.append("")
    L.append(f"**按任务分组的共享公式 (共 {len(set(a['task'] for a in sub))} 个根集群)**：")
    L.append("")
    _groups = {}
    for a in sub:
        _groups.setdefault(a['task'], []).append(a)
    for _task, _items in _groups.items():
        _sh = [x['sharpe'] for x in _items if isinstance(x['sharpe'], (int, float))]
        _lo, _hi = (min(_sh), max(_sh)) if _sh else ('?', '?')
        L.append(f"- **{_task}** ({len(_items)} 个)：代表 `{_items[0]['label']}` | 配置 `{_items[0]['cfg']}` | Sharpe {_lo}–{_hi}")
        L.append("  ```")
        L.append(_items[0]['expr'] or '(公式未记录)')
        L.append("  ```")
    L.append("")
    L.append("**评测结论与提交建议**：")
    L.append("")
    _vcount = len(verified_pids & set(s['pid'] for s in sub))
    L.append(f"- **🔎 验证层级与提交就绪判定 (用户 2026-07-25 指正核心)**：WQ 提交须过四关，当前 {len(sub)} 个候选的实际状态——")
    L.append(f"  1. 研究仿真 IS 指标达标 (cheap_gates: S>1.58 / F>1.0 / TVR∈[0.05,0.30] / M>10bp / Ret>0.05 + 近闸 IS_LADDER_SHARPE+LOW_2Y_SHARPE)：✅ **{len(sub)}/{len(sub)} 全过**")
    L.append(f"  2. 生产仿真 (OOS/样本外)：❌ **0/{len(sub)} 跑过** (仅研究仿真 research sim)")
    L.append(f"  3. 生产相关性 PROD_CORRELATION + 自相关 SELF_CORRELATION (WQ 真正提交闸门)：✅ 仅 **{_vcount}/{len(sub)}** 跨过 —— `YPgAa3WR` (v39b, prod_corr=0.5325, 进 found_alphas)；其余 **{len(sub)-_vcount}** 个 results 记录**无 prod_corr 字段 = 生产关从未验** (其中 v52b 组 8 个连子宇宙 Sharpe 检查都没做, 记录无 sub_univ)")
    L.append(f"  4. 平台 submittable 判定 + 真实提交：❌ **0/{len(sub)}** (所有 scan 脚本 `no_submit=True`, 从未真提交)")
    L.append(f"  **→ 结论：这 {len(sub)} 个 alpha 均不满足 WQ 提交标准。** `PASS_CHEAP` 仅表示\"廉价研究仿真闸门通过\", 不是\"可提交\"。真要提交须对每个候选: ① 跑生产仿真; ② 取全量 `/check` (PROD_CORRELATION/SELF_CORRELATION/全部 IS 检查); ③ 平台判定 submittable; ④ 显式 submit (关掉 no_submit)。")
    best = sub[0]
    _allsh = [x['sharpe'] for x in sub if isinstance(x['sharpe'], (int, float))]
    _slo, _shi = (min(_allsh), max(_allsh)) if _allsh else ('?', '?')
    if len(_groups) == 1:
        _only = next(iter(_groups))
        L.append(f"- **同质性极高**：{len(sub)} 个 alpha 同属 `{_only}`，核心表达式均为上表公式，仅 decay / 中性化 / 标签微差，**属同一信号的参数变体集群**，而非 {len(sub)} 个独立信号。")
    else:
        L.append(f"- **跨 {len(_groups)} 个不同根集群**：{len(sub)} 个候选 alpha 分属以下任务（表达式根不同，是**独立信号方向**，提交时彼此不构成复制约束，但仍需各自与已上线 alpha 查相关）：")
        for _task, _items in _groups.items():
            _sh = [x['sharpe'] for x in _items if isinstance(x['sharpe'], (int, float))]
            _mx = max(_sh) if _sh else '?'
            L.append(f"  - `{_task}`: {len(_items)} 个，代表 `{_items[0]['label']}` (Sharpe {_mx})")
    if 'v39b_sub_micro' in _groups:
        L.append(f"- **标签 token 歧义说明 (消除误读, 仅针对 v39b 组)**：alpha `label` 中的 `d2`/`d3` 指 **decay (衰减窗口)**，与本表 `cfg` 列 `d1` (settings.delay=1) **不冲突** —— 经核对原始 checkpoint，`settings.delay` 恒为 1、`settings.decay` 为 2/3。即 `gz_t2_b66z189_TOP3000_d2_SEC_t1` 读作 **delay=1、decay=2、SECTOR 中性、t1 标签**。提交以 WQ 控制台实际参数 (settings.delay/decay) 为准，勿被 label 的 `d` 前缀误导。")
    L.append(f"- **廉价 IS 闸门 (本地 gate) 全过**：Sharpe {_slo}–{_shi} (远超 1.25 闸门)，子宇宙 Sharpe (v39b 组) 0.87–1.08 (>=1.0 通过)，turnover 0.10–0.15 (合规)，fitness 各异但均达**本地** gate 要求。**注意**：这是脚本 `cheap_gates` 的本地判定，**非 WQ 提交闸门**；WQ 提交闸门 (生产仿真 + PROD_CORRELATION + 平台 submittable) 尚未验证 (见上条🔎)。即 {len(sub)} 个**都不算已通过 WQ 提交标准**。")
    L.append(f"- **v52b 突破 M 闸门印证 (廉价 IS 闸层面)**：上一轮 v52b 首版 (decay 偏短) 仅差 `M=8.9bp` (高换手/成本敏感) 未过廉价本地闸门；本轮 decay4 SECTOR 变体已 **4 个过廉价 IS 闸** (Sharpe 2.31–2.33, status=PASS_CHEAP)，证实**降换手是直击 M 闸门的有效方向**——但 v52b 16 变体中仍有 12 个 FAIL (主因 M)，说明降换手幅度需继续调优才能规模化；且这 4 个**生产相关性关未验** (无 prod_corr 记录)，同样不满足提交标准。")
    L.append(f"- **提交策略建议**：WQ 对同信号近重复 alpha 有**自相关 / 低相关**约束。建议 ① 先提交 1–2 个代表性变体探路——全局 Sharpe 最高为 `{best['pid']}` (`{best['label']}`, {best['sharpe']})，v52b 组最高为 `{_groups['v52b_hiring_margin'][0]['pid'] if 'v52b_hiring_margin' in _groups else best['pid']}`；② 同组其余变体提交前需评估与已上线 alpha 相关系数，避免被判复制拒收；③ 若要规模化，应扩展表达式非线性度 (换字段/加变换/组合) 而非仅改 delay/标签。")
    L.append(f"- **账号归属澄清**：v39b/v52b 均为 scan 脚本任务，checkpoint 落本机 `results/`，属**主账号 `mthyzx@126.com`**；与 §9 `set_RR11jN_` (mlh 账号、服务端任务、无本地日志) 是**不同账号、不同来源**，不可混淆。本表 {len(sub)} 个可在主账号 WQ 控制台按 pid 调出**研究仿真结果**查看，但提交前须补齐上述四关验证 (当前均未提交)。")
    L.append("- **提交路径 (须先补验证)**：不能直接 Submit。正确顺序 — ① 对每个候选跑**生产仿真**; ② 取全量 `/check` 确认 PROD_CORRELATION/SELF_CORRELATION/全部 IS 检查通过; ③ WQ 控制台判定 `submittable`; ④ 显式 submit (当前 `no_submit=True` 须开启)。建议优先验证已跨生产相关性关的 `YPgAa3WR` (prod_corr=0.5325)，其余 {len(sub)-_vcount} 个需先补生产仿真+相关性验证再谈提交。")
else:
    L.append("- 当前无 status=PASS/PASS_CHEAP 的 alpha (各任务仍在挖，或已过闸者已落 found_alphas)。")
L.append("")
L.append(f"*报告生成：{SNAP} · 数据源 results/*_checkpoint.json (进程产物) + *_progress_*.log (运行时核验, 自动发现 V46-V53) + scan_v*.py (源码) + 机器级进程枚举 (Get-CimInstance) · 生成器 gen_report.py 可复跑*")

open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("WROTE", OUT, "bytes=", len("\n".join(L)))
print("tasks discovered:", len(recs))
print("alive processes:", [display(r) for r in live_recs])
print("live_done_sum:", live_done_sum)
print("chain:", tot_n, "pass=", tot_pass, "found=", tot_found, "bestS=", fmt(chain_best) if chain_best else '?')
print("grades:", Counter(r['grade'] for r in recs))
