#!/usr/bin/env python3
"""
USA / delay=D1 / dataset_id=analyst44 / neutralization=RAM  PPA Alpha mining.
4-thread concurrent backtesting, results stored in pipeline_alphas DB table.
"""
from __future__ import annotations
import argparse, hashlib, json, logging, os, random, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import combinations
from threading import Lock
from typing import Any, Dict, List, Optional, Set, Tuple
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from wd_lib.api.datasets import get_datafields, get_datasets
    from wd_lib_wrapper import get_api
    from database import (save_alpha, alpha_exists, get_session,
                          PipelineAlpha, save_pipeline_alphas,
                          update_pipeline_alpha_backtest, get_pipeline_alpha_by_hash)
except ImportError:
    from worldquant_alpha.wd_lib.api.datasets import get_datafields, get_datasets
    from worldquant_alpha.wd_lib_wrapper import get_api
    from worldquant_alpha.database import (save_alpha, alpha_exists, get_session,
                          PipelineAlpha, save_pipeline_alphas,
                          update_pipeline_alpha_backtest, get_pipeline_alpha_by_hash)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "mine_analyst44.log"), encoding="utf-8")])
logger = logging.getLogger(__name__)

DATASET_ID = "analyst44"
TARGET_COUNT = 2
MAX_PROD_CORR = 0.7
CONCURRENT_THREADS = 4
SEARCH_SCOPE = {"instrumentType": "EQUITY", "region": "USA", "delay": 1, "universe": "TOP3000"}
DEFAULT_RAM_FIELD = os.environ.get("WQ_RAM_NEUTRAL_FIELD", "sta1_top3000c50")
BACKTEST_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "NONE", "truncation": 0.08,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P0Y",
}
_PROD_CORR_NAMES = ("PRODUCTION_CORRELATION","PROD_CORRELATION","MAX_PRODUCTION_CORRELATION","PRODUCTION_CORR")
_found_lock = Lock()

def _unwrap_session(api): return api.session

def field_wrap(f): return f"winsorize(ts_backfill({f}, 63), std=4)"

def field_wrap_variant(f, v):
    vs = [lambda x: f"winsorize(ts_backfill({x}, 63), std=4)",
          lambda x: f"winsorize(ts_backfill({x}, 120), std=3)",
          lambda x: f"ts_backfill({x}, 63)",
          lambda x: f"winsorize({x}, std=4)",
          lambda x: f"ts_backfill({x}, 120)",
          lambda x: f"rank(ts_backfill({x}, 63))"]
    return vs[v % len(vs)](f)

def apply_ram_neutralization(expr, ram_field):
    if "group_neutralize(" in expr: return expr
    return f"group_neutralize({expr}, {ram_field})"

def build_two_field_expressions(f1, f2):
    a, b = field_wrap(f1), field_wrap(f2)
    return [
        f"rank(subtract({a}, {b}))",
        f"rank(divide({a}, abs({b}) + 0.01))",
        f"rank(add({a}, {b}))",
        f"rank(multiply({a}, {b}))",
        f"rank(subtract(abs({a}), abs({b})))",
        f"rank(divide(subtract({a}, {b}), add(abs({a}), abs({b}) + 0.01))",
        f"rank(ts_corr({a}, {b}, 10))",
        f"rank(ts_corr({a}, {b}, 20))",
        f"rank(ts_corr({a}, {b}, 60))",
        f"rank(add(ts_rank({a}, 10), ts_rank({b}, 10)))",
        f"rank(add(ts_rank({a}, 22), ts_rank({b}, 22)))",
        f"rank(subtract(ts_rank({a}, 22), ts_rank({b}, 22)))",
        f"rank(subtract({a}, ts_delay({b}, 5)))",
        f"rank(subtract({a}, ts_delay({b}, 10)))",
        f"rank(subtract(ts_delta({a}, 5), ts_delta({b}, 5)))",
        f"rank(subtract(ts_delta({a}, 10), ts_delta({b}, 10)))",
        f"rank(ts_regression({a}, {b}, 20, 0, 2))",
        f"rank(ts_regression({a}, {b}, 60, 0, 2))",
        f"rank(ts_covariance({a}, {b}, 20))",
        f"rank(ts_covariance({a}, {b}, 60))",
        f"rank(divide(ts_min({a}, 20), ts_max({b}, 20) + 0.01))",
        f"rank(divide(ts_max({a}, 20), ts_min({b}, 20) + 0.01))",
        f"rank(subtract(ts_mean({a}, 20), ts_mean({b}, 20)))",
        f"rank(subtract(ts_mean({a}, 60), ts_mean({b}, 60)))",
        f"rank(divide(ts_std_dev({a}, 20) + 0.001, ts_std_dev({b}, 20) + 0.001))",
        f"rank(subtract(zscore({a}), zscore({b})))",
        f"rank(multiply(ts_delta({a}, 5), ts_delta({b}, 5)))",
        f"rank(add(ts_decay_linear({a}, 10), ts_decay_linear({b}, 10)))",
        f"rank(subtract(ts_decay_linear({a}, 10), ts_decay_linear({b}, 10)))",
    ]

