#!/usr/bin/env python3
"""V38b: sustainable_profit 救援 — 抬 TVR 到 5%+，冲 S>1.58.

V38 近关: gp_net_op_assets / op_asset_turnover S~1.1 但 TVR~1.6%。
策略: 更短窗 ts_delta/ts_rank/ts_zscore + 更低 decay + ILLIQUID/TOP1000。
仍禁 add/multiply/trade_when；不提交。
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
BATCH_COOLDOWN_SEC = float(os.environ.get("V38B_COOLDOWN", "45"))
PROGRESS_LOG_PATH = os.environ.get(
    "PROGRESS_LOG_PATH",
    os.path.join(_HERE, "results", f"v38b_sust_rescue_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
)
CKPT_PATH = os.path.join(_HERE, "results", "v38b_sust_rescue_checkpoint.json")
FOUND_PATH = os.path.join(_HERE, "results", f"scan_v38b_sust_rescue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
DATASET = "sustainable_profit"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v38b")

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
DIVERSITY_EVERY = 10

# V38 近关字段（精简以控制批次数）
FIELDS = [
    "gross_profitability_net_operating_assets",
    "operating_asset_turnover_ratio",
    "cash_flow_return_on_noa",
]
PAIRS = [
    ("gross_profitability_net_operating_assets", "external_funding_of_noa", "gpoa_fund"),
    ("operating_asset_turnover_ratio", "external_funding_of_noa", "turn_fund"),
]
UNIVERSES = ["TOP3000", "ILLIQUID_MINVOL1M", "TOP1000"]
DECAYS = [0, 2, 4]


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


def base_settings(universe: str, decay: int, neut: str) -> Dict[str, Any]:
    return {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": universe,
        "delay": 1,
        "decay": decay,
        "neutralization": neut,
        "truncation": 0.08,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "ON",
        "language": "FASTEXPR",
        "visualization": False,
        "testPeriod": "P6Y",
        "maxTrade": "OFF",
    }


def build_variants() -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = []
    seen = set()

    def add(label, expr, universe, decay, neut, style, field):
        ops = count_operators(expr)
        if ops >= MAX_OPS or ops > 900:
            return
        key = (expr, universe, decay, neut)
        if key in seen:
            return
        seen.add(key)
        variants.append(
            {
                "label": label,
                "expr": expr,
                "settings": base_settings(universe, decay, neut),
                "style": style,
                "field": field,
                "ops": ops,
            }
        )

    for f in FIELDS:
        short = f.replace("gross_profitability_net_operating_assets", "gpoa").replace(
            "operating_asset_turnover_ratio", "oat"
        ).replace("cash_flow_return_on_noa", "cfo").replace("return_on_operating_assets", "roa").replace(
            "operating_return_on_invested_assets", "ori"
        ).replace("external_funding_of_noa", "fund")[:16]
        # 短窗抬 TVR
        for uni in UNIVERSES:
            for decay in DECAYS:
                add(f"d5_{short}_{uni}_d{decay}", f"rank(ts_delta(vec_avg({f}), 5))", uni, decay, "SUBINDUSTRY", "delta5", f)
                add(f"d22_{short}_{uni}_d{decay}", f"rank(ts_delta(vec_avg({f}), 22))", uni, decay, "SUBINDUSTRY", "delta22", f)
                add(f"tr66_{short}_{uni}_d{decay}", f"rank(ts_rank(vec_avg({f}), 66))", uni, decay, "SUBINDUSTRY", "ts_rank66", f)
                add(f"z22_{short}_{uni}_d{decay}", f"rank(ts_zscore(vec_avg({f}), 22))", uni, decay, "SUBINDUSTRY", "z22", f)
                add(f"z66_{short}_{uni}_d{decay}", f"rank(ts_zscore(vec_avg({f}), 66))", uni, decay, "INDUSTRY", "z66", f)
                add(f"nd5_{short}_{uni}_d{decay}", f"-rank(ts_delta(vec_avg({f}), 5))", uni, decay, "SUBINDUSTRY", "delta5_flip", f)
                add(f"ir22_{short}_{uni}_d{decay}", f"rank(ts_ir(vec_avg({f}), 22))", uni, decay, "SUBINDUSTRY", "ir22", f)
                add(f"gr_d22_{short}_{uni}_d{decay}", f"group_rank(ts_delta(vec_avg({f}), 22), industry)", uni, decay, "SUBINDUSTRY", "gr_delta", f)

    for a, b, tag in PAIRS:
        for uni in ["TOP3000", "ILLIQUID_MINVOL1M", "TOP1000"]:
            for decay in [0, 2, 4]:
                add(f"spd5_{tag}_{uni}_d{decay}", f"rank(ts_delta(subtract(vec_avg({a}), vec_avg({b})), 5))", uni, decay, "SUBINDUSTRY", "spread_d5", f"{a}|{b}")
                add(f"spz22_{tag}_{uni}_d{decay}", f"rank(ts_zscore(subtract(vec_avg({a}), vec_avg({b})), 22))", uni, decay, "SUBINDUSTRY", "spread_z22", f"{a}|{b}")
                add(f"nspz22_{tag}_{uni}_d{decay}", f"-rank(ts_zscore(subtract(vec_avg({a}), vec_avg({b})), 22))", uni, decay, "INDUSTRY", "spread_z22_flip", f"{a}|{b}")

    logger.info("Built %d variants (ops<%d)", len(variants), MAX_OPS)
    return variants


def diversity_report(results: List[Dict], variants_meta: Dict[str, Dict], round_n: int):
    recent = results[-80:] if len(results) > 80 else results
    styles, fields, ops_used = Counter(), Counter(), Counter()
    for r in recent:
        meta = variants_meta.get(r.get("label") or "", {})
        styles[meta.get("style", "?")] += 1
        fields[str(meta.get("field", "?"))[:40]] += 1
        expr = meta.get("expr") or r.get("expr") or ""
        for op in re.findall(r"[a-z_]+\(", expr.lower()):
            ops_used[op[:-1]] += 1
    sharpes = [_f(r.get("sharpe")) for r in recent if _f(r.get("sharpe")) is not None]
    tvrs = [_f(r.get("tvr")) for r in recent if _f(r.get("tvr")) is not None]
    best = max(sharpes) if sharpes else None
    tvr_ok = sum(1 for t in tvrs if t and 0.05 < t < 0.30)
    logger.info("=" * 60)
    logger.info("DIVERSITY @%d | best_S=%s | TVR_in_band=%d/%d", round_n, best, tvr_ok, len(tvrs))
    logger.info("  styles: %s", styles.most_common(6))
    logger.info("  fields: %s", fields.most_common(5))
    logger.info("  ops: %s", ops_used.most_common(8))
    logger.info("  救援目标: 短窗抬TVR; 保留gpoa/oat质量信号; 失效=换手虚高损S")
    logger.info("=" * 60)


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
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"results": results_list, "found_alphas": found_list}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CKPT_PATH)
    except Exception as e:
        logger.warning("save_checkpoint: %s", e)


def fetch_checks(api, pid, retries=5):
    for _ in range(retries):
        try:
            r = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if r.status_code == 200 and r.text.strip():
                checks = (r.json().get("is") or {}).get("checks") or []
                d = {c.get("name", ""): {"value": c.get("value"), "result": c.get("result", "")} for c in checks}
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
    settings = base_s.copy()
    settings["neutralization"] = "MARKET"
    try:
        res = api.run_backtest(expr, settings=settings)
        if res and res.get("platform_id"):
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s = _f(is_.get("sharpe")) or 0.0
            f = _f(is_.get("fitness")) or 0.0
            m = _f(is_.get("margin"))
            m_bp = m * 10000 if m else 0
            ok = s > GATE_RISK_NEUT_S and f > GATE_RISK_NEUT_F and m_bp > GATE_RISK_NEUT_M_BP
            return ok, {"s": s, "f": f, "m_bp": m_bp}
    except Exception as e:
        logger.warning("risk-neut: %s", e)
    return False, {}


def robust_overfit_test(api, expr, base_s) -> Dict[str, Any]:
    report = {"ok": True, "tests": []}
    probes = [
        ("decay+2", {**base_s, "decay": min(int(base_s.get("decay", 2)) + 2, 10)}),
        ("uni_TOP2000", {**base_s, "universe": "TOP2000"}),
        ("uni_ILLIQ", {**base_s, "universe": "ILLIQUID_MINVOL1M"}),
        ("trunc_0.05", {**base_s, "truncation": 0.05}),
    ]
    base_flip = expr[1:] if expr.startswith("-") else f"-{expr}"
    probes.append(("sign_flip", base_s))
    for name, settings in probes:
        try:
            e = base_flip if name == "sign_flip" else expr
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
    checks, plat_fails, fetch_ok = {}, [], True
    ladder_v, ladder_r = "?", "?"
    if not fails:
        checks, plat_fails, fetch_ok = fetch_checks(api, pid)
        ladder = checks.get("IS_LADDER_SHARPE") or checks.get("LOW_2Y_SHARPE") or {}
        ladder_v, ladder_r = ladder.get("value", "?"), ladder.get("result", "?")
        if not fetch_ok:
            return {
                "label": label, "pid": pid, "expr": expr, "settings": settings,
                "sharpe": s, "fitness": f, "tvr": tvr, "margin": m,
                "status": "CHECK_PENDING", "fails": ["check_api_pending"],
                "checks": checks, "failed_checks": [], "ladder": ladder_v, "ladder_result": ladder_r,
            }
        for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
            c = checks.get(name) or {}
            if c.get("result") == "FAIL":
                fails.append(f"{name}_FAIL")
            val = _f(c.get("value"))
            if val is not None and val <= GATE_2Y:
                fails.append(f"{name}={val:.3f}<=1.6")
        if plat_fails:
            fails.append("platform_FAIL")
    return {
        "label": label, "pid": pid, "expr": expr, "settings": settings,
        "sharpe": s, "fitness": f, "tvr": tvr, "margin": m,
        "status": "PASS_CHEAP" if not fails else "FAIL", "fails": fails,
        "checks": checks, "failed_checks": plat_fails, "ladder": ladder_v, "ladder_result": ladder_r,
    }


def run_batch_multi(api, session, batch):
    by_label = {b["label"]: b for b in batch}
    raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
    out = []
    for item in raw:
        label = item["label"]
        b = by_label.get(label)
        if not item.get("ok") or not item.get("pid") or not b:
            out.append({"label": label, "status": "error", "fails": [item.get("error") or "no_pid"]})
            continue
        out.append(evaluate_is(api, label, item["pid"], b["expr"], b["settings"]))
    return out


def main():
    VARIANTS = build_variants()
    vmeta = {v["label"]: v for v in VARIANTS}
    logger.info("V38b rescue %s | %d variants | NO SUBMIT", DATASET, len(VARIANTS))

    api = WqApiSimple()
    session = api.session
    ckpt = load_checkpoint()
    if ckpt:
        ckpt_results = list(ckpt.get("results") or [])
        found_alphas = list(ckpt.get("found_alphas") or [])
        done_labels = {r.get("label") for r in ckpt_results if r.get("pid") or r.get("status") == "error"}
    else:
        ckpt_results, found_alphas, done_labels = [], [], set()

    pending = [v for v in VARIANTS if v["label"] not in done_labels]
    by_style: Dict[str, List] = defaultdict(list)
    for v in pending:
        by_style[v["style"]].append(v)
    pending_sorted = []
    while any(by_style.values()):
        for st in list(by_style.keys()):
            if by_style[st]:
                pending_sorted.append(by_style[st].pop(0))
    pending = pending_sorted

    pl = ProgressLogger(total_steps=len(VARIANTS), log_path=PROGRESS_LOG_PATH, task_name="v38b_sust_rescue", emit_interval_sec=15.0, max_recent=8)
    pl.start(meta={"dataset": DATASET, "variants": len(VARIANTS), "pending": len(pending), "no_submit": True})
    pl.done = len(done_labels)

    survivors = []
    batch_count = 0
    batches = chunked(pending, BATCH_SIZE)
    for bi, batch in enumerate(batches):
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        t0 = time.monotonic()
        logger.info("--- Batch %d/%d | %d ---", bi + 1, len(batches), len(batch))
        results = run_batch_multi(api, session, batch)
        wall = time.monotonic() - t0
        batch_count += 1
        scored = sorted(results, key=lambda r: _f(r.get("sharpe")) or -999, reverse=True)
        for r in scored[:3]:
            if r.get("sharpe") is not None:
                logger.info(
                    "  top %s S=%.3f F=%.3f TVR=%.3f M=%.1fbp %s",
                    r.get("label"), r.get("sharpe") or 0, r.get("fitness") or 0,
                    r.get("tvr") or 0, (r.get("margin") or 0) * 10000, r.get("status"),
                )
        for r in results:
            label = r.get("label")
            pl.step(extra={"label": label, "pid": r.get("pid"), "status": r.get("status"), "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"), "margin": r.get("margin"), "fails": r.get("fails"), "phase": 1, "batch_wall_sec": round(wall, 1)}, force_emit=True)
            ckpt_results.append({"label": label, "pid": r.get("pid"), "status": r.get("status"), "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"), "margin": r.get("margin"), "fails": r.get("fails") or [], "expr": r.get("expr") or (vmeta.get(label) or {}).get("expr"), "style": (vmeta.get(label) or {}).get("style")})
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s] cheap PASS", label)
        save_checkpoint(ckpt_results, found_alphas)
        if batch_count % DIVERSITY_EVERY == 0:
            diversity_report(ckpt_results, vmeta, batch_count)
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
        info = {"dataset": DATASET, "label": label, "pid": pid, "expr": expr, "sharpe": r["sharpe"], "fitness": r["fitness"], "tvr": r["tvr"], "margin": r["margin"], "prod_corr": pc_val, "risk_neut": rn_stats, "robust": robust, "settings": settings, "submitted": False}
        set_alpha_props(api, pid, f"v38b_{label}", ["v38b", DATASET, "USA_D1", "READY_MANUAL", "NO_SUBMIT"])
        found_alphas.append(info)
        logger.info("*** FOUND %s S=%.3f PC=%.4f (NO SUBMIT) ***", pid, r["sharpe"], pc_val)
        save_checkpoint(ckpt_results, found_alphas)

    with open(FOUND_PATH, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done found=%d (never submitted)", len(found_alphas))
    pl.finish(summary={"found": len(found_alphas), "no_submit": True})


if __name__ == "__main__":
    main()
