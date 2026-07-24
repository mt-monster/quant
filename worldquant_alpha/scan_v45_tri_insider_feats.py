#!/usr/bin/env python3
"""V45: insider_feats 三轨 multi-sim (8 槽 = 3 explore + 3 improve + 2 settings-rescue).

- Explore: 新字段/骨架
- Improve: 对 V44 Top 与本轮结果做表达式突变
- Rescue: 近关候选只改 decay/neut/trunc/universe (抬 TVR/SUB)
ops<6; 禁 add/multiply/trade_when; 绝不提交.
"""
from __future__ import annotations

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
    select_top_candidates,
)
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
BATCH_COOLDOWN_SEC = float(os.environ.get("V45_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
MAX_BATCHES = int(os.environ.get("V45_MAX_BATCHES", "40"))
PROGRESS_LOG_PATH = os.path.join(_HERE, "results", f"v45_tri_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
CKPT_PATH = os.path.join(_HERE, "results", "v45_tri_insider_feats_checkpoint.json")
SEED_CKPT = os.path.join(_HERE, "results", "v44_insider_feats_checkpoint.json")
FOUND_PATH = os.path.join(_HERE, "results", f"scan_v45_tri_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
READY_PATH = os.path.join(_HERE, "results", "manual_submit_ready.json")
DATASET = "insider_feats"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v45")

GATE_SHARPE, GATE_FITNESS, GATE_MARGIN_BP = 1.58, 1.0, 10.0
GATE_TVR_MIN, GATE_TVR_MAX, GATE_RETURNS, GATE_2Y = 0.05, 0.30, 0.05, 1.6
GATE_RISK_NEUT_S, GATE_RISK_NEUT_F, GATE_RISK_NEUT_M_BP = 1.0, 0.7, 10.0
MAX_PROD_CORR, MAX_OPS, TARGET_ALPHAS = 0.70, 6, 1

# Explore 侧重未充分扫的字段 + 新骨架
EXPLORE_FIELDS = [
    "buy_sell_ratio_top20_60d_filled",  # V44 最强
    "buy_sell_ratio_top5_60d_filled",
    "buy_sell_ratio_all_60d_filled",
    "buy_sell_ratio_all_5d_filled",
    "buy_sell_tx_count_ratio_all_60d_filled",
    "buy_sell_ratio_all_250d_filled",
]
PAIRS = [
    ("buy_sell_ratio_top20_60d_filled", "buy_sell_ratio_all_60d_filled", "top20_vs_all"),
    ("buy_sell_ratio_all_5d_filled", "buy_sell_ratio_all_250d_filled", "bs_5_250"),
]


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


def _vkey(v: Dict[str, Any]) -> Tuple:
    s = v.get("settings") or {}
    return (v.get("expr"), s.get("universe"), s.get("decay"), s.get("neutralization"), s.get("truncation"))


def build_explore_variants() -> List[Dict[str, Any]]:
    """新字段探索: 侧重短窗/backfill/高 TVR 倾向骨架."""
    variants, seen = [], set()

    def add(label, expr, uni, decay, neut, style, field, trunc=0.08):
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

    for f in EXPLORE_FIELDS:
        short = f.replace("buy_sell_ratio_", "bsr_").replace("buy_sell_tx_count_ratio_", "bscr_").replace("_filled", "")[:16]
        for uni in ("TOP3000", "ILLIQUID_MINVOL1M"):
            for decay in (1, 2, 3):  # 低 decay 抬 TVR
                for neut in ("SECTOR", "INDUSTRY"):
                    # backfill 骨架 (V39 成功路径)
                    add(f"ex_bf_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_backfill(vec_avg({f}), 66), 189), industry))",
                        uni, decay, neut, "explore_bf", f)
                    add(f"ex_bfz_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(ts_backfill(vec_avg({f}), 66), 189))",
                        uni, decay, neut, "explore_bfz", f)
                    # 短 mean → 更高换手
                    add(f"ex_sm_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_mean(vec_avg({f}), 5), 63), industry))",
                        uni, decay, neut, "explore_short", f)
                    add(f"ex_dl_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_delta(vec_avg({f}), 5), industry))",
                        uni, decay, neut, "explore_delta", f)
                    add(f"ex_tr_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_rank(vec_avg({f}), 60))",
                        uni, decay, neut, "explore_rank", f)

    for a, b, tag in PAIRS:
        for uni in ("TOP3000",):
            for decay in (1, 2, 3):
                for neut in ("SECTOR", "INDUSTRY"):
                    add(f"ex_sp_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(subtract(vec_avg({a}), vec_avg({b})), 63))",
                        uni, decay, neut, "explore_spread", f"{a}|{b}")
                    add(f"ex_spgz_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(subtract(vec_avg({a}), vec_avg({b})), 126), industry))",
                        uni, decay, neut, "explore_spgz", f"{a}|{b}")

    logger.info("explore pool: %d", len(variants))
    return variants


def load_seed_tops() -> List[Dict[str, Any]]:
    if not os.path.exists(SEED_CKPT):
        return []
    try:
        d = json.load(open(SEED_CKPT, encoding="utf-8"))
        tops = select_top_candidates(d.get("results") or [], top_k=10, min_abs_sharpe=0.35)
        logger.info("seed tops from V44: %d", len(tops))
        for t in tops[:5]:
            logger.info("  seed S=%.3f TVR=%s %s", t.get("sharpe") or 0, t.get("tvr"), t.get("label"))
        return tops
    except Exception as e:
        logger.warning("load seed: %s", e)
        return []


def load_checkpoint():
    if not os.path.exists(CKPT_PATH):
        return None
    try:
        return json.load(open(CKPT_PATH, encoding="utf-8"))
    except Exception:
        return None


def save_checkpoint(results_list, found_list, queues_meta=None):
    tmp = CKPT_PATH + ".tmp"
    payload = {"results": results_list, "found_alphas": found_list}
    if queues_meta:
        payload["queues"] = queues_meta
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CKPT_PATH)


def append_ready(info):
    try:
        ready = json.load(open(READY_PATH, encoding="utf-8")) if os.path.exists(READY_PATH) else {"goal": 10, "alphas": []}
        info = dict(info)
        info["n"] = len(ready.get("alphas", [])) + 1
        ready.setdefault("alphas", []).append(info)
        with open(READY_PATH, "w", encoding="utf-8") as f:
            json.dump(ready, f, ensure_ascii=False, indent=2)
        logger.info("Appended ready %d/10", len(ready["alphas"]))
    except Exception as e:
        logger.warning("append_ready: %s", e)


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


def evaluate_is(api, label, pid, expr, settings, track=None):
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
    sub_v, sub_lim = None, None
    if s > 1.4 or not fails:
        checks, plat_fails, ok = fetch_checks(api, pid)
        sub = checks.get("LOW_SUB_UNIVERSE_SHARPE") or {}
        sub_v, sub_lim = _f(sub.get("value")), _f(sub.get("limit"))
        if not fails:
            if not ok:
                return {"label": label, "pid": pid, "expr": expr, "settings": settings, "track": track, "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "status": "CHECK_PENDING", "fails": ["check_pending"], "sub_univ": sub_v, "sub_limit": sub_lim}
            for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
                c = checks.get(name) or {}
                if c.get("result") == "FAIL": fails.append(f"{name}_FAIL")
                val = _f(c.get("value"))
                if val is not None and val <= GATE_2Y: fails.append(f"{name}={val:.3f}<=1.6")
            if plat_fails: fails.extend([f"PF:{x}" for x in plat_fails])
    return {"label": label, "pid": pid, "expr": expr, "settings": settings, "track": track, "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "status": "PASS_CHEAP" if not fails else "FAIL", "fails": fails, "checks": checks, "failed_checks": plat_fails, "sub_univ": sub_v, "sub_limit": sub_lim}


def run_batch_multi(api, session, batch):
    by = {b["label"]: b for b in batch}
    raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
    out = []
    for item in raw:
        b = by.get(item["label"])
        if not item.get("ok") or not item.get("pid") or not b:
            out.append({"label": item["label"], "status": "error", "track": (b or {}).get("track"), "fails": [item.get("error") or "no_pid"]})
        else:
            out.append(evaluate_is(api, item["label"], item["pid"], b["expr"], b["settings"], track=b.get("track")))
    return out


def main():
    explore_q = build_explore_variants()
    seed_tops = load_seed_tops()
    improve_q = build_improve_variants(seed_tops, label_prefix="imp0") if seed_tops else []
    rescue_q = build_rescue_variants(seed_tops, label_prefix="rsc0") if seed_tops else []

    # 优先 explore: 短窗/低 decay
    def ex_prio(v):
        s = 0
        if "top20" in str(v.get("field")): s += 8
        if v.get("style") in ("explore_bf", "explore_short"): s += 6
        if (v.get("settings") or {}).get("decay") <= 2: s += 3
        return -s

    explore_q.sort(key=ex_prio)

    api = WqApiSimple()
    session = api.session
    ckpt = load_checkpoint()
    if ckpt:
        ckpt_results = list(ckpt.get("results") or [])
        found_alphas = list(ckpt.get("found_alphas") or [])
        done_keys: Set[Tuple] = set()
        for r in ckpt_results:
            if r.get("expr") and r.get("settings"):
                s = r["settings"]
                done_keys.add((r["expr"], s.get("universe"), s.get("decay"), s.get("neutralization"), s.get("truncation")))
            elif r.get("label"):
                done_keys.add(("label", r["label"]))
    else:
        ckpt_results, found_alphas, done_keys = [], [], set()

    seen: Set[Tuple] = set(done_keys)
    # 过滤队列中已跑过的
    explore_q = [v for v in explore_q if _vkey(v) not in seen]
    improve_q = [v for v in improve_q if _vkey(v) not in seen]
    rescue_q = [v for v in rescue_q if _vkey(v) not in seen]

    logger.info(
        "V45 TRI-TRACK | explore=%d improve=%d rescue=%d | slots %d/%d/%d | NO SUBMIT",
        len(explore_q), len(improve_q), len(rescue_q), SLOT_EXPLORE, SLOT_IMPROVE, SLOT_RESCUE,
    )
    logger.info("submit envelope: %s", envelope_summary())

    total_est = min(MAX_BATCHES * BATCH_SIZE, len(explore_q) + len(improve_q) + len(rescue_q))
    pl = ProgressLogger(total_steps=max(total_est, 1), log_path=PROGRESS_LOG_PATH, task_name="v45_tri_insider_feats", emit_interval_sec=15.0, max_recent=8)
    pl.start(meta={"dataset": DATASET, "tri_track": True, "slots": [SLOT_EXPLORE, SLOT_IMPROVE, SLOT_RESCUE], "no_submit": True})
    pl.done = len(ckpt_results)

    survivors = []
    track_stats = {"explore": 0, "improve": 0, "rescue": 0}

    for bi in range(MAX_BATCHES):
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        if not (explore_q or improve_q or rescue_q):
            logger.info("queues empty, stop")
            break

        batch, taken = mix_batch(explore_q, improve_q, rescue_q, seen=seen, batch_size=BATCH_SIZE)
        if not batch:
            break
        for t, n in taken.items():
            track_stats[t] = track_stats.get(t, 0) + n

        t0 = time.monotonic()
        logger.info(
            "--- Batch %d/%d | slots E%d I%d R%d | q_left E%d I%d R%d ---",
            bi + 1, MAX_BATCHES, taken["explore"], taken["improve"], taken["rescue"],
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
            pl.step(extra={
                "label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"),
                "sharpe": r.get("sharpe"), "track": r.get("track"), "fails": r.get("fails"),
                "batch_wall_sec": round(wall, 1),
            }, force_emit=True)
            parent = next((b for b in batch if b["label"] == r.get("label")), {})
            ckpt_results.append({
                "label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"),
                "track": r.get("track") or parent.get("track"),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"),
                "margin": r.get("margin"), "fails": r.get("fails") or [],
                "expr": r.get("expr") or parent.get("expr"),
                "settings": r.get("settings") or parent.get("settings"),
                "style": parent.get("style"), "field": parent.get("field"),
                "parent_label": parent.get("parent_label"),
            })
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s/%s] cheap PASS", r.get("track"), r.get("label"))

        # 动态补充 improve/rescue
        refill_queues_from_results(results, explore_q, improve_q, rescue_q, seen=seen, top_k=5)
        save_checkpoint(
            ckpt_results, found_alphas,
            queues_meta={"explore": len(explore_q), "improve": len(improve_q), "rescue": len(rescue_q), "track_stats": track_stats},
        )

        if (bi + 1) % 5 == 0:
            ss = [_f(x.get("sharpe")) for x in ckpt_results if _f(x.get("sharpe")) is not None]
            by_track = {}
            for x in ckpt_results:
                t = x.get("track") or "?"
                by_track.setdefault(t, []).append(_f(x.get("sharpe")) or 0)
            best_t = {t: max(vs) if vs else None for t, vs in by_track.items()}
            logger.info("DIVERSITY @%d best_S=%s by_track=%s stats=%s", bi + 1, max(ss) if ss else None, best_t, track_stats)

        if bi + 1 < MAX_BATCHES and (explore_q or improve_q or rescue_q):
            after_batch_cooldown(BATCH_COOLDOWN_SEC)

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
            "dataset": DATASET, "style": "insider_buy_sell_ratio_tri", "pid": pid, "label": label,
            "expr": expr, "sharpe": r["sharpe"], "fitness": r["fitness"], "tvr": r["tvr"],
            "margin": r["margin"], "prod_corr": pc_val, "risk_neut": rn_stats, "robust": robust,
            "settings": settings, "track": r.get("track"), "submitted": False,
        }
        set_alpha_props(api, pid, f"v45_{label}", ["v45", DATASET, "USA_D1", "READY_MANUAL", "NO_SUBMIT", f"track_{r.get('track')}"])
        found_alphas.append(info)
        append_ready({**info, "margin_bp": (r["margin"] or 0) * 10000, "tags": ["v45", DATASET, "USA_D1", "READY_MANUAL"]})
        logger.info("*** FOUND %s S=%.3f PC=%.4f track=%s (NO SUBMIT) ***", pid, r["sharpe"], pc_val, r.get("track"))
        save_checkpoint(ckpt_results, found_alphas)

    with open(FOUND_PATH, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done found=%d track_stats=%s (never submitted)", len(found_alphas), track_stats)
    pl.finish(summary={"found": len(found_alphas), "track_stats": track_stats, "no_submit": True})


if __name__ == "__main__":
    main()
