#!/usr/bin/env python3
"""近关救援专用槽: 高 S / 高 TVR / 低 F·M → 降换手。

默认目标: dl_riskfree_returns (及可选 web_traffic_engage)
- 提高 decay (4–10)
- ts_mean 平滑 + 更长 z 窗
- ops<6; 禁 add/multiply/trade_when; 不提交
- 占舰队 1 救援槽; 与 explore 共享 submit_gate

用法:
  python -u scan_rescue_tvr.py
  python -u scan_rescue_tvr.py --dataset dl_riskfree_returns
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
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

from multi_sim import (
    API_BASE,
    DEFAULT_COOLDOWN_SEC,
    after_batch_cooldown,
    chunked,
    envelope_summary,
    run_multi_batch,
)
from wd_lib_wrapper import WqApiSimple

BATCH = 8
COOLDOWN = float(os.environ.get("RESCUE_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
CKPT = os.path.join(_HERE, "results", "rescue_tvr_checkpoint.json")

GATE_S, GATE_F, GATE_M = 1.58, 1.0, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
MAX_PC = 0.70
MAX_OPS = 6

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rescue_tvr")

# 已验证高 S 父本 (来自 checkpoint)
PARENTS = [
    {
        "dataset": "dl_riskfree_returns",
        "field": "predicted_return_10day_horizon_techindi10",
        "note": "S~2.3 TVR~70% F~0.7 M~2bp",
    },
    {
        "dataset": "dl_riskfree_returns",
        "field": "prob_label1_1day_2quantile_2",
        "note": "次强",
    },
    {
        "dataset": "web_traffic_engage",
        "field": "aggregate_bounce_ratio_today",
        "note": "S~2.2 TVR高 — 若字段不存在会 sim 失败跳过",
    },
]


def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def count_ops(expr: str) -> int:
    low = expr.lower().replace(" ", "")
    if "trade_when(" in low or "add(" in low or "multiply(" in low:
        return 999
    if "*" in expr or re.search(r"(?<![eE])\+", expr):
        return 999
    return len(re.findall(r"[a-z_]+\(", expr.lower()))


def settings(uni, decay, neut, trunc=0.01):
    return {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": uni,
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


def build_exprs(field: str) -> List[tuple]:
    """返回 (tag, expr) 降换手骨架, ops<6."""
    f = field
    cands = [
        ("bf_z189", f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))"),
        ("bf_z252", f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 252), industry))"),
        ("mean22_z189", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 22), 189), industry))"),
        ("mean44_z252", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 44), 252), industry))"),
        ("mean22_z252", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 120), 22), 252), industry))"),
        ("tsrank126", f"rank(group_zscore(ts_rank(ts_backfill({f}, 66), 126), industry))"),
        ("tsrank252", f"rank(group_zscore(ts_rank(ts_mean(ts_backfill({f}, 66), 22), 252), industry))"),
        ("noz_mean", f"rank(group_zscore(ts_mean(ts_backfill({f}, 66), 44), industry))"),
    ]
    out = []
    for tag, e in cands:
        ops = count_ops(e)
        if ops < MAX_OPS:
            out.append((tag, e, ops))
        else:
            logger.warning("skip ops=%d %s", ops, tag)
    return out


def build_variants(datasets_filter: List[str] | None = None) -> List[Dict[str, Any]]:
    variants, seen = [], set()
    for p in PARENTS:
        if datasets_filter and p["dataset"] not in datasets_filter:
            continue
        field = p["field"]
        short = re.sub(r"[^a-z0-9]+", "_", field)[:18]
        for tag, expr, ops in build_exprs(field):
            for uni in ("TOP3000", "TOP2000"):
                for decay in (4, 5, 6, 8, 10):  # 高 decay 降 TVR
                    for neut in ("SECTOR", "INDUSTRY", "SUBINDUSTRY"):
                        for trunc in (0.01, 0.05, 0.08):
                            key = (expr, uni, decay, neut, trunc)
                            if key in seen:
                                continue
                            seen.add(key)
                            variants.append(
                                {
                                    "label": f"{short}_{tag}_{uni[:6]}_d{decay}_{neut[:3]}_t{int(trunc*100)}",
                                    "expr": expr,
                                    "settings": settings(uni, decay, neut, trunc),
                                    "dataset": p["dataset"],
                                    "field": field,
                                    "ops": ops,
                                    "track": "rescue_tvr",
                                }
                            )

    def prio(v):
        s = v["settings"]
        sc = 0
        if "mean" in v["label"]:
            sc += 8
        if s["decay"] in (5, 6, 8):
            sc += 5
        if s["universe"] == "TOP3000":
            sc += 3
        if s["neutralization"] == "SECTOR":
            sc += 2
        if "dl_riskfree" in v["dataset"]:
            sc += 10
        return -sc

    variants.sort(key=prio)
    # 控制规模: 优先前 120
    logger.info("rescue variants %d -> trim 120", len(variants))
    return variants[:120]


def evaluate(api, label, pid, expr, settings):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, fit = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m, ret = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0, _f(is_.get("returns")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_S:
        fails.append(f"S={s:.3f}")
    if fit <= GATE_F:
        fails.append(f"F={fit:.3f}")
    if tvr <= GATE_TVR_LO or tvr >= GATE_TVR_HI:
        fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_M:
        fails.append(f"M={m_bp:.1f}bp")
    if ret <= 0.05:
        fails.append(f"Ret={ret:.4f}")
    status = "PASS_CHEAP" if not fails else "FAIL"
    if status == "PASS_CHEAP" or (s > 1.5 and tvr < 0.35):
        try:
            ch = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                checks = (ch.json().get("is") or {}).get("checks") or []
                pf = [c.get("name") for c in checks if c.get("result") == "FAIL"]
                if pf and status == "PASS_CHEAP":
                    fails.extend([f"PF:{x}" for x in pf])
                    status = "FAIL"
                for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
                    c = next((x for x in checks if x.get("name") == name), None)
                    if not c:
                        continue
                    val = _f(c.get("value"))
                    if c.get("result") == "FAIL" or (val is not None and val <= 1.6):
                        fails.append(f"{name}={val}")
                        status = "FAIL"
        except Exception:
            pass
    return {
        "label": label,
        "pid": pid,
        "expr": expr,
        "settings": settings,
        "sharpe": s,
        "fitness": fit,
        "tvr": tvr,
        "margin_bp": m_bp,
        "status": status,
        "fails": fails,
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


def harvest(api, r, dataset):
    rn = api.run_backtest(r["expr"], settings={**r["settings"], "neutralization": "MARKET"})
    if not rn or not rn.get("platform_id"):
        return None
    det = api.get_alpha_details(rn["platform_id"])
    is_ = det.get("is") or {}
    rs, rf = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    rm = (_f(is_.get("margin")) or 0) * 10000
    if not (rs > 1 and rf > 0.7 and rm > 10):
        logger.info("risk-neut FAIL s=%.2f f=%.2f m=%.1f", rs, rf, rm)
        return None
    pc = wait_pc(api, r["pid"])
    if pc is None or pc >= MAX_PC:
        logger.warning("PC=%s 淘汰", pc)
        return None
    info = {
        "dataset": dataset,
        "style": "rescue_tvr_smooth",
        "pid": r["pid"],
        "label": r["label"],
        "expr": r["expr"],
        "sharpe": r["sharpe"],
        "fitness": r["fitness"],
        "tvr": r["tvr"],
        "margin_bp": r["margin_bp"],
        "prod_corr": pc,
        "risk_neut": {"s": rs, "f": rf, "m_bp": rm},
        "settings": r["settings"],
        "submitted": False,
        "tags": ["rescue_tvr", dataset, "USA_D1", "READY_MANUAL", "NO_SUBMIT"],
    }
    try:
        api.session.patch(
            f"{API_BASE}/alphas/{r['pid']}",
            json={
                "color": "GREEN",
                "name": f"rescue_{r['label']}"[:80],
                "tags": info["tags"],
                "regular": {"description": r["expr"][:200]},
            },
            timeout=60,
        )
    except Exception:
        pass
    ready = json.load(open(READY, encoding="utf-8")) if os.path.exists(READY) else {"goal": 10, "alphas": []}
    info["n"] = len(ready.get("alphas", [])) + 1
    ready.setdefault("alphas", []).append(info)
    with open(READY, "w", encoding="utf-8") as f:
        json.dump(ready, f, ensure_ascii=False, indent=2)
    logger.info("*** FOUND %s S=%.3f TVR=%.3f M=%.1f PC=%.4f ***", r["pid"], r["sharpe"], r["tvr"], r["margin_bp"], pc)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", action="append", default=[], help="可多次; 默认 dl_riskfree+web_traffic")
    args = ap.parse_args()
    filt = args.dataset or None

    variants = build_variants(filt)
    logger.info("RESCUE TVR lane | %d | %s", len(variants), envelope_summary())
    api = WqApiSimple()
    session = api.session
    results, found = [], []
    done = set()
    if os.path.exists(CKPT):
        try:
            ck = json.load(open(CKPT, encoding="utf-8"))
            results = list(ck.get("results") or [])
            found = list(ck.get("found_alphas") or [])
            done = {r.get("label") for r in results}
            variants = [v for v in variants if v["label"] not in done]
        except Exception:
            pass

    meta = {v["label"]: v for v in variants}
    for bi, batch in enumerate(chunked(variants, BATCH)):
        if found:
            break
        logger.info("--- Rescue Batch %d (%d left) ---", bi + 1, len(variants) - bi * BATCH)
        raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
        by = {b["label"]: b for b in batch}
        for item in raw:
            b = by.get(item["label"])
            if not item.get("ok") or not item.get("pid") or not b:
                results.append({"label": item["label"], "status": "error", "fails": [item.get("error")]})
                continue
            r = evaluate(api, item["label"], item["pid"], b["expr"], b["settings"])
            r["dataset"] = b["dataset"]
            results.append(r)
            logger.info(
                "  %s S=%.3f F=%.3f TVR=%.3f M=%.1fbp %s %s",
                r["label"][:40],
                r["sharpe"],
                r["fitness"],
                r["tvr"],
                r["margin_bp"],
                r["status"],
                (r["fails"] or [])[:2],
            )
            if r["status"] == "PASS_CHEAP":
                info = harvest(api, r, b["dataset"])
                if info:
                    found.append(info)
                    break
        with open(CKPT, "w", encoding="utf-8") as f:
            json.dump({"results": results, "found_alphas": found}, f, ensure_ascii=False, indent=2)
        if found:
            break
        if bi + 1 < (len(variants) + BATCH - 1) // BATCH:
            after_batch_cooldown(COOLDOWN)

    # 报告 TVR 改善
    ok = [r for r in results if r.get("tvr") is not None and r.get("sharpe") is not None]
    ok.sort(key=lambda x: (abs(x.get("sharpe") or 0), -(x.get("tvr") or 99)), reverse=True)
    logger.info(
        "Done found=%d; best tradeoff: %s",
        len(found),
        [
            (
                round(x.get("sharpe") or 0, 2),
                round(x.get("tvr") or 0, 3),
                round(x.get("fitness") or 0, 2),
                round(x.get("margin_bp") or 0, 1),
                x.get("label", "")[:30],
            )
            for x in ok[:8]
        ],
    )


if __name__ == "__main__":
    main()
