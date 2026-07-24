#!/usr/bin/env python3
"""V39b: insider_matrix 微救援 — SUB 0.82→过 0.84 limit.

近关: KPELJG11 indmom eur_top_value_1 TOP3000 d3 SECTOR
  S=1.95 F=1.54 TVR=10.5% 2y=1.75 PASS; SUB=0.82 limit=0.84 (差0.02)

微扫: 窗口/decay/trunc/neut/universe/winsor/scale, 禁 add/multiply; 不提交。
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

from multi_sim import API_BASE, chunked, run_multi_batch
from progress_logger import ProgressLogger
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
BATCH_COOLDOWN_SEC = float(os.environ.get("V39B_COOLDOWN", "40"))
PROGRESS_LOG_PATH = os.path.join(_HERE, "results", f"v39b_sub_micro_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
CKPT_PATH = os.path.join(_HERE, "results", "v39b_sub_micro_checkpoint.json")
FOUND_PATH = os.path.join(_HERE, "results", f"scan_v39b_sub_micro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
DATASET = "insider_matrix"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v39b")

GATE_SHARPE = 1.58
GATE_FITNESS = 1.0
GATE_MARGIN_BP = 10.0
GATE_TVR_MIN = 0.05
GATE_TVR_MAX = 0.30
GATE_RETURNS = 0.05
GATE_2Y = 1.6
GATE_RISK_NEUT_S = 1.0
GATE_RISK_NEUT_F = 0.7
GATE_RISK_NEUT_M_BP = 10.0
MAX_PROD_CORR = 0.70
MAX_OPS = 6
TARGET_ALPHAS = 1

FIELDS = ["eur_top_value_1", "eur_aggregated_value_2", "eur_aggregated_value_1", "eur_top_value_2"]


def _f(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def count_operators(expr: str) -> int:
    low = expr.lower().replace(" ", "")
    if "trade_when(" in low or "add(" in low or "multiply(" in low:
        return 999
    if "*" in expr or re.search(r"(?<![eE])\+", expr):
        return 999
    return len(re.findall(r"[a-z_]+\(", expr.lower()))


def base_settings(universe, decay, neut, trunc) -> Dict[str, Any]:
    return {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": universe,
        "delay": 1,
        "decay": decay,
        "neutralization": neut,
        "truncation": trunc,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "ON",
        "language": "FASTEXPR",
        "visualization": False,
        "testPeriod": "P6Y",
        "maxTrade": "OFF",
    }


def build_variants() -> List[Dict[str, Any]]:
    variants, seen = [], set()

    def add(label, expr, universe, decay, neut, trunc, style, field):
        ops = count_operators(expr)
        if ops >= MAX_OPS or ops > 900:
            return
        key = (expr, universe, decay, neut, trunc)
        if key in seen:
            return
        seen.add(key)
        variants.append({
            "label": label, "expr": expr,
            "settings": base_settings(universe, decay, neut, trunc),
            "style": style, "field": field, "ops": ops,
        })

    for f in FIELDS:
        short = f.replace("eur_", "").replace("aggregated_value_", "a").replace("top_value_", "t")[:10]
        for bf, zw in [(40, 126), (66, 126), (66, 189), (66, 252), (90, 189), (120, 189)]:
            for uni in ["TOP3000", "TOP2000"]:
                for decay in [2, 3, 4, 5]:
                    for neut in ["SECTOR", "INDUSTRY"]:
                        for trunc in [0.01, 0.05, 0.08, 0.12]:
                            # 近关骨架
                            add(
                                f"gz_{short}_b{bf}z{zw}_{uni}_d{decay}_{neut[:3]}_t{int(trunc*100)}",
                                f"rank(group_zscore(ts_zscore(ts_backfill({f}, {bf}), {zw}), industry))",
                                uni, decay, neut, trunc, "gz_ind", f,
                            )
        # 额外稳健化 (少网格)
        for uni in ["TOP3000", "TOP2000"]:
            for decay in [3, 4]:
                for neut in ["SECTOR", "INDUSTRY"]:
                    add(f"gzsec_{short}_{uni}_d{decay}", f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), sector))", uni, decay, neut, 0.08, "gz_sec", f)
                    add(f"wz_{short}_{uni}_d{decay}", f"rank(winsorize(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry), std=3))", uni, decay, neut, 0.05, "wz_gz", f)
                    add(f"sc_{short}_{uni}_d{decay}", f"scale(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))", uni, decay, neut, 0.08, "scale_gz", f)
                    add(f"gr_{short}_{uni}_d{decay}", f"group_rank(ts_zscore(ts_backfill({f}, 66), 189), industry)", uni, decay, neut, 0.05, "gr", f)

    logger.info("Built %d variants", len(variants))
    return variants


def load_checkpoint():
    if not os.path.exists(CKPT_PATH):
        return None
    try:
        with open(CKPT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_checkpoint(results_list, found_list):
    tmp = CKPT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"results": results_list, "found_alphas": found_list}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CKPT_PATH)


def fetch_checks(api, pid, retries=6):
    for _ in range(retries):
        try:
            r = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if r.status_code == 200 and r.text.strip():
                checks = (r.json().get("is") or {}).get("checks") or []
                d = {c.get("name", ""): c for c in checks}
                fails = [c.get("name") for c in checks if c.get("result") == "FAIL"]
                return d, fails, True
            time.sleep(4)
        except Exception:
            time.sleep(8)
    return {}, [], False


def wait_for_pc(api, pid, max_wait_s=3600):
    waited = 0
    while waited < max_wait_s:
        try:
            ch = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                checks = (ch.json().get("is") or {}).get("checks") or []
                pc = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), None)
                if pc and pc.get("result") in ("PASS", "FAIL", "WARNING"):
                    return _f(pc.get("value"))
            time.sleep(30)
            waited += 30
        except Exception:
            time.sleep(30)
            waited += 30
    return None


def test_risk_neutralization(api, expr, base_s):
    settings = {**base_s, "neutralization": "MARKET"}
    try:
        res = api.run_backtest(expr, settings=settings)
        if res and res.get("platform_id"):
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s = _f(is_.get("sharpe")) or 0.0
            f = _f(is_.get("fitness")) or 0.0
            m = _f(is_.get("margin"))
            m_bp = m * 10000 if m else 0
            return (s > GATE_RISK_NEUT_S and f > GATE_RISK_NEUT_F and m_bp > GATE_RISK_NEUT_M_BP), {"s": s, "f": f, "m_bp": m_bp}
    except Exception as e:
        logger.warning("risk-neut: %s", e)
    return False, {}


def robust_overfit_test(api, expr, base_s) -> Dict[str, Any]:
    report = {"ok": True, "tests": []}
    probes = [
        ("decay+1", {**base_s, "decay": min(int(base_s.get("decay", 3)) + 1, 10)}),
        ("uni_TOP2000", {**base_s, "universe": "TOP2000"}),
        ("trunc_alt", {**base_s, "truncation": 0.05 if base_s.get("truncation", 0.08) != 0.05 else 0.08}),
        ("sign_flip", base_s),
    ]
    flip = expr[1:] if expr.startswith("-") else f"-{expr}"
    for name, settings in probes:
        try:
            e = flip if name == "sign_flip" else expr
            res = api.run_backtest(e, settings=settings)
            if not res or not res.get("platform_id"):
                report["ok"] = False
                report["tests"].append({"name": name, "error": "no_pid"})
                continue
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s = _f(is_.get("sharpe")) or 0.0
            f = _f(is_.get("fitness")) or 0.0
            entry = {"name": name, "sharpe": s, "fitness": f}
            if name == "sign_flip":
                entry["abs_ok"] = abs(s) > 0.8
                if not entry["abs_ok"]:
                    report["ok"] = False
            else:
                entry["stable"] = s > 0.9 and f > 0.5
                if not entry["stable"]:
                    report["ok"] = False
            report["tests"].append(entry)
            time.sleep(2)
        except Exception as e:
            report["ok"] = False
            report["tests"].append({"name": name, "error": str(e)[:80]})
    return report


def set_alpha_props(api, pid, name, tags):
    try:
        r = api.session.patch(
            f"{API_BASE}/alphas/{pid}",
            json={"color": "GREEN", "name": name[:80], "tags": tags, "regular": {"description": name[:200]}},
            timeout=60,
        )
        logger.info("set_props %s -> %s (NO SUBMIT)", pid, r.status_code)
        return r.ok
    except Exception as e:
        logger.warning("set_props: %s", e)
        return False


def evaluate_is(api, label, pid, expr, settings):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s = _f(is_.get("sharpe")) or 0.0
    f = _f(is_.get("fitness")) or 0.0
    tvr = _f(is_.get("turnover")) or 0.0
    m = _f(is_.get("margin")) or 0.0
    ret = _f(is_.get("returns")) or 0.0
    m_bp = m * 10000
    fails = []
    if s <= GATE_SHARPE:
        fails.append(f"S={s:.3f}")
    if f <= GATE_FITNESS:
        fails.append(f"F={f:.3f}")
    if tvr <= GATE_TVR_MIN or tvr >= GATE_TVR_MAX:
        fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_MARGIN_BP:
        fails.append(f"M={m_bp:.1f}bp")
    if ret <= GATE_RETURNS:
        fails.append(f"Ret={ret:.4f}")

    checks, plat_fails = {}, []
    sub_v, sub_lim, ladder_v = None, None, None
    if s > 1.4:  # 近关都拉 check
        checks, plat_fails, ok = fetch_checks(api, pid)
        sub = checks.get("LOW_SUB_UNIVERSE_SHARPE") or {}
        sub_v, sub_lim = _f(sub.get("value")), _f(sub.get("limit"))
        ladder = checks.get("LOW_2Y_SHARPE") or checks.get("IS_LADDER_SHARPE") or {}
        ladder_v = _f(ladder.get("value"))
        if not fails:
            if not ok:
                return {"label": label, "pid": pid, "expr": expr, "settings": settings, "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "status": "CHECK_PENDING", "fails": ["check_pending"], "sub_univ": sub_v, "sub_limit": sub_lim, "ladder": ladder_v, "checks": checks, "failed_checks": []}
            for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
                c = checks.get(name) or {}
                if c.get("result") == "FAIL":
                    fails.append(f"{name}_FAIL")
                val = _f(c.get("value"))
                if val is not None and val <= GATE_2Y:
                    fails.append(f"{name}={val:.3f}<=1.6")
            if plat_fails:
                fails.extend([f"PF:{x}" for x in plat_fails])
            # 额外记录 margin to limit
            if sub_v is not None and sub_lim is not None:
                logger.info("  SUB detail %s val=%.3f limit=%.3f gap=%+.3f", label, sub_v, sub_lim, sub_v - sub_lim)

    return {
        "label": label, "pid": pid, "expr": expr, "settings": settings,
        "sharpe": s, "fitness": f, "tvr": tvr, "margin": m,
        "status": "PASS_CHEAP" if not fails else "FAIL", "fails": fails,
        "sub_univ": sub_v, "sub_limit": sub_lim, "ladder": ladder_v,
        "checks": {k: {"value": v.get("value"), "result": v.get("result"), "limit": v.get("limit")} for k, v in checks.items()} if checks else {},
        "failed_checks": plat_fails,
    }


def run_batch_multi(api, session, batch):
    by_label = {b["label"]: b for b in batch}
    raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
    out = []
    for item in raw:
        b = by_label.get(item["label"])
        if not item.get("ok") or not item.get("pid") or not b:
            out.append({"label": item["label"], "status": "error", "fails": [item.get("error") or "no_pid"]})
            continue
        out.append(evaluate_is(api, item["label"], item["pid"], b["expr"], b["settings"]))
    return out


def main():
    VARIANTS = build_variants()
    # 优先: top_value_1 + TOP3000 + SECTOR + d3 附近
    def prio(v):
        s = 0
        if "top_value_1" in v["field"] or "t1" in v["label"]:
            s += 20
        if "a2" in v["label"] or "value_2" in v["field"]:
            s += 10
        if v["settings"]["universe"] == "TOP3000":
            s += 5
        if v["settings"]["neutralization"] == "SECTOR":
            s += 5
        if v["settings"]["decay"] in (3, 4):
            s += 3
        if "b66z189" in v["label"]:
            s += 4
        return -s

    VARIANTS.sort(key=prio)
    if len(VARIANTS) > 160:
        logger.info("Trim %d -> 160", len(VARIANTS))
        VARIANTS = VARIANTS[:160]

    vmeta = {v["label"]: v for v in VARIANTS}
    logger.info("V39b micro SUB rescue | %d | NO SUBMIT", len(VARIANTS))

    api = WqApiSimple()
    session = api.session
    ckpt = load_checkpoint()
    if ckpt:
        ckpt_results = list(ckpt.get("results") or [])
        found_alphas = list(ckpt.get("found_alphas") or [])
        done = {r.get("label") for r in ckpt_results if r.get("pid") or r.get("status") == "error"}
    else:
        ckpt_results, found_alphas, done = [], [], set()

    pending = [v for v in VARIANTS if v["label"] not in done]
    pl = ProgressLogger(total_steps=len(VARIANTS), log_path=PROGRESS_LOG_PATH, task_name="v39b_sub_micro", emit_interval_sec=15.0, max_recent=8)
    pl.start(meta={"dataset": DATASET, "variants": len(VARIANTS), "pending": len(pending), "no_submit": True, "goal": "SUB>=limit"})
    pl.done = len(done)

    survivors = []
    batches = chunked(pending, BATCH_SIZE)
    for bi, batch in enumerate(batches):
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        t0 = time.monotonic()
        logger.info("--- Batch %d/%d ---", bi + 1, len(batches))
        results = run_batch_multi(api, session, batch)
        wall = time.monotonic() - t0

        # 按 SUB gap 排序展示
        def gap(r):
            if r.get("sub_univ") is not None and r.get("sub_limit") is not None:
                return r["sub_univ"] - r["sub_limit"]
            return -999

        for r in sorted(results, key=gap, reverse=True)[:3]:
            if r.get("sharpe") is not None:
                logger.info(
                    "  %s S=%.3f sub=%s lim=%s gap=%s %s",
                    r.get("label"), r.get("sharpe") or 0, r.get("sub_univ"), r.get("sub_limit"),
                    f"{gap(r):+.3f}" if gap(r) > -100 else "?", r.get("status"),
                )

        for r in results:
            pl.step(extra={"label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"), "sharpe": r.get("sharpe"), "sub_univ": r.get("sub_univ"), "sub_limit": r.get("sub_limit"), "fails": r.get("fails"), "phase": 1, "batch_wall_sec": round(wall, 1)}, force_emit=True)
            ckpt_results.append({
                "label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"),
                "margin": r.get("margin"), "fails": r.get("fails") or [],
                "sub_univ": r.get("sub_univ"), "sub_limit": r.get("sub_limit"),
                "expr": r.get("expr") or (vmeta.get(r.get("label")) or {}).get("expr"),
                "settings": r.get("settings") or (vmeta.get(r.get("label")) or {}).get("settings"),
            })
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("*** cheap PASS %s ***", r.get("label"))
        save_checkpoint(ckpt_results, found_alphas)
        if bi + 1 < len(batches):
            time.sleep(BATCH_COOLDOWN_SEC)

    for r in survivors:
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        label, pid, expr, settings = r["label"], r["pid"], r["expr"], r["settings"]
        rn_ok, rn_stats = test_risk_neutralization(api, expr, settings)
        if not rn_ok:
            logger.info("[%s] risk-neut FAIL %s", label, rn_stats)
            continue
        robust = robust_overfit_test(api, expr, settings)
        if not robust.get("ok"):
            logger.info("[%s] robust FAIL", label)
            continue
        pc_val = wait_for_pc(api, pid)
        if pc_val is None or pc_val >= MAX_PROD_CORR:
            logger.warning("[%s] PC=%s 淘汰(不提交)", label, pc_val)
            continue
        info = {"dataset": DATASET, "label": label, "pid": pid, "expr": expr, "sharpe": r["sharpe"], "fitness": r["fitness"], "tvr": r["tvr"], "margin": r["margin"], "prod_corr": pc_val, "sub_univ": r.get("sub_univ"), "risk_neut": rn_stats, "robust": robust, "settings": settings, "submitted": False}
        set_alpha_props(api, pid, f"v39b_{label}", ["v39b", DATASET, "USA_D1", "READY_MANUAL", "NO_SUBMIT"])
        found_alphas.append(info)
        logger.info("*** FOUND %s S=%.3f PC=%.4f (NO SUBMIT) ***", pid, r["sharpe"], pc_val)
        save_checkpoint(ckpt_results, found_alphas)

    # 汇报最接近
    near = [r for r in ckpt_results if r.get("sub_univ") is not None and r.get("sub_limit") is not None]
    near.sort(key=lambda x: (x["sub_univ"] - x["sub_limit"]), reverse=True)
    if near:
        n0 = near[0]
        logger.info("Closest SUB: %s gap=%+.3f (%.3f/%.3f) S=%s", n0.get("label"), n0["sub_univ"] - n0["sub_limit"], n0["sub_univ"], n0["sub_limit"], n0.get("sharpe"))

    with open(FOUND_PATH, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done found=%d (never submitted)", len(found_alphas))
    pl.finish(summary={"found": len(found_alphas), "no_submit": True})


if __name__ == "__main__":
    main()
