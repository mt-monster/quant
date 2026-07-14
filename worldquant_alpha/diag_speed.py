#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断回测速度：定位 ts_backfill 是否为卡顿元凶。"""
import sys, os, time
sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv(os.path.abspath(".env"))
from wd_lib_wrapper import WqApiSimple
from mine_usa_ppa_single import SETTINGS

api = WqApiSimple()

def try_expr(label, expr, max_wait=300):
    print(f"\n=== {label} ===", flush=True)
    print("EXPR:", expr, flush=True)
    t0 = time.time()
    try:
        res = api.run_backtest(expr, settings=SETTINGS.copy(), max_wait_time=max_wait)
    except Exception as e:
        print(f"EXCEPTION after {time.time()-t0:.1f}s: {e}", flush=True)
        return
    dt = time.time() - t0
    if res and res.get("platform_id"):
        pid = res["platform_id"]
        det = api.get_alpha_details(pid)
        is_ = det.get("is") or {}
        print(f"OK in {dt:.1f}s -> pid={pid} S={is_.get('sharpe')} F={is_.get('fitness')} status={det.get('status')}", flush=True)
    else:
        print(f"NO RESULT after {dt:.1f}s (timeout or fail)", flush=True)

# 1) 无 ts_backfill 的单字段 rank
try_expr("A_no_tsbackfill_single", "rank(inst6_num_of_institutional_buyers)")
# 2) 无 ts_backfill 的双字段 subtract
try_expr("B_no_tsbackfill_pair", "rank(subtract(inst6_num_of_institutional_buyers, inst6_num_of_institutional_sellers))")
# 3) 短窗口 ts_backfill
try_expr("C_tsbackfill_5", "rank(subtract(ts_backfill(inst6_num_of_institutional_buyers, 5), ts_backfill(inst6_num_of_institutional_sellers, 5)))")
print("\nDIAG_DONE", flush=True)
