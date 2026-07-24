#!/usr/bin/env python3
"""V32: 多区域 PPA 扫描 — ASI/CHN/KOR 未点亮数据集.
ASI: ai_news_scores (105 MATRIX, sentiment)
CHN: continuation_score (560 MATRIX, chart patterns)
KOR: pattern_scores (504 MATRIX, chart patterns)
不自动提交! 只报告候选, 等待 PC<0.70 后罗列给用户.
"""
import sys, os, json, time, logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))
from progress_logger import ProgressLogger
PROGRESS_LOG_PATH = os.getenv("PROGRESS_LOG_PATH", os.path.join(_HERE, "results", f"v32_kor_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v30")
from wd_lib_wrapper import WqApiSimple

PRE_SHARPE = 1.58; PRE_FITNESS = 1.00; HARD_MARGIN_BP = 5.0
HARD_TVR_MIN = 0.05; HARD_TVR_MAX = 0.20; HARD_RETURNS = 0.05
MAX_PROD_CORR = 0.70

def _to_float(v):
    if v is None: return None
    try: return float(v)
    except: return None

# Region configs: (region, universe, dataset, [(fieldA, fieldB, name), ...])
REGION_CONFIGS = [
    # CHN skipped — continuation_score signal too weak (S<0.62 in 74 variants)
    ("KOR", "TOP600", "pattern_scores", [
        ("asc_triangle_mean_simscore_lookback120", "asc_triangle_min_simscore_lookback120", "tri_mean_vs_min"),
        ("avg_similarity_continuation_rising_wedge_120", "avg_similarity_continuation_falling_wedge", "rise_vs_fall"),
        ("avg_similarity_downward_breakaway_gap_120", "adaptive_similarity_upward_breakaway_gap_120", "down_vs_up"),
        ("asc_triangle_max_simscore_lookback120", "asc_triangle_mean_simscore_lookback60", "tri_max_vs_mean60"),
    ]),
]

settings_base = {
    "instrumentType": "EQUITY", "delay": 1, "decay": 4,
    "neutralization": "SUBINDUSTRY", "truncation": 0.08,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y",
}

VARIANTS = []
for region, universe, ds_id, pairs in REGION_CONFIGS:
    for fA, fB, sig_name in pairs:
        A = f"ts_backfill({fA}, 66)"
        B = f"ts_backfill({fB}, 66)"
        SPREAD = f"subtract(ts_mean({B}, 22), ts_mean({A}, 22), filter=true)"
        fund_plain = f"rank(ts_zscore({SPREAD}, 189))"
        fund_gz = f"rank(group_zscore(ts_zscore({SPREAD}, 189), industry))"
        for ret_z in [21, 42]:
            ret_expr = f"scale(-rank(ts_zscore(returns, {ret_z})))"
            for w in [0.30, 0.35, 0.40, 0.45, 0.50]:
                for decay in [3, 4, 5, 6, 7]:
                    label = f"{region}_{sig_name}_plain_r{ret_z}_w{w}_d{decay}"
                    VARIANTS.append((label, f"scale({fund_plain}) + {ret_expr} * {w}",
                        {"decay": decay, "region": region, "universe": universe}, region))
                    label = f"{region}_{sig_name}_gzi_r{ret_z}_w{w}_d{decay}"
                    VARIANTS.append((label, f"scale({fund_gz}) + {ret_expr} * {w}",
                        {"decay": decay, "region": region, "universe": universe}, region))

logger.info("V32 multi-region scan | %d variants | log: %s", len(VARIANTS), PROGRESS_LOG_PATH)

def wait_for_production_correlation(api, pid, max_wait_s=3600):
    waited = 0
    while waited < max_wait_s:
        try:
            ch = api.session.get(f"https://api.worldquantbrain.com/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                chj = ch.json()
                checks = (chj.get("is") or {}).get("checks") or []
                pc_check = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), None)
                if pc_check:
                    result = pc_check.get("result", "")
                    value = pc_check.get("value", None)
                    if result in ("PASS", "FAIL", "WARNING"):
                        return _to_float(value)
            time.sleep(30); waited += 30
        except:
            time.sleep(30); waited += 30
    return None