def build_two_field_expressions_v2(f1, f2, v):
    a, b = field_wrap_variant(f1, v), field_wrap_variant(f2, v+1)
    return [f"rank(subtract({a}, {b}))", f"rank(ts_corr({a}, {b}, 20))",
            f"rank(add(ts_rank({a}, 22), ts_rank({b}, 22)))",
            f"rank(ts_regression({a}, {b}, 20, 0, 2))",
            f"rank(subtract(ts_mean({a}, 20), ts_mean({b}, 20)))",
            f"rank(multiply({a}, {b}))"]

def parse_production_correlation(p):
    if not p: return None
    for c in ((p.get("is") or {}).get("checks") or []):
        n = (c.get("name") or "").upper()
        if any(k in n for k in _PROD_CORR_NAMES):
            v = c.get("value")
            if v is None: return None
            try: return abs(float(v))
            except: return None
    for c in ((p.get("is") or {}).get("checks") or []):
        if "PRODUCTION" in (c.get("name") or "").upper():
            v = c.get("value")
            if v is not None:
                try: return abs(float(v))
                except: pass
    return None

def wait_for_production_correlation(api, aid, max_wait=1800, poll=25):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try: ch = api.get_alpha_check(aid)
        except Exception as e:
            logger.warning("check fail: %s", e); time.sleep(poll); continue
        c = parse_production_correlation(ch)
        if c is not None: return c
        logger.info("prod corr not ready, %ss retry (%s)", poll, aid)
        time.sleep(poll)
    return None

def passes_submission_shape(api, aid, ms, mf):
    d = api.get_alpha_details(aid); i = d.get("is") or {}
    try: s = float(i.get("sharpe") or 0); f = float(i.get("fitness") or 0)
    except: return False, 0.0, 0.0
    return (True, s, f) if s >= ms and f >= mf else (False, s, f)

def verify_dataset_unlit(api, did):
    df = get_datasets(session=_unwrap_session(api),
                      instrument_type=SEARCH_SCOPE["instrumentType"],
                      region=SEARCH_SCOPE["region"],
                      delay=SEARCH_SCOPE["delay"],
                      universe=SEARCH_SCOPE["universe"])
    if df is None or df.empty: return False
    for _, r in df.iterrows():
        if str(r.get("id", "")) == did:
            try: pm = float(r.get("pyramidMultiplier", 1.0))
            except: pm = 1.0
            logger.info("dataset %s: pm=%.4f fields=%s name=%s", did, pm, r.get("fieldCount"), r.get("name",""))
            return abs(pm - 1.0) < 1e-6
    logger.warning("dataset %s not found in list", did); return False

def fetch_matrix_fields(api, did, limit=50):
    df = get_datafields(search_scope=SEARCH_SCOPE, dataset_id=did, field_type="MATRIX", session=_unwrap_session(api))
    if df is None or df.empty: return []
    return df[df["type"] == "MATRIX"]["id"].tolist()[:limit]

def expr_hash(e): return hashlib.sha256(e.encode()).hexdigest()

