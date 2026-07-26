#!/usr/bin/env python3
"""通用三轨挖掘 worker — 多进程共享 submit_gate，错峰占满令牌桶。

用法:
  python scan_tri_job.py --job v47
  python scan_tri_job.py --job v48
  python scan_tri_job.py --job v49

约束: ops<6; 禁 add/multiply/trade_when; 绝不提交 alpha; 相关 vs YPgAa3WR <0.4
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, after_batch_cooldown, envelope_summary, run_multi_batch
from progress_logger import ProgressLogger
from tri_track import (
    SLOT_EXPLORE,
    SLOT_IMPROVE,
    SLOT_RESCUE,
    build_improve_variants,
    build_rescue_variants,
    mix_batch,
    refill_queues_from_results,
)
from wd_lib_wrapper import WqApiSimple

KNOWN_PID = "YPgAa3WR"
READY_PATH = os.path.join(_HERE, "results", "manual_submit_ready.json")

GATE_SHARPE, GATE_FITNESS, GATE_MARGIN_BP = 1.58, 1.0, 10.0
GATE_TVR_MIN, GATE_TVR_MAX, GATE_RETURNS, GATE_2Y = 0.05, 0.30, 0.05, 1.6
GATE_RISK_NEUT_S, GATE_RISK_NEUT_F, GATE_RISK_NEUT_M_BP = 1.0, 0.7, 10.0
MAX_PROD_CORR, MAX_OPS, TARGET_ALPHAS = 0.70, 6, 1
MAX_PAIR_CORR = 0.40
BATCH_SIZE = 8

# kind: matrix | vector
JOBS: Dict[str, Dict[str, Any]] = {
    "v47": {
        "dataset": "search_interest",
        "style": "search_attention",
        "kind": "vector",
        "fields": [
            "relative_interest_score",
            "relative_interest_score_3_fast_d1",
            "relative_interest_score_4",
            "relative_interest_score_2",
            "trend_confidence_overlap_months",
            "trend_confidence_overlap_months_2_fast_d1",
        ],
        "pairs": [
            ("relative_interest_score_3_fast_d1", "relative_interest_score", "ris3_vs_ris"),
            ("relative_interest_score_4", "relative_interest_score_2", "ris4_vs_ris2"),
        ],
    },
    "v48": {
        "dataset": "acquisition_model",
        "style": "ma_likelihood",
        "kind": "vector",
        "fields": [
            "global_percentile_acquisition_likelihood",
            "industry_percentile_acquisition_likelihood",
            "country_percentile_acquisition_likelihood",
            "global_valuation_percentile_rank",
            "global_fundamental_factor_percentile_rank",
            "global_credit_quality_percentile_rank",
            "global_text_factor_percentile_rank",
            "global_company_size_percentile_rank",
        ],
        "pairs": [
            ("global_percentile_acquisition_likelihood", "industry_percentile_acquisition_likelihood", "glob_vs_ind"),
            ("global_valuation_percentile_rank", "global_fundamental_factor_percentile_rank", "val_vs_fund"),
        ],
    },
    "v49": {
        "dataset": "forward_beta_risk",
        "style": "forward_beta",
        "kind": "matrix",
        "fields": [
            "beta_prediction_uncertainty",
            "beta_prediction_dispersion",
            "beta_lower_confidence_band",
            "beta_prediction_uncertainty_fast_d1",
            "beta_prediction_dispersion_fast_d1",
            "beta_lower_confidence_band_fast_d1",
        ],
        "pairs": [
            ("beta_prediction_uncertainty", "beta_prediction_dispersion", "unc_vs_disp"),
            ("beta_lower_confidence_band", "beta_prediction_uncertainty", "band_vs_unc"),
        ],
    },
    "v50": {
        "dataset": "board_network",
        "style": "board_centrality",
        "kind": "matrix",
        "fields": [
            "network_authority_centrality_metric",
            "network_betweenness_centrality_metric",
            "mean_connection_significance_score",
            "mean_connection_significance_weighted_by_market_value",
            "count_connected_companies",
            "count_external_board_connections",
            "mean_connected_company_market_value",
            "board_member_count",
        ],
        "pairs": [
            ("network_authority_centrality_metric", "network_betweenness_centrality_metric", "auth_vs_bet"),
            ("mean_connection_significance_score", "count_connected_companies", "sig_vs_cnt"),
        ],
    },
    "v51": {
        "dataset": "behavioral_signals",
        "style": "price_path_behavior",
        "kind": "vector",
        "fields": [
            "salience_weighted_return_score",
            "visual_price_path_shape_score",
            "price_path_curvature_measure",
            "chronological_return_sequence_correlation",
            "consecutive_return_streak_length",
            "extreme_daily_return_indicator",
        ],
        "pairs": [
            ("salience_weighted_return_score", "visual_price_path_shape_score", "sal_vs_shape"),
            ("price_path_curvature_measure", "chronological_return_sequence_correlation", "curv_vs_corr"),
        ],
    },
    "v52": {
        "dataset": "hiring_trends",
        "style": "hiring_momentum",
        "kind": "vector",
        "fields": [
            "aggregate_open_positions_count",
            "fresh_open_positions_count",
            "rolling_84d_new_positions_sum",
        ],
        "pairs": [
            ("fresh_open_positions_count", "aggregate_open_positions_count", "fresh_vs_agg"),
            ("rolling_84d_new_positions_sum", "aggregate_open_positions_count", "roll_vs_agg"),
        ],
    },
    "v53": {
        "dataset": "stock_search_trends",
        "style": "search_trend_matrix",
        "kind": "matrix",
        "fields": [
            "search_interest_7d_corporate_name",
            "search_interest_14d_corporate_name",
            "search_interest_28d_corporate_name",
            "search_interest_1y_corporate_name",
            "search_interest_7d_equity_symbol",
            "search_interest_14d_equity_symbol",
            "search_interest_28d_equity_symbol",
        ],
        "pairs": [
            ("search_interest_7d_corporate_name", "search_interest_1y_corporate_name", "7d_vs_1y"),
            ("search_interest_14d_corporate_name", "search_interest_14d_equity_symbol", "name_vs_sym"),
        ],
    },
    "v54": {
        "dataset": "event_stock_model",
        "style": "corp_event_score",
        "kind": "vector",
        "fields": [
            "corporate_structure_event_score_2",
            "earnings_financial_event_score_2",
            "corporate_structure_event_score",
            "earnings_financial_event_score",
            "company_total_market_value_3",
            "total_equity_market_value",
        ],
        "pairs": [
            ("corporate_structure_event_score_2", "earnings_financial_event_score_2", "struct_vs_earn"),
            ("corporate_structure_event_score", "earnings_financial_event_score", "struct_vs_earn1"),
        ],
    },
}


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


def base_settings(universe, decay, neut, trunc=0.01):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe, "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "ON", "language": "FASTEXPR",
        "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
    }


def _vkey(v: Dict[str, Any]) -> Tuple:
    s = v.get("settings") or {}
    return (v.get("expr"), s.get("universe"), s.get("decay"), s.get("neutralization"), s.get("truncation"))


def _wrap(field: str, kind: str) -> str:
    return f"vec_avg({field})" if kind == "vector" else field


def build_explore(job: Dict[str, Any], logger) -> List[Dict[str, Any]]:
    kind = job["kind"]
    variants, seen = [], set()

    def add(label, expr, uni, decay, neut, style, field, trunc=0.01):
        ops = count_operators(expr)
        if ops >= MAX_OPS or ops > 900:
            return
        item = {
            "label": label, "expr": expr, "settings": base_settings(uni, decay, neut, trunc),
            "style": style, "field": field, "ops": ops, "track": "explore",
        }
        k = _vkey(item)
        if k in seen:
            return
        seen.add(k)
        variants.append(item)

    for f in job["fields"]:
        x = _wrap(f, kind)
        short = re.sub(r"[^a-z0-9]+", "_", f)[:16]
        for uni in ("TOP3000", "ILLIQUID_MINVOL1M"):
            for decay in (2, 3, 4):
                for neut in ("SECTOR", "INDUSTRY"):
                    add(f"ex_bf_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_backfill({x}, 66), 189), industry))",
                        uni, decay, neut, "v39_bf", f)
                    add(f"ex_bfz_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(ts_backfill({x}, 66), 189))",
                        uni, decay, neut, "bf_z", f)
                    add(f"ex_gz_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_mean({x}, 22), 189), industry))",
                        uni, decay, neut, "gz_mean", f)
                    if decay == 3 and neut == "SECTOR":
                        add(f"ex_flip_{short}_{uni}_d{decay}_{neut[:3]}",
                            f"-rank(group_zscore(ts_zscore(ts_backfill({x}, 66), 189), industry))",
                            uni, decay, neut, "v39_flip", f)
                        add(f"ex_tr_{short}_{uni}_d{decay}_{neut[:3]}",
                            f"rank(ts_rank(ts_backfill({x}, 66), 126))",
                            uni, decay, neut, "ts_rank", f)

    for a, b, tag in job.get("pairs") or []:
        xa, xb = _wrap(a, kind), _wrap(b, kind)
        for uni in ("TOP3000",):
            for decay in (2, 3):
                for neut in ("SECTOR", "INDUSTRY"):
                    add(f"ex_sp_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(subtract(ts_backfill({xa}, 66), ts_backfill({xb}, 66)), 189))",
                        uni, decay, neut, "spread", f"{a}|{b}")
                    add(f"ex_spgz_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(subtract({xa}, {xb}), 189), industry))",
                        uni, decay, neut, "spread_gz", f"{a}|{b}")

    logger.info("explore pool: %d", len(variants))
    return variants


def seed_templates(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    kind = job["kind"]
    seeds = []
    for f in job["fields"][:5]:
        x = _wrap(f, kind)
        seeds.append({
            "label": f"seed_{f[:18]}",
            "expr": f"rank(group_zscore(ts_zscore(ts_backfill({x}, 66), 189), industry))",
            "settings": base_settings("TOP3000", 3, "SECTOR", 0.01),
            "sharpe": 0.5,
            "field": f,
        })
    return seeds


def append_ready(info):
    try:
        ready = json.load(open(READY_PATH, encoding="utf-8")) if os.path.exists(READY_PATH) else {"goal": 10, "alphas": []}
        info = dict(info)
        info["n"] = len(ready.get("alphas", [])) + 1
        ready.setdefault("alphas", []).append(info)
        with open(READY_PATH, "w", encoding="utf-8") as f:
            json.dump(ready, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.getLogger("tri_job").warning("append_ready: %s", e)


def fetch_checks(api, pid, retries=5):
    for _ in range(retries):
        try:
            r = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if r.status_code == 200 and r.text.strip():
                checks = (r.json().get("is") or {}).get("checks") or []
                return {c.get("name", ""): c for c in checks}, [c.get("name") for c in checks if c.get("result") == "FAIL"], True
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


def check_corr_vs_known(api, pid):
    if getattr(api, "local_sc", None) is not None:
        try:
            c = api.local_sc.corr_pair(pid, KNOWN_PID)
            return (c is not None and abs(c) < MAX_PAIR_CORR), c
        except Exception:
            pass
    return True, "pending"


def test_risk_neutralization(api, expr, base_s):
    settings = {**base_s, "neutralization": "MARKET"}
    try:
        res = api.run_backtest(expr, settings=settings)
        if res and res.get("platform_id"):
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s, fit = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            m = _f(is_.get("margin"))
            m_bp = m * 10000 if m else 0
            return s > GATE_RISK_NEUT_S and fit > GATE_RISK_NEUT_F and m_bp > GATE_RISK_NEUT_M_BP, {"s": s, "f": fit, "m_bp": m_bp}
    except Exception as e:
        logging.getLogger("tri_job").warning("risk-neut: %s", e)
    return False, {}


def robust_overfit_test(api, expr, base_s):
    report = {"ok": True, "tests": []}
    probes = [
        ("decay+2", {**base_s, "decay": min(int(base_s.get("decay", 3)) + 2, 10)}),
        ("uni_TOP2000", {**base_s, "universe": "TOP2000"}),
        ("sign_flip", base_s),
    ]
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
            s, fit = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            ok = abs(s) > 0.8 if name == "sign_flip" else (s > 0.9 and fit > 0.5)
            report["tests"].append({"name": name, "sharpe": s, "fitness": fit})
            if not ok:
                report["ok"] = False
        except Exception:
            report["ok"] = False
    return report


def set_alpha_props(api, pid, name, tags):
    try:
        r = api.session.patch(
            f"{API_BASE}/alphas/{pid}",
            json={"color": "GREEN", "name": name[:80], "tags": tags, "regular": {"description": name[:200]}},
            timeout=60,
        )
        return r.ok
    except Exception:
        return False


def evaluate_is(api, label, pid, expr, settings, track=None):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, fit = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m, ret = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0, _f(is_.get("returns")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_SHARPE: fails.append(f"S={s:.3f}")
    if fit <= GATE_FITNESS: fails.append(f"F={fit:.3f}")
    if tvr <= GATE_TVR_MIN or tvr >= GATE_TVR_MAX: fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_MARGIN_BP: fails.append(f"M={m_bp:.1f}bp")
    if ret <= GATE_RETURNS: fails.append(f"Ret={ret:.4f}")
    checks, plat_fails = {}, []
    sub_v, sub_lim = None, None
    if s > 1.4 or not fails:
        checks, plat_fails, ok = fetch_checks(api, pid)
        sub = checks.get("LOW_SUB_UNIVERSE_SHARPE") or {}
        sub_v, sub_lim = _f(sub.get("value")), _f(sub.get("limit"))
        if not fails:
            if not ok:
                return {"label": label, "pid": pid, "expr": expr, "settings": settings, "track": track,
                        "sharpe": s, "fitness": fit, "tvr": tvr, "margin": m, "status": "CHECK_PENDING",
                        "fails": ["check_pending"], "sub_univ": sub_v, "sub_limit": sub_lim}
            for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
                c = checks.get(name) or {}
                if c.get("result") == "FAIL": fails.append(f"{name}_FAIL")
                val = _f(c.get("value"))
                if val is not None and val <= GATE_2Y: fails.append(f"{name}={val:.3f}<=1.6")
            if plat_fails: fails.extend([f"PF:{x}" for x in plat_fails])
    return {"label": label, "pid": pid, "expr": expr, "settings": settings, "track": track,
            "sharpe": s, "fitness": fit, "tvr": tvr, "margin": m,
            "status": "PASS_CHEAP" if not fails else "FAIL", "fails": fails,
            "checks": checks, "failed_checks": plat_fails, "sub_univ": sub_v, "sub_limit": sub_lim}


def run_batch_multi(api, session, batch):
    by = {b["label"]: b for b in batch}
    raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
    out = []
    for item in raw:
        b = by.get(item["label"])
        if not item.get("ok") or not item.get("pid") or not b:
            out.append({"label": item["label"], "status": "error", "track": (b or {}).get("track"),
                        "fails": [item.get("error") or "no_pid"]})
        else:
            out.append(evaluate_is(api, item["label"], item["pid"], b["expr"], b["settings"], track=b.get("track")))
    return out


def run_job(job_id: str, job: Dict[str, Any] | None = None):
    if job is None:
        if job_id not in JOBS:
            raise SystemExit(f"unknown job {job_id}; choose {list(JOBS)} or --dataset")
        job = JOBS[job_id]
    else:
        JOBS[job_id] = job
    dataset = job["dataset"]
    cooldown = float(os.environ.get(f"{job_id.upper()}_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
    max_batches = int(os.environ.get(f"{job_id.upper()}_MAX_BATCHES", "40"))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ckpt_path = os.path.join(_HERE, "results", f"{job_id}_tri_{dataset}_checkpoint.json")
    progress_path = os.path.join(_HERE, "results", f"{job_id}_tri_progress_{ts}.log")
    found_path = os.path.join(_HERE, "results", f"scan_{job_id}_tri_{ts}.json")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(job_id)

    explore_q = build_explore(job, logger)
    seeds = seed_templates(job)
    improve_q = build_improve_variants(seeds, label_prefix="imp0")
    rescue_q = build_rescue_variants(seeds, label_prefix="rsc0")

    def ex_prio(v):
        s = 0
        if v.get("style") == "v39_bf": s += 10
        if (v.get("settings") or {}).get("universe") == "TOP3000": s += 3
        if (v.get("settings") or {}).get("neutralization") == "SECTOR": s += 3
        if (v.get("settings") or {}).get("decay") == 3: s += 2
        return -s

    explore_q.sort(key=ex_prio)

    api = WqApiSimple()
    session = api.session
    if os.path.exists(ckpt_path):
        try:
            ckpt = json.load(open(ckpt_path, encoding="utf-8"))
        except Exception:
            ckpt = None
    else:
        ckpt = None
    if ckpt:
        ckpt_results = list(ckpt.get("results") or [])
        found_alphas = list(ckpt.get("found_alphas") or [])
        done_keys: Set[Tuple] = set()
        for r in ckpt_results:
            if r.get("expr") and r.get("settings"):
                s = r["settings"]
                done_keys.add((r["expr"], s.get("universe"), s.get("decay"), s.get("neutralization"), s.get("truncation")))
    else:
        ckpt_results, found_alphas, done_keys = [], [], set()

    seen: Set[Tuple] = set(done_keys)
    explore_q = [v for v in explore_q if _vkey(v) not in seen]
    improve_q = [v for v in improve_q if _vkey(v) not in seen]
    rescue_q = [v for v in rescue_q if _vkey(v) not in seen]

    logger.info(
        "%s TRI %s | E=%d I=%d R=%d | slots 3/3/2 | NO SUBMIT",
        job_id.upper(), dataset, len(explore_q), len(improve_q), len(rescue_q),
    )
    logger.info("submit envelope: %s", envelope_summary())

    total_est = min(max_batches * BATCH_SIZE, len(explore_q) + len(improve_q) + len(rescue_q))
    pl = ProgressLogger(total_steps=max(total_est, 1), log_path=progress_path, task_name=f"{job_id}_tri_{dataset}", emit_interval_sec=15.0, max_recent=8)
    pl.start(meta={"dataset": dataset, "job": job_id, "tri_track": True, "submit_gate": True, "no_submit": True})
    pl.done = len(ckpt_results)

    survivors = []
    track_stats = {"explore": 0, "improve": 0, "rescue": 0}

    def save_ckpt(queues_meta=None):
        tmp = ckpt_path + ".tmp"
        payload = {"results": ckpt_results, "found_alphas": found_alphas}
        if queues_meta:
            payload["queues"] = queues_meta
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ckpt_path)
        try:
            from db_store import sync_checkpoint_to_db
            sync_checkpoint_to_db(job_id, dataset, ckpt_results, found_alphas)
        except Exception as e:
            logger.warning("db_store sync skipped: %s", e)

    for bi in range(max_batches):
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        if not (explore_q or improve_q or rescue_q):
            break
        batch, taken = mix_batch(explore_q, improve_q, rescue_q, seen=seen, batch_size=BATCH_SIZE)
        if not batch:
            break
        for t, n in taken.items():
            track_stats[t] = track_stats.get(t, 0) + n

        t0 = time.monotonic()
        logger.info(
            "--- Batch %d/%d | E%d I%d R%d | q E%d I%d R%d ---",
            bi + 1, max_batches, taken["explore"], taken["improve"], taken["rescue"],
            len(explore_q), len(improve_q), len(rescue_q),
        )
        results = run_batch_multi(api, session, batch)
        wall = time.monotonic() - t0

        for r in sorted(results, key=lambda x: _f(x.get("sharpe")) or -999, reverse=True)[:4]:
            if r.get("sharpe") is not None:
                logger.info(
                    "  [%s] %s S=%.3f F=%.3f TVR=%.3f %s",
                    r.get("track"), r.get("label"), r.get("sharpe") or 0, r.get("fitness") or 0,
                    r.get("tvr") or 0, r.get("status"),
                )

        for r in results:
            pl.step(extra={"label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"),
                           "sharpe": r.get("sharpe"), "track": r.get("track"), "batch_wall_sec": round(wall, 1)}, force_emit=True)
            parent = next((b for b in batch if b["label"] == r.get("label")), {})
            ckpt_results.append({
                "label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"),
                "track": r.get("track") or parent.get("track"),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"),
                "margin": r.get("margin"), "fails": r.get("fails") or [],
                "expr": r.get("expr") or parent.get("expr"),
                "settings": r.get("settings") or parent.get("settings"),
                "style": parent.get("style"), "field": parent.get("field"),
            })
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s/%s] cheap PASS", r.get("track"), r.get("label"))

        refill_queues_from_results(results, explore_q, improve_q, rescue_q, seen=seen, top_k=5)
        save_ckpt({"explore": len(explore_q), "improve": len(improve_q), "rescue": len(rescue_q), "track_stats": track_stats})

        if (bi + 1) % 5 == 0:
            ss = [_f(x.get("sharpe")) for x in ckpt_results if _f(x.get("sharpe")) is not None]
            logger.info("DIVERSITY @%d best_S=%s stats=%s", bi + 1, max(ss) if ss else None, track_stats)

        if bi + 1 < max_batches and (explore_q or improve_q or rescue_q):
            after_batch_cooldown(cooldown)

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
            logger.warning("[%s] PC=%s 淘汰", label, pc_val)
            continue
        corr_ok, pair_c = check_corr_vs_known(api, pid)
        if not corr_ok:
            logger.warning("[%s] pair-corr=%s 淘汰", label, pair_c)
            continue
        info = {
            "dataset": dataset, "style": job["style"], "pid": pid, "label": label,
            "expr": expr, "sharpe": r["sharpe"], "fitness": r["fitness"], "tvr": r["tvr"],
            "margin": r["margin"], "prod_corr": pc_val, "pair_corr_vs": {KNOWN_PID: pair_c},
            "risk_neut": rn_stats, "robust": robust, "settings": settings,
            "track": r.get("track"), "job": job_id, "submitted": False,
        }
        set_alpha_props(api, pid, f"{job_id}_{label}", [job_id, dataset, "USA_D1", "READY_MANUAL", "NO_SUBMIT"])
        found_alphas.append(info)
        append_ready({**info, "margin_bp": (r["margin"] or 0) * 10000, "tags": [job_id, dataset, "USA_D1", "READY_MANUAL"]})
        logger.info("*** FOUND %s S=%.3f PC=%.4f (NO SUBMIT) ***", pid, r["sharpe"], pc_val)
        save_ckpt()

    with open(found_path, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done found=%d stats=%s", len(found_alphas), track_stats)
    pl.finish(summary={"found": len(found_alphas), "track_stats": track_stats, "no_submit": True})


def discover_job(dataset: str, session=None) -> Dict[str, Any]:
    """按 dataset 自动拉字段, 构造三轨 job 配置."""
    if session is None:
        api = WqApiSimple()
        session = api.session
    rows, offset = [], 0
    while True:
        r = session.get(
            f"{API_BASE}/data-fields",
            params={
                "instrumentType": "EQUITY",
                "region": "USA",
                "universe": "TOP3000",
                "delay": 1,
                "dataset.id": dataset,
                "limit": 50,
                "offset": offset,
            },
            timeout=60,
        )
        if r.status_code == 429:
            time.sleep(35)
            continue
        if not r.ok:
            raise RuntimeError(f"fields {dataset}: {r.status_code} {r.text[:160]}")
        batch = (r.json() or {}).get("results") or []
        rows.extend(batch)
        count = (r.json() or {}).get("count") or 0
        if not batch or len(rows) >= count:
            break
        offset += 50
        time.sleep(1.5)
    if not rows:
        raise RuntimeError(f"no fields for {dataset}")

    def cov(x):
        try:
            return float(x.get("coverage") or 0)
        except Exception:
            return 0.0

    rows.sort(key=cov, reverse=True)
    # 优先 MATRIX, 否则 VECTOR
    mats = [x for x in rows if (x.get("type") or "").upper() == "MATRIX" and cov(x) >= 0.35]
    vecs = [x for x in rows if (x.get("type") or "").upper() == "VECTOR" and cov(x) >= 0.35]
    if mats:
        kind, pool = "matrix", mats
    elif vecs:
        kind, pool = "vector", vecs
    else:
        kind = "matrix" if (rows[0].get("type") or "").upper() == "MATRIX" else "vector"
        pool = rows
    fields = [x["id"] for x in pool[:8]]
    pairs = []
    if len(fields) >= 2:
        pairs.append((fields[0], fields[1], "f0_vs_f1"))
    if len(fields) >= 4:
        pairs.append((fields[2], fields[3], "f2_vs_f3"))
    return {
        "dataset": dataset,
        "style": f"auto_{dataset[:20]}",
        "kind": kind,
        "fields": fields,
        "pairs": pairs,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job", default="", help="预置 job id, 如 v47")
    p.add_argument("--dataset", default="", help="未点亮数据集 id; 自动拉字段")
    p.add_argument("--job-id", default="", help="自定义 job id (配合 --dataset)")
    args = p.parse_args()
    if args.dataset:
        jid = args.job_id or ("ds_" + re.sub(r"[^a-z0-9_]+", "_", args.dataset.lower())[:28])
        job = discover_job(args.dataset)
        run_job(jid, job=job)
    elif args.job:
        run_job(args.job)
    else:
        p.error("need --job or --dataset")


if __name__ == "__main__":
    main()
