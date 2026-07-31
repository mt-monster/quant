#!/usr/bin/env python3
"""USA PPA: web_traffic_engage (8 fields, S=2.27 proven)
Constraints: REGULAR, D1, max_trade=OFF, ops<6, 1-2 fields, no trade_when/add/multiply
7 lanes, BATCH=8, multi-create-simulate
"""

import json, os, re, sys, time, threading, itertools, queue, random
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("usa_web")

ROOT = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(ROOT, "results"); os.makedirs(RES, exist_ok=True)
CKPT = os.path.join(RES, "usa_web_checkpoint.json")
LOG = os.path.join(RES, "usa_web.log")
sys.path.insert(0, ROOT)
from wd_lib_wrapper import WqApiSimple
from multi_sim import run_multi_batch, chunked, API_BASE
api = WqApiSimple()

# === Config ===
DATASET = "web_traffic_engage"
FIELDS = sorted([
    "desktop_visit_count_today", "desktop_pageview_count_today",
    "desktop_avg_pages_per_session_today", "desktop_bounce_ratio_today",
    "mobile_avg_pages_per_session_today", "total_visit_count_today",
    "total_avg_pages_per_session_today", "aggregate_bounce_ratio_today",
])
# Fields mock for build_variants
FIELDS_MOCK = [{"id": f} for f in FIELDS]

BATCH_SIZE = 8
N_LANES = int(os.environ.get("WEB_LANES", "4"))  # 4 lanes = sweet spot
UNIVERSE_SEQ = ["TOP3000", "TOP2000", "TOP1000"]
NEUTS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR"]
DECAYS = [3, 4, 5, 6, 8, 10, 12]
MAX_VARIANTS = 600
MAX_OPS = 5
INTERVAL = 10

GATE_S, GATE_F, GATE_M = 1.58, 1.00, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
GATE_RET = 0.05
GATE_2Y = 1.60
GATE_SC, GATE_PC = 0.50, 0.70

def _f(v):
    try: return float(v)
    except: return None

# === Templates ===
TEMPLATES = [
    # 0: spread B-A (proven best for web_traffic)
    ("spread", "rank(ts_zscore(subtract(ts_mean(ts_backfill({F2}, 66), 22), ts_mean(ts_backfill({F1}, 66), 22), filter=true), 189))", True),
    # 1: pure rank
    ("pure", "rank(ts_zscore(ts_backfill({F1}, 66), 189))", False),
    # 2: residual from mean
    ("resid", "rank(ts_zscore(subtract(ts_backfill({F1}, 66), ts_mean(ts_backfill({F2}, 66), 22)), 252))", True),
    # 3: diff of ranks
    ("diff", "rank(ts_zscore(ts_backfill({F1}, 66), 189)) - rank(ts_zscore(ts_backfill({F2}, 66), 189))", True),
    # 4: momentum-reversal
    ("momrev", "rank(ts_zscore(ts_backfill({F1}, 252), 42)) - rank(ts_zscore(ts_backfill({F1}, 22), 42))", False),
    # 5: vol-adjusted
    ("voladj", "rank(ts_zscore(ts_backfill({F1}, 66), 189) / (ts_std(ts_backfill({F1}, 66), 66) + 1e-8))", False),
    # 6: cross-window
    ("cross", "rank(ts_zscore(subtract(ts_mean(ts_backfill({F1}, 66), 10), ts_mean(ts_backfill({F1}, 66), 30)), 189))", False),
]

def count_ops(expr):
    return len(re.findall(r'(rank|ts_zscore|ts_backfill|ts_mean|ts_std|subtract|divide|log|abs|sign|sqrt|power)', expr))

def S(uni, dec, neut):
    return {"instrumentType":"EQUITY","region":"USA","universe":uni,"delay":1,
            "decay":dec,"neutralization":neut,"testPeriod":"P6Y",
            "truncation":0.08,"pasteurization":"ON","unitHandling":"VERIFY",
            "nanHandling":"ON","language":"FASTEXPR","visualization":False}

