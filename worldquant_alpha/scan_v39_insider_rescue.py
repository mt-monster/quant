#!/usr/bin/env python3
"""V39: USA insider_matrix 救援 — 攻克 LOW_SUB_UNIVERSE_SHARPE.

V34 近关 (无 add/multiply):
  ind_momentum eur_aggregated_value_1: S=1.95 F=1.36 TVR=10.7% 2y=1.98
  唯一硬 FAIL: LOW_SUB_UNIVERSE_SHARPE (~0.05)

策略: 同字段同骨架, 扫 universe/truncation/decay/neut/winsorize/group_rank
以抬升 sub-universe sharpe; 禁 trade_when/add/multiply/+/*; 不提交。
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
BATCH_COOLDOWN_SEC = float(os.environ.get("V39_COOLDOWN", "45"))
PROGRESS_LOG_PATH = os.environ.get(
    "PROGRESS_LOG_PATH",
    os.path.join(_HERE, "results", f"v39_insider_rescue_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
)
CKPT_PATH = os.path.join(_HERE, "results", "v39_insider_rescue_checkpoint.json")
FOUND_PATH = os.path.join(_HERE, "results", f"scan_v39_insider_rescue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
DATASET = "insider_matrix"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v39")

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

FIELDS = [
    "eur_aggregated_value_1",
    "eur_aggregated_value_2",
    "eur_aggregated_value_3",
    "eur_aggregated_value_4",
    "eur_top_value_1",
    "eur_director_value_1",
    "director_intensity_score",
]
UNIVERSES = ["TOP3000", "TOP2000", "TOP1000", "ILLIQUID_MINVOL1M"]
DECAYS = [2, 3, 4, 5, 6]
NEUTS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR"]
TRUNCS = [0.05, 0.08, 0.01, 0.1]


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


def base_settings(universe: str, decay: int, neut: str, trunc: float = 0.08) -> Dict[str, Any]:
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
    variants: List[Dict[str, Any]] = []
    seen = set()

    def add(label, expr, universe, decay, neut, style, field, trunc=0.08):
        ops = count_operators(expr)
        if ops >= MAX_OPS or ops > 900:
            return
        key = (expr, universe, decay, neut, trunc)
        if key in seen:
            return
        seen.add(key)
        variants.append(
            {
                "label": label,
                "expr": expr,
                "settings": base_settings(universe, decay, neut, trunc),
                "style": style,
                "field": field,
                "ops": ops,
            }
        )

    # 核心骨架: V34 赢家 ind_momentum / momentum (无 +/*)
    for f in FIELDS:
        short = f.replace("eur_", "").replace("aggregated_value_", "agg").replace("director_value_", "dir").replace("top_value_", "top").replace("director_intensity_score", "dis")[:14]
        for uni in UNIVERSES:
            for decay in DECAYS:
                for neut in NEUTS:
                    for trunc in TRUNCS:
                        # 原始赢家
                        add(
                            f"indmom_{short}_{uni}_d{decay}_{neut[:3]}_t{int(trunc*100)}",
                            f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))",
                            uni, decay, neut, "ind_momentum", f, trunc,
                        )
                        add(
                            f"mom_{short}_{uni}_d{decay}_{neut[:3]}_t{int(trunc*100)}",
                            f"rank(ts_zscore(ts_backfill({f}, 66), 189))",
                            uni, decay, neut, "momentum", f, trunc,
                        )
        # 子宇宙友好变体 (更少行业偏置 / winsor / sector group)
        for uni in ["TOP3000", "TOP2000", "ILLIQUID_MINVOL1M"]:
            for decay in [3, 4, 5]:
                add(f"gzsec_{short}_{uni}_d{decay}", f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), sector))", uni, decay, "SECTOR", "gz_sector", f, 0.08)
                add(f"gr_{short}_{uni}_d{decay}", f"group_rank(ts_zscore(ts_backfill({f}, 66), 189), industry)", uni, decay, "SUBINDUSTRY", "group_rank", f, 0.05)
                add(f"wz_{short}_{uni}_d{decay}", f"rank(winsorize(ts_zscore(ts_backfill({f}, 66), 189), std=3))", uni, decay, "SUBINDUSTRY", "winsor_z", f, 0.05)
                add(f"tr_{short}_{uni}_d{decay}", f"rank(ts_rank(ts_backfill({f}, 66), 252))", uni, decay, "SUBINDUSTRY", "ts_rank", f, 0.08)
                add(f"nz_indmom_{short}_{uni}_d{decay}", f"-rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))", uni, decay, "SUBINDUSTRY", "ind_flip", f, 0.08)

    logger.info("Built %d variants (ops<%d)", len(variants), MAX_OPS)
    return variants


def diversity_report(results, variants_meta, round_n):
    recent = results[-80:] if len(results) > 80 else results
    styles, fields = Counter(), Counter()
    for r in recent:
        meta = variants_meta.get(r.get("label") or "", {})
        styles[meta.get("style", "?")] += 1
        fields[str(meta.get("field", "?"))[:36]] += 1
    sharpes = [_f(r.get("sharpe")) for r in recent if _f(r.get("sharpe")) is not None]
    sub_ok = sum(1 for r in recent if "LOW_SUB_UNIVERSE" not in str(r.get("fails")) and (_f(r.get("sharpe")) or 0) > 1.5)
    logger.info("=" * 60)
    logger.info("DIVERSITY @%d | best_S=%s | near_no_subfail~%d", round_n, max(sharpes) if sharpes else None, sub_ok)
    logger.info("  styles: %s", styles.most_common(6))
    logger.info("  fields: %s", fields.most_common(5))
    logger.info("  目标: 过 LOW_SUB_UNIVERSE; 保留 insider 动量; 失效=截断过猛损IS")
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
        logger.warning("ckpt: %s", e)


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
        ("decay+2", {**base_s, "decay": min(int(base_s.get("decay", 3)) + 2, 10)}),
        ("uni_TOP2000", {**base_s, "universe": "TOP2000"}),
        ("trunc_0.05", {**base_s, "truncation": 0.05}),
        ("sign_flip", base_s),
    ]
    base_flip = expr[1:] if expr.startswith("-") else f"-{expr}"
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
    ladder_v, ladder_r, sub_v = "?", "?", None
    # 近关也拉 check, 便于看 SUB_UNIVERSE
    if s > 1.2:
        checks, plat_fails, fetch_ok = fetch_checks(api, pid)
        ladder = checks.get("IS_LADDER_SHARPE") or checks.get("LOW_2Y_SHARPE") or {}
        ladder_v, ladder_r = ladder.get("value", "?"), ladder.get("result", "?")
        sub = checks.get("LOW_SUB_UNIVERSE_SHARPE") or {}
        sub_v = _f(sub.get("value"))
        if not fails:
            if not fetch_ok:
                return {
                    "label": label, "pid": pid, "expr": expr, "settings": settings,
                    "sharpe": s, "fitness": f, "tvr": tvr, "margin": m,
                    "status": "CHECK_PENDING", "fails": ["check_api_pending"],
                    "checks": checks, "failed_checks": [], "ladder": ladder_v, "ladder_result": ladder_r, "sub_univ": sub_v,
                }
            for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
                c = checks.get(name) or {}
                if c.get("result") == "FAIL":
                    fails.append(f"{name}_FAIL")
                val = _f(c.get("value"))
                if val is not None and val <= GATE_2Y:
                    fails.append(f"{name}={val:.3f}<=1.6")
            if plat_fails:
                fails.extend([f"PF:{x}" for x in plat_fails])

    return {
        "label": label, "pid": pid, "expr": expr, "settings": settings,
        "sharpe": s, "fitness": f, "tvr": tvr, "margin": m,
        "status": "PASS_CHEAP" if not fails else "FAIL", "fails": fails,
        "checks": checks, "failed_checks": plat_fails, "ladder": ladder_v, "ladder_result": ladder_r, "sub_univ": sub_v,
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
    # 优先跑 V34 赢家附近: eur_aggregated_value_1/2 + TOP3000/TOP2000 + SUBINDUSTRY
    def prio(v):
        score = 0
        if "agg1" in v["label"] or "agg2" in v["label"] or "value_1" in str(v["field"]) or "value_2" in str(v["field"]):
            score += 10
        if v["settings"]["universe"] in ("TOP3000", "TOP2000"):
            score += 5
        if v["style"] in ("ind_momentum", "momentum"):
            score += 3
        if v["settings"]["decay"] in (3, 4):
            score += 2
        return -score

    VARIANTS.sort(key=prio)
    # 控制规模: 先跑前 240 个高优先
    if len(VARIANTS) > 240:
        logger.info("Trim %d -> 240 priority variants", len(VARIANTS))
        VARIANTS = VARIANTS[:240]

    vmeta = {v["label"]: v for v in VARIANTS}
    logger.info("V39 insider_matrix rescue | %d variants | NO SUBMIT", len(VARIANTS))

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
    pl = ProgressLogger(total_steps=len(VARIANTS), log_path=PROGRESS_LOG_PATH, task_name="v39_insider_rescue", emit_interval_sec=15.0, max_recent=8)
    pl.start(meta={"dataset": DATASET, "variants": len(VARIANTS), "pending": len(pending), "no_submit": True, "goal": "fix_SUB_UNIVERSE"})
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
                    "  top %s S=%.3f F=%.3f TVR=%.3f sub=%s fails=%s",
                    r.get("label"), r.get("sharpe") or 0, r.get("fitness") or 0,
                    r.get("tvr") or 0, r.get("sub_univ"), r.get("fails"),
                )

        for r in results:
            label = r.get("label")
            pl.step(extra={"label": label, "pid": r.get("pid"), "status": r.get("status"), "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"), "margin": r.get("margin"), "fails": r.get("fails"), "sub_univ": r.get("sub_univ"), "phase": 1, "batch_wall_sec": round(wall, 1)}, force_emit=True)
            ckpt_results.append({
                "label": label, "pid": r.get("pid"), "status": r.get("status"),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"),
                "margin": r.get("margin"), "fails": r.get("fails") or [],
                "sub_univ": r.get("sub_univ"),
                "expr": r.get("expr") or (vmeta.get(label) or {}).get("expr"),
                "style": (vmeta.get(label) or {}).get("style"),
                "settings": r.get("settings") or (vmeta.get(label) or {}).get("settings"),
            })
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s] cheap PASS (incl platform) -> Phase2", label)
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
        info = {
            "dataset": DATASET, "label": label, "pid": pid, "expr": expr,
            "sharpe": r["sharpe"], "fitness": r["fitness"], "tvr": r["tvr"], "margin": r["margin"],
            "prod_corr": pc_val, "risk_neut": rn_stats, "robust": robust,
            "settings": settings, "submitted": False,
        }
        set_alpha_props(api, pid, f"v39_{label}", ["v39", DATASET, "USA_D1", "READY_MANUAL", "NO_SUBMIT"])
        found_alphas.append(info)
        logger.info("*** FOUND %s S=%.3f PC=%.4f (NO SUBMIT) ***", pid, r["sharpe"], pc_val)
        save_checkpoint(ckpt_results, found_alphas)

    with open(FOUND_PATH, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done found=%d (never submitted)", len(found_alphas))
    pl.finish(summary={"found": len(found_alphas), "no_submit": True})


if __name__ == "__main__":
    main()
