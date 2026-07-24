#!/usr/bin/env python3
"""V40: USA D1 cre_exposure_model (未点亮 PM=1.5) — 真 multi-sim 8.

目标: 第2个不同数据集/风格 alpha (相对 insider_matrix).
字段仅2个 VECTOR: commercial/residential realty exposure beta.
硬规则同前: ops<6, 禁 add/multiply/trade_when, 不提交.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict
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
BATCH_COOLDOWN_SEC = float(os.environ.get("V40_COOLDOWN", "45"))
PROGRESS_LOG_PATH = os.path.join(_HERE, "results", f"v40_cre_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
CKPT_PATH = os.path.join(_HERE, "results", "v40_cre_checkpoint.json")
FOUND_PATH = os.path.join(_HERE, "results", f"scan_v40_cre_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
READY_PATH = os.path.join(_HERE, "results", "manual_submit_ready.json")
DATASET = "cre_exposure_model"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v40")

GATE_SHARPE, GATE_FITNESS, GATE_MARGIN_BP = 1.58, 1.0, 10.0
GATE_TVR_MIN, GATE_TVR_MAX, GATE_RETURNS, GATE_2Y = 0.05, 0.30, 0.05, 1.6
GATE_RISK_NEUT_S, GATE_RISK_NEUT_F, GATE_RISK_NEUT_M_BP = 1.0, 0.7, 10.0
MAX_PROD_CORR, MAX_OPS, TARGET_ALPHAS = 0.70, 6, 1

A, B = "commercial_realty_exposure_beta", "residential_realty_exposure_beta"
FIELDS = [A, B]
UNIVERSES = ["TOP3000", "TOP2000", "ILLIQUID_MINVOL1M", "TOP1000"]
DECAYS = [2, 3, 5, 8]
NEUTS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR"]
TRUNCS = [0.01, 0.05, 0.08]


def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def count_operators(expr: str) -> int:
    low = expr.lower().replace(" ", "")
    if "trade_when(" in low or "add(" in low or "multiply(" in low:
        return 999
    if "*" in expr or re.search(r"(?<![eE])\+", expr):
        return 999
    return len(re.findall(r"[a-z_]+\(", expr.lower()))


def base_settings(universe, decay, neut, trunc=0.08):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe, "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "ON", "language": "FASTEXPR",
        "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
    }


def build_variants():
    variants, seen = [], set()

    def add(label, expr, uni, decay, neut, style, field, trunc=0.08):
        ops = count_operators(expr)
        if ops >= MAX_OPS or ops > 900:
            return
        key = (expr, uni, decay, neut, trunc)
        if key in seen:
            return
        seen.add(key)
        variants.append({"label": label, "expr": expr, "settings": base_settings(uni, decay, neut, trunc), "style": style, "field": field, "ops": ops})

    for f, tag in [(A, "com"), (B, "res")]:
        for uni in UNIVERSES:
            for decay in DECAYS:
                for neut in NEUTS:
                    add(f"z_{tag}_{uni}_d{decay}_{neut[:3]}", f"rank(ts_zscore(ts_mean(vec_avg({f}), 22), 126))", uni, decay, neut, "zscore", f)
                    add(f"nz_{tag}_{uni}_d{decay}_{neut[:3]}", f"-rank(ts_zscore(ts_mean(vec_avg({f}), 22), 126))", uni, decay, neut, "zscore_flip", f)
                    add(f"gz_{tag}_{uni}_d{decay}_{neut[:3]}", f"group_zscore(ts_zscore(ts_mean(vec_avg({f}), 22), 126), industry)", uni, decay, neut, "group_z", f)
                    add(f"raw_{tag}_{uni}_d{decay}_{neut[:3]}", f"rank(vec_avg({f}))", uni, decay, neut, "raw", f)
                    add(f"d_{tag}_{uni}_d{decay}_{neut[:3]}", f"rank(ts_delta(vec_avg({f}), 22))", uni, decay, neut, "delta", f)
                    add(f"tr_{tag}_{uni}_d{decay}_{neut[:3]}", f"rank(ts_rank(vec_avg({f}), 126))", uni, decay, neut, "ts_rank", f)

    # 核心经济意义: 商业 vs 住宅地产暴露差
    for uni in UNIVERSES:
        for decay in DECAYS:
            for neut in NEUTS:
                for trunc in TRUNCS:
                    add(f"sp_cr_{uni}_d{decay}_{neut[:3]}_t{int(trunc*100)}", f"rank(ts_zscore(subtract(vec_avg({A}), vec_avg({B})), 126))", uni, decay, neut, "cre_spread", f"{A}|{B}", trunc)
                    add(f"nsp_cr_{uni}_d{decay}_{neut[:3]}_t{int(trunc*100)}", f"-rank(ts_zscore(subtract(vec_avg({A}), vec_avg({B})), 126))", uni, decay, neut, "cre_spread_flip", f"{A}|{B}", trunc)
                    add(f"spgz_cr_{uni}_d{decay}_{neut[:3]}_t{int(trunc*100)}", f"group_zscore(ts_zscore(subtract(vec_avg({A}), vec_avg({B})), 189), industry)", uni, decay, neut, "cre_spread_gz", f"{A}|{B}", trunc)
                    add(f"spgr_cr_{uni}_d{decay}_{neut[:3]}_t{int(trunc*100)}", f"group_rank(ts_mean(subtract(vec_avg({A}), vec_avg({B})), 22), industry)", uni, decay, neut, "cre_spread_gr", f"{A}|{B}", trunc)

    logger.info("Built %d variants", len(variants))
    return variants


def load_checkpoint():
    if not os.path.exists(CKPT_PATH):
        return None
    try:
        return json.load(open(CKPT_PATH, encoding="utf-8"))
    except Exception:
        return None


def save_checkpoint(results_list, found_list):
    tmp = CKPT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"results": results_list, "found_alphas": found_list}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CKPT_PATH)


def append_ready(info):
    try:
        ready = json.load(open(READY_PATH, encoding="utf-8")) if os.path.exists(READY_PATH) else {"goal": 10, "alphas": []}
        info = dict(info)
        info["n"] = len(ready.get("alphas", [])) + 1
        ready.setdefault("alphas", []).append(info)
        with open(READY_PATH, "w", encoding="utf-8") as f:
            json.dump(ready, f, ensure_ascii=False, indent=2)
        logger.info("Appended to %s (%d/10)", READY_PATH, len(ready["alphas"]))
    except Exception as e:
        logger.warning("append_ready: %s", e)


def fetch_checks(api, pid, retries=5):
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
            s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            m = _f(is_.get("margin"))
            m_bp = m * 10000 if m else 0
            return s > GATE_RISK_NEUT_S and f > GATE_RISK_NEUT_F and m_bp > GATE_RISK_NEUT_M_BP, {"s": s, "f": f, "m_bp": m_bp}
    except Exception as e:
        logger.warning("risk-neut: %s", e)
    return False, {}


def robust_overfit_test(api, expr, base_s):
    report = {"ok": True, "tests": []}
    probes = [("decay+2", {**base_s, "decay": min(int(base_s.get("decay", 3)) + 2, 10)}), ("uni_TOP2000", {**base_s, "universe": "TOP2000"}), ("sign_flip", base_s)]
    flip = expr[1:] if expr.startswith("-") else f"-{expr}"
    for name, settings in probes:
        try:
            e = flip if name == "sign_flip" else expr
            res = api.run_backtest(e, settings=settings)
            if not res or not res.get("platform_id"):
                report["ok"] = False
                continue
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            ok = abs(s) > 0.8 if name == "sign_flip" else (s > 0.9 and f > 0.5)
            report["tests"].append({"name": name, "sharpe": s, "fitness": f})
            if not ok:
                report["ok"] = False
            time.sleep(2)
        except Exception:
            report["ok"] = False
    return report


def set_alpha_props(api, pid, name, tags):
    try:
        r = api.session.patch(f"{API_BASE}/alphas/{pid}", json={"color": "GREEN", "name": name[:80], "tags": tags, "regular": {"description": name[:200]}}, timeout=60)
        logger.info("set_props %s -> %s (NO SUBMIT)", pid, r.status_code)
        return r.ok
    except Exception as e:
        logger.warning("set_props: %s", e)
        return False


def evaluate_is(api, label, pid, expr, settings):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m, ret = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0, _f(is_.get("returns")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_SHARPE: fails.append(f"S={s:.3f}")
    if f <= GATE_FITNESS: fails.append(f"F={f:.3f}")
    if tvr <= GATE_TVR_MIN or tvr >= GATE_TVR_MAX: fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_MARGIN_BP: fails.append(f"M={m_bp:.1f}bp")
    if ret <= GATE_RETURNS: fails.append(f"Ret={ret:.4f}")
    checks, plat_fails = {}, []
    if not fails:
        checks, plat_fails, ok = fetch_checks(api, pid)
        if not ok:
            return {"label": label, "pid": pid, "expr": expr, "settings": settings, "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "status": "CHECK_PENDING", "fails": ["check_pending"]}
        for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
            c = checks.get(name) or {}
            if c.get("result") == "FAIL": fails.append(f"{name}_FAIL")
            val = _f(c.get("value"))
            if val is not None and val <= GATE_2Y: fails.append(f"{name}={val:.3f}<=1.6")
        if plat_fails: fails.extend([f"PF:{x}" for x in plat_fails])
    return {"label": label, "pid": pid, "expr": expr, "settings": settings, "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "status": "PASS_CHEAP" if not fails else "FAIL", "fails": fails, "checks": checks, "failed_checks": plat_fails}


def run_batch_multi(api, session, batch):
    by = {b["label"]: b for b in batch}
    raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
    out = []
    for item in raw:
        b = by.get(item["label"])
        if not item.get("ok") or not item.get("pid") or not b:
            out.append({"label": item["label"], "status": "error", "fails": [item.get("error") or "no_pid"]})
        else:
            out.append(evaluate_is(api, item["label"], item["pid"], b["expr"], b["settings"]))
    return out


def main():
    VARIANTS = build_variants()
    if len(VARIANTS) > 200:
        # 优先 spread 风格
        VARIANTS = sorted(VARIANTS, key=lambda v: (0 if "spread" in v["style"] else 1, v["label"]))[:200]
        logger.info("Trimmed to 200 priority variants")
    vmeta = {v["label"]: v for v in VARIANTS}
    logger.info("V40 %s | %d | NO SUBMIT", DATASET, len(VARIANTS))

    api = WqApiSimple()
    session = api.session
    ckpt = load_checkpoint()
    if ckpt:
        ckpt_results, found_alphas = list(ckpt.get("results") or []), list(ckpt.get("found_alphas") or [])
        done = {r.get("label") for r in ckpt_results if r.get("pid") or r.get("status") == "error"}
    else:
        ckpt_results, found_alphas, done = [], [], set()

    pending = [v for v in VARIANTS if v["label"] not in done]
    pl = ProgressLogger(total_steps=len(VARIANTS), log_path=PROGRESS_LOG_PATH, task_name="v40_cre", emit_interval_sec=15.0, max_recent=8)
    pl.start(meta={"dataset": DATASET, "variants": len(VARIANTS), "pending": len(pending), "no_submit": True})
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
        for r in sorted(results, key=lambda x: _f(x.get("sharpe")) or -999, reverse=True)[:3]:
            if r.get("sharpe") is not None:
                logger.info("  top %s S=%.3f F=%.3f TVR=%.3f %s", r.get("label"), r.get("sharpe") or 0, r.get("fitness") or 0, r.get("tvr") or 0, r.get("status"))
        for r in results:
            pl.step(extra={"label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"), "sharpe": r.get("sharpe"), "fails": r.get("fails"), "phase": 1, "batch_wall_sec": round(wall, 1)}, force_emit=True)
            ckpt_results.append({"label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"), "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"), "margin": r.get("margin"), "fails": r.get("fails") or [], "expr": r.get("expr") or (vmeta.get(r.get("label")) or {}).get("expr"), "style": (vmeta.get(r.get("label")) or {}).get("style"), "settings": r.get("settings")})
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s] cheap PASS", r.get("label"))
        save_checkpoint(ckpt_results, found_alphas)
        if (bi + 1) % 10 == 0:
            ss = [_f(x.get("sharpe")) for x in ckpt_results if _f(x.get("sharpe")) is not None]
            logger.info("DIVERSITY @%d best_S=%s styles=%s", bi + 1, max(ss) if ss else None, Counter((vmeta.get(x.get("label")) or {}).get("style") for x in ckpt_results[-80:]).most_common(5))
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
        info = {"dataset": DATASET, "style": "cre_realty_spread", "pid": pid, "label": label, "expr": expr, "sharpe": r["sharpe"], "fitness": r["fitness"], "tvr": r["tvr"], "margin": r["margin"], "prod_corr": pc_val, "risk_neut": rn_stats, "robust": robust, "settings": settings, "submitted": False}
        set_alpha_props(api, pid, f"v40_{label}", ["v40", DATASET, "USA_D1", "READY_MANUAL", "NO_SUBMIT"])
        found_alphas.append(info)
        append_ready({**info, "margin_bp": (r["margin"] or 0) * 10000, "tags": ["v40", DATASET, "USA_D1", "READY_MANUAL"]})
        logger.info("*** FOUND %s S=%.3f PC=%.4f (NO SUBMIT) ***", pid, r["sharpe"], pc_val)
        save_checkpoint(ckpt_results, found_alphas)

    with open(FOUND_PATH, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done found=%d (never submitted)", len(found_alphas))
    pl.finish(summary={"found": len(found_alphas), "no_submit": True})


if __name__ == "__main__":
    main()