def build_variants():
    vs = []
    for uni in UNIVERSE_SEQ:
        for dec in DECAYS:
            for neut in NEUTS:
                for ti, (style, tmpl, dual) in enumerate(TEMPLATES):
                    if dual:
                        for f1, f2 in itertools.combinations(FIELDS_MOCK, 2):
                            expr = tmpl.format(F1=f1["id"], F2=f2["id"])
                            if count_ops(expr) > MAX_OPS: continue
                            vs.append({"label": f"w{ti}_{f1['id'][:7]}_{f2['id'][:7]}_{uni[:4]}_d{dec}_{neut[:3]}",
                                       "expr": expr, "settings": S(uni, dec, neut), "style": style})
                    else:
                        for f in FIELDS_MOCK:
                            expr = tmpl.format(F1=f["id"])
                            if count_ops(expr) > MAX_OPS: continue
                            vs.append({"label": f"w{ti}_{f['id'][:7]}_{uni[:4]}_d{dec}_{neut[:3]}",
                                       "expr": expr, "settings": S(uni, dec, neut), "style": style})
    random.shuffle(vs)
    vs = vs[:MAX_VARIANTS] if len(vs) > MAX_VARIANTS else vs
    logger.info("Built %d variants (capped at %d)", len(vs), MAX_VARIANTS)
    return vs

def eval_one(pid, label, expr, settings, style):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, f_ = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0
    ret = _f(is_.get("returns")) or 0
    mbp = m * 10000
    fails = []
    if s <= GATE_S: fails.append(f"S={s:.3f}")
    if f_ <= GATE_F: fails.append(f"F={f_:.3f}")
    if tvr <= GATE_TVR_LO or tvr >= GATE_TVR_HI: fails.append(f"TVR={tvr:.4f}")
    if mbp <= GATE_M: fails.append(f"M={mbp:.1f}bp")
    if ret <= GATE_RET: fails.append(f"Ret={ret:.4f}")
    st = "PASS_CHEAP" if not fails else "FAIL"
    if s > 1.25 and mbp > 8:
        try:
            chk = api.get_alpha_check(pid)
            for c in chk.get("is",{}).get("checks",[]):
                if c.get("result")=="FAIL" and c.get("name") not in ("REGULAR_DESCRIPTION_LENGTH","REGULAR_DESCRIPTION_FORMAT","PROD_CORRELATION","SELF_CORRELATION"):
                    fails.append(f"PF:{c['name']}"); st = "FAIL"
        except: pass
    return {"pid":pid,"label":label,"expr":expr,"settings":settings,"sharpe":s,"fitness":f_,
            "tvr":tvr,"margin_bp":mbp,"returns":ret,"status":st,"fails":fails,"style":style}

def test_risk_neut(expr, bs):
    try:
        s2 = dict(bs); s2["neutralization"] = "MARKET"
        bt = api.run_backtest(expr, settings=s2)
        pid = bt.get("platform_id") if isinstance(bt,dict) else None
        if not pid: return False, {}
        det = api.get_alpha_details(pid)
        is_ = det.get("is",{})
        ns, nf = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
        nm = (_f(is_.get("margin")) or 0)*10000
        return ns>1 and nf>0.7 and nm>10, {"rn_pid":pid,"rn_S":ns,"rn_F":nf,"rn_M":nm}
    except: return False, {}

def test_robust(expr, bs):
    ss = {}
    for tp in ["P4Y","P5Y","P6Y"]:
        try:
            s2=dict(bs); s2["testPeriod"]=tp
            bt=api.run_backtest(expr,settings=s2)
            pid=bt.get("platform_id") if isinstance(bt,dict) else None
            if pid:
                det=api.get_alpha_details(pid)
                ss[tp]=_f(det.get("is",{}).get("sharpe")) or 0
        except: pass
    if not ss: return False, {}
    vals=list(ss.values()); avg=sum(vals)/len(vals); mn=min(vals)
    return mn>1.25 and (max(vals)-mn)/max(vals)<0.5, {"rob_S":avg,"rob_min":mn}

def wait_pc(pid, tmax=600):
    t0=time.time()
    while time.time()-t0<tmax:
        try:
            chk=api.get_alpha_check(pid)
            cs=chk.get("is",{}).get("checks",[])
            pc=next((c for c in cs if c["name"]=="PROD_CORRELATION"),None)
            sc=next((c for c in cs if c["name"]=="SELF_CORRELATION"),None)
            if pc and sc:
                pv,sv=_f(pc.get("value")) or 1,_f(sc.get("value")) or 1
                return pv<GATE_PC and sv<GATE_SC, {"pc":pv,"sc":sv}
            time.sleep(30)
        except: time.sleep(15)
    return False, {"timeout":True}