def save_pipeline_exprs_to_db(expressions, round_num):
    db = get_session(); to_sim = {}
    try:
        for expr, f1, f2 in expressions:
            h = expr_hash(expr)
            ex = get_pipeline_alpha_by_hash(db, h)
            if ex and ex.backtest_status in ("completed", "running"): continue
            to_sim[h] = (expr, f1, f2)
        ne = [it[0] for it in to_sim.values()]
        if ne:
            save_pipeline_alphas(db, ne, order=1, stage=f"analyst44_r{round_num}",
                                 settings={**BACKTEST_SETTINGS, "dataset_id": DATASET_ID}, dataset_id=DATASET_ID)
    except Exception as e: logger.warning("pipeline db err: %s", e)
    finally: db.close()
    return to_sim

def update_pipeline_db(h, **kw):
    try:
        db = get_session()
        try: update_pipeline_alpha_backtest(db, h, **kw)
        finally: db.close()
    except Exception as e: logger.warning("update pipeline err: %s", e)

def backtest_one(api, expr, f1, f2, eh, ram_field, ms, mf, pcw, sn):
    ram_expr = apply_ram_neutralization(expr, ram_field)
    logger.info("SIM #%d [%s] (%s,%s) %s", sn, DATASET_ID, f1[:20], f2[:20], ram_expr[:80])
    update_pipeline_db(eh, backtest_status="running")
    try: res = api.run_backtest(ram_expr, settings=BACKTEST_SETTINGS.copy())
    except Exception as e:
        logger.warning("bt err: %s", e); update_pipeline_db(eh, backtest_status="failed", error_message=str(e)); return None
    if not res: update_pipeline_db(eh, backtest_status="failed", error_message="no result"); return None
    pid = res.get("platform_id")
    if not pid: update_pipeline_db(eh, backtest_status="failed", error_message="no pid"); return None
    ok, sh, fi = passes_submission_shape(api, pid, ms, mf)
    if not ok:
        logger.info("IS fail S=%.3f F=%.3f", sh, fi)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True, platform_alpha_id=pid, sharpe=sh, fitness=fi)
        return None
    logger.info("IS ok S=%.3f F=%.3f, waiting prod corr…", sh, fi)
    pc = wait_for_production_correlation(api, pid, max_wait=pcw)
    if pc is None:
        logger.warning("no prod corr for %s", pid)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True, platform_alpha_id=pid, sharpe=sh, fitness=fi)
        return None
    if pc > MAX_PROD_CORR:
        logger.info("prod corr %.4f > %.2f, skip", pc, MAX_PROD_CORR)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True, platform_alpha_id=pid, sharpe=sh, fitness=fi,
                           checks_payload={"production_correlation": pc})
        return None
    rec = {"platform_alpha_id": pid, "dataset_id": DATASET_ID, "expression": ram_expr,
           "base_two_field_expression": expr, "field_1": f1, "field_2": f2,
           "ram_neutral_field": ram_field, "sharpe": sh, "fitness": fi,
           "production_correlation": pc, "found_at": datetime.now().isoformat(), "simulation_number": sn}
    update_pipeline_db(eh, backtest_status="completed", is_tested=True, platform_alpha_id=pid,
                       sharpe=sh, fitness=fi, checks_payload={"production_correlation": pc, "passed": True}, candidate_status="candidate")
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-sharpe", type=float, default=1.25)
    ap.add_argument("--min-fitness", type=float, default=1.0)
    ap.add_argument("--max-pairs-per-round", type=int, default=15)
    ap.add_argument("--field-sample", type=int, default=40)
    ap.add_argument("--prod-corr-wait", type=int, default=1800)
    ap.add_argument("--ram-neutral-field", type=str, default=DEFAULT_RAM_FIELD)
    args = ap.parse_args()
    logger.info("=" * 72)
    logger.info("USA D1 RAM PPA | dataset=%s | %d concurrent | target %d", DATASET_ID, CONCURRENT_THREADS, TARGET_COUNT)
    logger.info("=" * 72)
    api = get_api(); rng = random.Random(42)
    is_unlit = verify_dataset_unlit(api, DATASET_ID)
    if not is_unlit: logger.warning("dataset %s not unlit pyramid, continuing anyway", DATASET_ID)
    fields = fetch_matrix_fields(api, DATASET_ID, limit=args.field_sample)
    if len(fields) < 2: logger.error("fields < 2, abort"); return
    logger.info("dataset %s has %d MATRIX fields: %s", DATASET_ID, len(fields), fields[:10])
    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)
    found = []; tried = set(); total_sim = 0; rnd = 0
    while len(found) < TARGET_COUNT:
        rnd += 1
        logger.info("--- Round %d | found %d/%d | sims %d ---", rnd, len(found), TARGET_COUNT, total_sim)
        pairs = list(combinations(fields, 2)); rng.shuffle(pairs)
        raw = []
        for f1, f2 in pairs[:args.max_pairs_per_round]:
            for e in build_two_field_expressions(f1, f2):
                h = expr_hash(e)
                if h not in tried: tried.add(h); raw.append((e, f1, f2))
        rng.shuffle(pairs)
        for f1, f2 in pairs[:max(args.max_pairs_per_round // 2, 3)]:
            for v in range(3):
                for e in build_two_field_expressions_v2(f1, f2, v):
                    h = expr_hash(e)
                    if h not in tried: tried.add(h); raw.append((e, f1, f2))
        rng.shuffle(raw)
        logger.info("round %d: %d candidates", rnd, len(raw))
        if not raw: continue
        to_sim = save_pipeline_exprs_to_db(raw, rnd)
        if not to_sim: logger.info("all exprs already in DB, skip round"); continue
        items = list(to_sim.items())
        logger.info("round %d: %d to simulate", rnd, len(items))
        with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS, thread_name_prefix="W") as ex:
            futs = {}
            for eh, (expr, f1, f2) in items:
                if len(found) >= TARGET_COUNT: break
                with _found_lock: total_sim += 1; sn = total_sim
                futs[ex.submit(backtest_one, api, expr, f1, f2, eh,
                               args.ram_neutral_field, args.min_sharpe, args.min_fitness,
                               args.prod_corr_wait, sn)] = (expr, f1, f2, eh)
            for fut in as_completed(futs):
                expr, f1, f2, eh = futs[fut]
                try: rec = fut.result()
                except Exception as e: logger.warning("future err: %s", e); continue
                if rec:
                    with _found_lock:
                        found.append(rec)
                        logger.info("HIT #%d/%d id=%s corr=%.4f S=%.3f F=%.3f",
                                    len(found), TARGET_COUNT, rec["platform_alpha_id"],
                                    rec["production_correlation"], rec["sharpe"], rec["fitness"])
                    try: save_alpha(rec["expression"], f"USA_RAM_PPA_{DATASET_ID}",
                                    {**BACKTEST_SETTINGS, "dataset_id": DATASET_ID,
                                     "ram_neutral_field": args.ram_neutral_field,
                                     "base_expression": expr, "field_1": f1, "field_2": f2})
                    except: pass
                    with _found_lock:
                        p = os.path.join(rdir, f"analyst44_ram_ppa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                        with open(p, "w", encoding="utf-8") as fout:
                            json.dump({"target": TARGET_COUNT, "found": len(found), "max_prod_corr": MAX_PROD_CORR,
                                       "dataset_id": DATASET_ID, "total_simulations": total_sim, "rounds": rnd, "alphas": found},
                                      fout, indent=2, ensure_ascii=False)
                        logger.info("saved to %s", p)
                with _found_lock:
                    if len(found) >= TARGET_COUNT:
                        logger.info("TARGET REACHED, cancelling…")
                        for fc in futs: fc.cancel()
                        break
        if len(found) < TARGET_COUNT:
            logger.info("round %d done, %d/%d, continuing…", rnd, len(found), TARGET_COUNT)
            time.sleep(2)
    p = os.path.join(rdir, f"analyst44_ram_ppa_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as fout:
        json.dump({"target": TARGET_COUNT, "found": len(found), "max_prod_corr": MAX_PROD_CORR,
                   "dataset_id": DATASET_ID, "total_simulations": total_sim, "rounds": rnd, "alphas": found},
                  fout, indent=2, ensure_ascii=False)
    logger.info("FINAL saved to %s", os.path.abspath(p))
    for i, a in enumerate(found, 1):
        logger.info("  Alpha #%d: %s S=%.3f F=%.3f PC=%.4f", i, a["platform_alpha_id"], a["sharpe"], a["fitness"], a["production_correlation"])

if __name__ == "__main__":
    main()