def run_variant(api, label, expr, ov, region, pl):
    settings = settings_base.copy(); settings.update(ov)
    try: res = api.run_backtest(expr, settings=settings)
    except Exception as e:
        if pl: pl.step(extra={"label": label, "status": "exception", "error": str(e)[:80]})
        return None
    if not res or not res.get("platform_id"):
        if pl: pl.step(extra={"label": label, "status": "no_alpha_id"})
        return None
    pid = res["platform_id"]
    det = api.get_alpha_details(pid); is_ = det.get("is") or {}
    s = _to_float(is_.get("sharpe")) or 0.0; f = _to_float(is_.get("fitness")) or 0.0
    tvr = _to_float(is_.get("turnover")); marg = _to_float(is_.get("margin"))
    ret = _to_float(is_.get("returns"))
    ch = None
    for _ in range(5):
        try:
            r = api.session.get(f"https://api.worldquantbrain.com/alphas/{pid}/check", timeout=60)
            if r.status_code == 200 and r.text.strip(): ch = r.json(); break
            time.sleep(5)
        except: time.sleep(10)
    if ch is None: ch = {}
    checks = (ch.get("is") or {}).get("checks") or []
    ladder = next((c for c in checks if c.get("name") in ("IS_LADDER_SHARPE","LOW_2Y_SHARPE")), {})
    sub = next((c for c in checks if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
    sc = next((c for c in checks if c.get("name") == "SELF_CORRELATION"), {})
    pc = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), {})
    lv = ladder.get("value","?"); lr = ladder.get("result","?")
    sv = sub.get("value","?"); sr = sub.get("result","?")
    scv = sc.get("value","?"); scr = sc.get("result","?")
    pcv = pc.get("value","?"); pcr = pc.get("result","?")
    tvr_s = f"{tvr*100:.1f}%" if tvr else "?"; marg_s = f"{marg*10000:.1f}bp" if marg else "?"
    logger.info("[%s] S=%.3f F=%.3f TVR=%s M=%s | LAD=%s(%s) Sub=%s(%s) SC=%s(%s) PC=%s(%s)",
                label, s, f, tvr_s, marg_s, lv, lr, sv, sr, scv, scr, pcv, pcr)
    fails = []
    if s < PRE_SHARPE: fails.append(f"S={s:.3f}")
    if f < PRE_FITNESS: fails.append(f"F={f:.3f}")
    if tvr is not None and (tvr < HARD_TVR_MIN or tvr > HARD_TVR_MAX): fails.append(f"TVR={tvr:.4f}")
    if marg is not None and marg*10000 < HARD_MARGIN_BP: fails.append(f"M={marg*10000:.1f}bp")
    if ret is not None and ret < HARD_RETURNS: fails.append(f"Ret={ret:.4f}")
    if ch:
        fn = [c.get("name") for c in checks if c.get("result") == "FAIL"]
        if fn: fails.append(f"FAIL: {','.join(fn)}")
    status = "FAIL" if fails else "PENDING_PC"
    if pl: pl.step(extra={"label": label, "pid": pid, "status": status, "sharpe": s, "fitness": f, "tvr": tvr, "margin": marg, "ladder": lv, "ladder_result": lr, "sub": sv, "sub_result": sr, "self_corr": scv, "self_corr_result": scr, "prod_corr": pcv, "prod_corr_result": pcr, "fails": fails, "region": region})
    if fails:
        return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":False,"fails":fails,"ladder":lv,"ladder_result":lr,"region":region}

    # Cheap gates passed — wait for PC, but DO NOT submit!
    logger.info("[%s] >>> Cheap gates passed! Waiting for PC (NOT submitting)...", label)
    pc_val = wait_for_production_correlation(api, pid, max_wait_s=3600)
    if pc_val is None:
        logger.warning("[%s] PC timeout! Candidate reported but PC unknown.", label)
        if pl: pl.step(extra={"label": label, "status": "PC_TIMEOUT"})
        return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":False,"fails":["PC_TIMEOUT"],"ladder":lv,"ladder_result":lr,"region":region,"prod_corr":"timeout"}
    if pc_val >= MAX_PROD_CORR:
        logger.warning("[%s] PC=%.4f >= 0.70! NOT a valid candidate.", label, pc_val)
        if pl: pl.step(extra={"label": label, "status": "PC_FAIL", "prod_corr": pc_val})
        return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":False,"fails":[f"PC={pc_val:.4f}"],"ladder":lv,"ladder_result":lr,"region":region,"prod_corr":pc_val}

    # PC < 0.70 — valid candidate! Report but do NOT submit.
    logger.info("[%s] >>> VALID CANDIDATE (PC=%.4f < 0.70)! Reporting to user (NOT submitting).", label, pc_val)
    if pl: pl.step(extra={"label": label, "status": "VALID_CANDIDATE", "prod_corr": pc_val})
    return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":True,"fails":[],"ladder":lv,"ladder_result":lr,"region":region,"prod_corr":pc_val}