_lock = threading.RLock()
def save(state):
    with _lock:
        tmp=CKPT+".tmp"
        json.dump({"results":state["results"],"found":state["found"],"total":len(state.get("all_variants",[]))},
                  open(tmp,"w",encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp,CKPT)

def worker(lid, q, state, start_ts):
    while True:
        try: batch = q.get(timeout=5)
        except queue.Empty: return
        if not batch: return
        logger.info("[lane%d] batch: %s", lid, [v["label"][:25] for v in batch[:2]])
        try: results = run_multi_batch(api, batch)
        except Exception as e:
            logger.error("[lane%d] err: %s", lid, e); continue
        for r in (results or []):
            pid = r.get("platform_id")
            if not pid:
                continue
            item = next((v for v in batch if v["label"] == r.get("label")), None)
            if not item:
                continue
            ev=eval_one(pid,item["label"],item["expr"],item["settings"],item["style"])
            with _lock:
                state["results"].append(ev)
                et=int(time.time()-start_ts)
                logger.info("progress %d/%d (%.1f%%) elapsed=%ds found=%d",
                           len(state["results"]),len(state["all_variants"]),
                           len(state["results"])/len(state["all_variants"])*100, et, len(state["found"]))
            if ev["status"]!="PASS_CHEAP": continue
            rn_ok,rn=test_risk_neut(item["expr"],item["settings"])
            if not rn_ok: logger.info("  RN FAIL S=%.2f", rn.get("rn_S",0)); continue
            logger.info("  RN PASS S=%.2f", rn.get("rn_S",0))
            rob_ok,_=test_robust(item["expr"],item["settings"])
            if not rob_ok: logger.info("  ROB FAIL"); continue
            logger.info("  ROB PASS")
            pc_ok,pi=wait_pc(pid)
            if not pc_ok: logger.info("  PC/SC FAIL pc=%.3f sc=%.3f", pi.get("pc",0), pi.get("sc",0)); continue
            logger.info("  ★★★ PC/SC PASS! pc=%.3f sc=%.3f", pi.get("pc",0), pi.get("sc",0))
            # Set properties
            try:
                desc=(f"USA PPA: {item['label']}. web_traffic_engage, REGULAR, D1. "
                      f"S={ev['sharpe']:.2f}, F={ev['fitness']:.2f}, M={ev['margin_bp']:.1f}bp. "
                      f"RN S={rn.get('rn_S',0):.2f}. PC={pi.get('pc',0):.3f}. DO NOT SUBMIT.")
                api.session.patch(f"{API_BASE}alphas/{pid}", json={"name":f"usa_web_{item['label'][:20]}",
                    "regular":{"description":desc},"color":"GREEN"})
                logger.info("  Properties set (NO SUBMIT)")
            except Exception as e: logger.warning("  Set prop err: %s", e)
            with _lock:
                state["found"].append({"pid":pid,"label":item["label"],"sharpe":ev["sharpe"],"rn":rn,"pc":pi})
                save(state)
        save(state)
        # Diversity every INTERVAL batches
        if len(state["results"])>0 and len(state["results"])% (BATCH_SIZE*INTERVAL)<BATCH_SIZE:
            ss=[r.get("sharpe",0) or 0 for r in state["results"]]
            sts=set(r.get("style","?") for r in state["results"])
            logger.info("[DIV] batch=%d done=%d maxS=%.2f styles=%s",
                       len(state["results"])//BATCH_SIZE, len(state["results"]),
                       max(ss) if ss else 0, sts)

def main():
    state = {"results":[], "found":[], "all_variants":build_variants()}
    if os.path.exists(CKPT):
        try:
            ck=json.load(open(CKPT,encoding="utf-8"))
            state["results"]=list(ck.get("results") or [])
            state["found"]=list(ck.get("found") or [])
            done=set(r["label"] for r in state["results"])
            state["all_variants"]=[v for v in state["all_variants"] if v["label"] not in done] + state["results"]
            logger.info("Resume: %d done, %d left, %d found", len(state["results"]),
                       len(state["all_variants"])-len(state["results"]), len(state["found"]))
        except Exception as e: logger.warning("ckpt err: %s", e)
    pending=[v for v in state["all_variants"] if v["label"] not in set(r["label"] for r in state["results"])]
    logger.info("Vars total=%d pending=%d lanes=%d", len(state["all_variants"]), len(pending), N_LANES)
    if not pending: logger.info("ALL DONE"); return
    start_ts=time.time()
    q = queue.Queue()
    for b in chunked(pending, BATCH_SIZE): q.put(b)
    lanes=[threading.Thread(target=worker, args=(i,q,state,start_ts), daemon=True) for i in range(N_LANES)]
    for t in lanes: t.start()
    for t in lanes: t.join()
    save(state)
    logger.info("DONE found=%d", len(state["found"]))
    for f in state["found"]: logger.info("  READY: %s S=%.2f", f["pid"], f.get("sharpe",0))

if __name__=="__main__": main()
