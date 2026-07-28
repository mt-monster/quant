#!/usr/bin/env python3
"""model313 深挖: 历史近关 S=1.57 (F/TVR/M 已过) + 探索 ts_rank S≈2.0。

策略:
  - 父本字段 mdl313_atlas_unit_name
  - 围绕 ts_rank / mean8-12+z126 / 短 decay 细扫
  - 目标抬 S 过 1.58, 保住 TVR∈(5%,30%) M>10
  - ops<6; 禁 add/multiply/trade_when; 不提交
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
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
CKPT = os.path.join(_HERE, "results", "rescue_model313_deep_checkpoint.json")

GATE_S, GATE_F, GATE_M = 1.58, 1.0, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
MAX_PC = 0.70
MAX_OPS = 6
FIELD = "mdl313_atlas_unit_name"
DATASET = "model313"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rescue_m313_deep")


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
    f = field
    cands = [
        # 探索冠军邻域 ts_rank
        ("tsr189", f"rank(group_zscore(ts_rank(ts_backfill({f}, 66), 189), industry))"),
        ("tsr126", f"rank(group_zscore(ts_rank(ts_backfill({f}, 66), 126), industry))"),
        ("tsr252", f"rank(group_zscore(ts_rank(ts_backfill({f}, 66), 252), industry))"),
        ("tsr189_bf22", f"rank(group_zscore(ts_rank(ts_backfill({f}, 22), 189), industry))"),
        ("tsr189_bf120", f"rank(group_zscore(ts_rank(ts_backfill({f}, 120), 189), industry))"),
        # 救援近关 mean10_z126 邻域 (细调 mean / z)
        ("mean8_z126", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 8), 126), industry))"),
        ("mean10_z126", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 10), 126), industry))"),
        ("mean12_z126", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 12), 126), industry))"),
        ("mean10_z100", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 10), 100), industry))"),
        ("mean10_z150", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 10), 150), industry))"),
        ("mean10_z189", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 10), 189), industry))"),
        # 无 mean + 短 decay 友好
        ("bf_z126", f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 126), industry))"),
        ("bf_z189", f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))"),
        ("bf_z100", f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 100), industry))"),
        # group 到 sector 的变体 (ops 仍 <6)
        ("tsr189_sec", f"rank(group_zscore(ts_rank(ts_backfill({f}, 66), 189), sector))"),
        ("mean10_z126_sec", f"rank(group_zscore(ts_zscore(ts_mean(ts_backfill({f}, 66), 10), 126), sector))"),
    ]
    out = []
    for tag, e in cands:
        ops = count_ops(e)
        if ops < MAX_OPS:
            out.append((tag, e, ops))
        else:
            logger.warning("skip ops=%d %s", ops, tag)
    return out


def build_variants() -> List[Dict[str, Any]]:
    variants, seen = [], set()
    for tag, expr, ops in build_exprs(FIELD):
        for uni in ("TOP3000", "TOP2000"):
            for decay in (1, 2, 3, 4, 5):
                for neut in ("INDUSTRY", "SECTOR", "SUBINDUSTRY"):
                    for trunc in (0.01, 0.05, 0.08):
                        key = (expr, uni, decay, neut, trunc)
                        if key in seen:
                            continue
                        seen.add(key)
                        variants.append(
                            {
                                "label": f"m313_{tag}_{uni[:6]}_d{decay}_{neut[:3]}_t{int(trunc*100)}",
                                "expr": expr,
                                "settings": settings(uni, decay, neut, trunc),
                                "dataset": DATASET,
                                "field": FIELD,
                                "ops": ops,
                                "track": "rescue_m313_deep",
                            }
                        )

    def prio(v):
        s = v["settings"]
        sc = 0
        if "tsr189" in v["label"]:
            sc += 20
        if "mean10_z126" in v["label"]:
            sc += 18
        if "mean8" in v["label"] or "mean12" in v["label"]:
            sc += 12
        if s["decay"] in (1, 2, 3):
            sc += 6
        if s["neutralization"] == "INDUSTRY":
            sc += 4
        if s["universe"] == "TOP3000":
            sc += 3
        if s["truncation"] == 0.08:
            sc += 2
        return -sc

    variants.sort(key=prio)
    logger.info("model313 deep variants %d -> trim 120", len(variants))
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


def harvest(api, r):
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
        "dataset": DATASET,
        "style": "model313_atlas_tsrank_deep",
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
        "tags": ["rescue_m313_deep", DATASET, "USA_D1", "READY_MANUAL", "NO_SUBMIT"],
    }
    try:
        api.session.patch(
            f"{API_BASE}/alphas/{r['pid']}",
            json={
                "color": "GREEN",
                "name": f"m313_{r['label']}"[:80],
                "tags": info["tags"],
                "regular": {"description": r["expr"][:200]},
            },
            timeout=60,
        )
    except Exception:
        pass
    ready = json.load(open(READY, encoding="utf-8")) if os.path.exists(READY) else {"goal": 10, "alphas": []}
    # 不重复 pid
    if any(a.get("pid") == r["pid"] for a in ready.get("alphas") or []):
        return info
    info["n"] = len(ready.get("alphas", [])) + 1
    ready.setdefault("alphas", []).append(info)
    with open(READY, "w", encoding="utf-8") as f:
        json.dump(ready, f, ensure_ascii=False, indent=2)
    logger.info("*** FOUND %s S=%.3f F=%.3f TVR=%.3f M=%.1f PC=%.4f ***", r["pid"], r["sharpe"], r["fitness"], r["tvr"], r["margin_bp"], pc)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=CKPT)
    args = ap.parse_args()
    ckpt = args.ckpt

    variants = build_variants()
    logger.info(
        "RESCUE model313 DEEP | field=%s | %d | parent: ts_rank S~2.0 / mean10_z126 S=1.57 | %s",
        FIELD,
        len(variants),
        envelope_summary(),
    )
    api = WqApiSimple()
    session = api.session
    results, found = [], []
    if os.path.exists(ckpt):
        try:
            ck = json.load(open(ckpt, encoding="utf-8"))
            results = list(ck.get("results") or [])
            found = list(ck.get("found_alphas") or [])
            done = {r.get("label") for r in results}
            variants = [v for v in variants if v["label"] not in done]
        except Exception:
            pass

    for bi, batch in enumerate(chunked(variants, BATCH)):
        if found:
            break
        logger.info("--- model313 Deep Batch %d (%d left) ---", bi + 1, len(variants) - bi * BATCH)
        raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
        by = {b["label"]: b for b in batch}
        for item in raw:
            b = by.get(item["label"])
            if not item.get("ok") or not item.get("pid") or not b:
                results.append({"label": item["label"], "status": "error", "fails": [item.get("error")]})
                continue
            r = evaluate(api, item["label"], item["pid"], b["expr"], b["settings"])
            r["dataset"] = DATASET
            results.append(r)
            logger.info(
                "  %s S=%.3f F=%.3f TVR=%.3f M=%.1fbp %s %s",
                r["label"][:42],
                r["sharpe"],
                r["fitness"],
                r["tvr"],
                r["margin_bp"],
                r["status"],
                (r["fails"] or [])[:2],
            )
            if r["status"] == "PASS_CHEAP":
                info = harvest(api, r)
                if info:
                    found.append(info)
                    break
        with open(ckpt, "w", encoding="utf-8") as f:
            json.dump(
                {"results": results, "found_alphas": found, "round": "model313_deep", "field": FIELD},
                f,
                ensure_ascii=False,
                indent=2,
            )
        if found:
            break
        if bi + 1 < (len(variants) + BATCH - 1) // BATCH:
            after_batch_cooldown(COOLDOWN)

    ok = [r for r in results if r.get("sharpe") is not None]
    ok.sort(key=lambda x: (-(x.get("sharpe") or 0), -(x.get("fitness") or 0)))
    logger.info(
        "Done found=%d; best: %s",
        len(found),
        [
            (
                round(x.get("sharpe") or 0, 2),
                round(x.get("fitness") or 0, 2),
                round(x.get("tvr") or 0, 3),
                round(x.get("margin_bp") or 0, 1),
                x.get("label", "")[:28],
            )
            for x in ok[:8]
        ],
    )


if __name__ == "__main__":
    main()