api = WqApiSimple()
results = []; candidates = []  # candidates = PC<0.70 valid alphas (not submitted)
pl = ProgressLogger(total_steps=len(VARIANTS), log_path=PROGRESS_LOG_PATH, task_name="v32_kor_region", emit_interval_sec=15.0, max_recent=5)
pl.start(meta={"regions":["ASI","CHN","KOR"],"variants":len(VARIANTS)})
try:
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="v30") as ex:
        futs = {}
        for label, expr, ov, region in VARIANTS:
            futs[ex.submit(run_variant, api, label, expr, ov, region, pl)] = label
        for fut in as_completed(futs):
            label = futs[fut]
            try: r = fut.result()
            except Exception as e:
                pl.step(extra={"label": label, "status": "future_exception", "error": str(e)[:80]})
                continue
            if r:
                results.append(r)
                if r.get("passed"):
                    candidates.append(r)
                    logger.info(">>> VALID CANDIDATE [%s]! (total: %d)", label, len(candidates))
except Exception as e:
    logger.error("V32 aborted: %s", e)
finally:
    pl.finish(summary={"total":len(VARIANTS),"completed":len(results),"candidates":len(candidates)})

results.sort(key=lambda x: -(x.get("sharpe",0) or 0))
logger.info("V32 complete | %d done, %d valid candidates (NOT submitted)", len(results), len(candidates))
for r in results[:20]:
    tvr = r.get("tvr"); tvr_s = f"{tvr*100:.1f}%" if tvr else "?"
    pc = r.get("prod_corr","?")
    reg = r.get("region","?")
    logger.info("  %-45s %s S=%-6.3f F=%-6.3f TVR=%-7s LAD=%-5s(%s) PC=%s %s",
                f"{reg}/{r['label']}", "CANDIDATE" if r.get("passed") else "FAIL",
                r.get("sharpe",0), r.get("fitness",0), tvr_s,
                r.get("ladder","?"), r.get("ladder_result","?"), pc,
                "; ".join(r.get("fails",[]))[:40])

out_path = os.path.join(_HERE, "results", f"scan_v32_kor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f: json.dump({"results":results,"candidates":candidates}, f, indent=2)
logger.info("Saved to %s", out_path)

# Print final candidate list
if candidates:
    print("\n" + "="*80)
    print(f"VALID CANDIDATES (PC < 0.70, NOT submitted — for user to submit):")
    print("="*80)
    for c in candidates:
        print(f"  Region={c['region']} | PID={c['pid']} | S={c['sharpe']:.3f} F={c['fitness']:.3f} TVR={c['tvr']*100:.1f}% LAD={c['ladder']}({c['ladder_result']}) PC={c.get('prod_corr','?')}")
        print(f"    Label: {c['label']}")
