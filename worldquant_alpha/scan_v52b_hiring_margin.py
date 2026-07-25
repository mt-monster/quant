#!/usr/bin/env python3
"""V52b: hiring_trends 近关救援 — S=2.5 F=1.74 TVR=16.7% 只卡 M=9.7bp (需>10).

固定近关表达式, 微扫 decay/neut/trunc/universe 抬 margin; submit_gate; 不提交.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, after_batch_cooldown, envelope_summary, run_multi_batch, chunked
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
COOLDOWN = float(os.environ.get("V52B_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
CKPT = os.path.join(_HERE, "results", "v52b_hiring_margin_checkpoint.json")
PROGRESS = os.path.join(_HERE, "results", "v52b_hiring_margin_progress.log")
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
DATASET = "hiring_trends"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v52b")

# 近关父表达式 (impR_0_w126to63)
BASE_EXPRS = [
    # S=2.5 F=1.74 TVR=16.7% M=9.7bp — 只差 margin
    "rank(group_zscore(ts_zscore(ts_backfill(vec_avg(aggregate_open_positions_count), 66), 63), industry))",
    "rank(group_zscore(ts_zscore(ts_backfill(vec_avg(aggregate_open_positions_count), 22), 63), industry))",
    "rank(group_zscore(ts_zscore(ts_backfill(vec_avg(aggregate_open_positions_count), 66), 126), industry))",
    "rank(group_zscore(ts_zscore(ts_backfill(vec_avg(fresh_open_positions_count), 66), 63), industry))",
    "rank(ts_rank(ts_backfill(vec_avg(aggregate_open_positions_count), 66), 126))",
]

GATE_S, GATE_F, GATE_M_BP = 1.58, 1.0, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
MAX_PC = 0.70


def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def base_settings(uni, decay, neut, trunc):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": uni, "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc,
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
        "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
    }


def build():
    out, seen = [], set()
    for i, expr in enumerate(BASE_EXPRS):
        for uni in ("TOP3000", "TOP2000", "ILLIQUID_MINVOL1M"):
            for decay in (1, 2, 3, 4, 5, 6, 8):
                for neut in ("SECTOR", "INDUSTRY", "SUBINDUSTRY"):
                    for trunc in (0.01, 0.02, 0.05, 0.08):
                        # 稀疏: 优先低 decay 抬 margin 倾向
                        key = (expr, uni, decay, neut, trunc)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append({
                            "label": f"m{i}_{uni[:6]}_d{decay}_{neut[:3]}_t{int(trunc*100)}",
                            "expr": expr,
                            "settings": base_settings(uni, decay, neut, trunc),
                        })
    # 优先 TOP3000 + 中低 decay
    def prio(v):
        s = v["settings"]
        sc = 0
        if s["universe"] == "TOP3000": sc += 5
        if s["decay"] in (2, 3, 4): sc += 3
        if s["neutralization"] == "SECTOR": sc += 2
        return -sc
    out.sort(key=prio)
    logger.info("built %d variants, trim 160", len(out))
    return out[:160]


def eval_one(api, label, pid, expr, settings):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m, ret = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0, _f(is_.get("returns")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_S: fails.append(f"S={s:.3f}")
    if f <= GATE_F: fails.append(f"F={f:.3f}")
    if tvr <= GATE_TVR_LO or tvr >= GATE_TVR_HI: fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_M_BP: fails.append(f"M={m_bp:.1f}bp")
    if ret <= 0.05: fails.append(f"Ret={ret:.4f}")
    status = "PASS_CHEAP" if not fails else "FAIL"
    # 近关也拉 check
    if s > 1.5 and m_bp > 8:
        try:
            ch = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                checks = (ch.json().get("is") or {}).get("checks") or []
                pfails = [c.get("name") for c in checks if c.get("result") == "FAIL"]
                if status == "PASS_CHEAP" and pfails:
                    fails.extend([f"PF:{x}" for x in pfails])
                    status = "FAIL"
                for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
                    c = next((x for x in checks if x.get("name") == name), None)
                    if c:
                        val = _f(c.get("value"))
                        if c.get("result") == "FAIL" or (val is not None and val <= 1.6):
                            fails.append(f"{name}={val}")
                            status = "FAIL"
        except Exception:
            pass
    return {
        "label": label, "pid": pid, "expr": expr, "settings": settings,
        "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "margin_bp": m_bp,
        "status": status, "fails": fails,
    }


def wait_pc(api, pid, max_wait=3600):
    waited = 0
    while waited < max_wait:
        try:
            ch = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                checks = (ch.json().get("is") or {}).get("checks") or []
                pc = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), None)
                if pc and pc.get("result") in ("PASS", "FAIL", "WARNING"):
                    return _f(pc.get("value"))
        except Exception:
            pass
        time.sleep(30)
        waited += 30
    return None


def main():
    variants = build()
    logger.info("V52b margin rescue | %d | %s", len(variants), envelope_summary())
    api = WqApiSimple()
    session = api.session
    results, found = [], []
    if os.path.exists(CKPT):
        try:
            ck = json.load(open(CKPT, encoding="utf-8"))
            results = list(ck.get("results") or [])
            found = list(ck.get("found_alphas") or [])
            done = {r.get("label") for r in results}
            variants = [v for v in variants if v["label"] not in done]
        except Exception:
            pass
    total_jobs = len(variants) + len(results)
    start_ts = time.time()

    for bi, batch in enumerate(chunked(variants, BATCH_SIZE)):
        if found:
            break
        logger.info("--- Batch %d ---", bi + 1)
        raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
        by = {b["label"]: b for b in batch}
        for item in raw:
            b = by.get(item["label"])
            if not item.get("ok") or not item.get("pid") or not b:
                results.append({"label": item["label"], "status": "error"})
                continue
            r = eval_one(api, item["label"], item["pid"], b["expr"], b["settings"])
            results.append(r)
            logger.info(
                "  %s S=%.3f F=%.3f TVR=%.3f M=%.1fbp %s %s",
                r["label"], r["sharpe"], r["fitness"], r["tvr"], r["margin_bp"], r["status"], r["fails"][:2],
            )
            if r["status"] == "PASS_CHEAP":
                # risk-neut quick
                try:
                    rn = api.run_backtest(r["expr"], settings={**r["settings"], "neutralization": "MARKET"})
                    if rn and rn.get("platform_id"):
                        det = api.get_alpha_details(rn["platform_id"])
                        is_ = det.get("is") or {}
                        rs, rf = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
                        rm = (_f(is_.get("margin")) or 0) * 10000
                        if not (rs > 1 and rf > 0.7 and rm > 10):
                            logger.info("  risk-neut FAIL s=%.2f f=%.2f m=%.1f", rs, rf, rm)
                            continue
                        rn_stats = {"s": rs, "f": rf, "m_bp": rm}
                    else:
                        continue
                except Exception as e:
                    logger.warning("risk-neut: %s", e)
                    continue
                pc = wait_pc(api, r["pid"])
                if pc is None or pc >= MAX_PC:
                    logger.warning("  PC=%s 淘汰", pc)
                    continue
                info = {
                    "dataset": DATASET, "style": "hiring_ts_rank_rescue", "pid": r["pid"],
                    "label": r["label"], "expr": r["expr"], "sharpe": r["sharpe"],
                    "fitness": r["fitness"], "tvr": r["tvr"], "margin_bp": r["margin_bp"],
                    "prod_corr": pc, "risk_neut": rn_stats, "settings": r["settings"],
                    "submitted": False, "tags": ["v52b", DATASET, "USA_D1", "READY_MANUAL", "NO_SUBMIT"],
                }
                try:
                    api.session.patch(
                        f"{API_BASE}/alphas/{r['pid']}",
                        json={"color": "GREEN", "name": f"v52b_{r['label']}"[:80],
                              "tags": info["tags"], "regular": {"description": r["expr"][:200]}},
                        timeout=60,
                    )
                except Exception:
                    pass
                found.append(info)
                ready = json.load(open(READY, encoding="utf-8")) if os.path.exists(READY) else {"goal": 10, "alphas": []}
                info["n"] = len(ready.get("alphas", [])) + 1
                ready.setdefault("alphas", []).append(info)
                with open(READY, "w", encoding="utf-8") as f:
                    json.dump(ready, f, ensure_ascii=False, indent=2)
                logger.info("*** FOUND %s S=%.3f M=%.1fbp PC=%.4f (NO SUBMIT) ***", r["pid"], r["sharpe"], r["margin_bp"], pc)
        with open(CKPT, "w", encoding="utf-8") as f:
            json.dump({"results": results, "found_alphas": found}, f, ensure_ascii=False, indent=2)
        # ---- progress log ----
        done_now = len(results)
        el = time.time() - start_ts
        pct = done_now / total_jobs * 100 if total_jobs else 0
        prog = json.dumps({
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "event": "progress",
            "task": "v52b_hiring_margin",
            "done": done_now, "total": total_jobs,
            "pct": round(pct, 1), "elapsed_sec": round(el, 1),
        }, ensure_ascii=False)
        with open(PROGRESS, "a", encoding="utf-8") as pf:
            pf.write(prog + "\n")
        if bi + 1 < (len(variants) + BATCH_SIZE - 1) // BATCH_SIZE and not found:
            after_batch_cooldown(COOLDOWN)

    # 报告最佳 margin
    okm = [r for r in results if r.get("margin_bp") is not None]
    okm.sort(key=lambda x: (x.get("margin_bp") or 0), reverse=True)
    logger.info("Done found=%d; top margin: %s", len(found), [
        (round(x.get("margin_bp") or 0, 1), round(x.get("sharpe") or 0, 2), x.get("label")) for x in okm[:5]
    ])


if __name__ == "__main__":
    main()
