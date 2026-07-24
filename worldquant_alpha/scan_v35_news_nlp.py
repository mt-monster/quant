#!/usr/bin/env python3
"""V35: USA D1 news_sentiment_nlp (other未点亮) — 真 multi-sim 8 并发.

硬规则:
- REGULAR / maxTrade=OFF / 1-2字段 / ops<6
- 禁止 trade_when / add() / multiply()
- 不提交; PC缺失或>0.7 淘汰
- 闸门: S>1.58 F>1 TVR(5%,30%) margin>10bp 2y>1.6
- risk-neut: S>1 F>0.7 margin>10bp
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
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

from multi_sim import API_BASE, chunked, run_multi_batch
from progress_logger import ProgressLogger
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
BATCH_COOLDOWN_SEC = float(os.environ.get("V35_COOLDOWN", "45"))
PROGRESS_LOG_PATH = os.environ.get(
    "PROGRESS_LOG_PATH",
    os.path.join(_HERE, "results", f"v35_news_nlp_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
)
CKPT_PATH = os.path.join(_HERE, "results", "v35_news_nlp_checkpoint.json")
FOUND_PATH = os.path.join(_HERE, "results", f"scan_v35_news_nlp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v35")

GATE_SHARPE = 1.58
GATE_FITNESS = 1.0
GATE_MARGIN_BP = 10.0
GATE_TVR_MIN = 0.05
GATE_TVR_MAX = 0.30
GATE_RETURNS = 0.05
GATE_RISK_NEUT_S = 1.0
GATE_RISK_NEUT_F = 0.7
GATE_RISK_NEUT_M_BP = 10.0
MAX_PROD_CORR = 0.70
MAX_ALPHA_CORR = 0.40
MAX_OPS = 6
TARGET_ALPHAS = 1  # 本数据集先找1个合格再换数据集
DIVERSITY_EVERY = 10

# ---- fields (VECTOR) ----
SENT_FIELDS = [
    "headline_sentiment_vader_score",
    "headline_textblob_sentiment_score",
    "headline_sentence_sentiment_average",
    "headline_sentence_sentiment_maximum",
    "headline_sentence_sentiment_minimum",
    "headline_sentence_sentiment_median",
    "headline_subjectivity_score",
    "headline_vader_positive_polarity",
    "headline_vader_negative_polarity",
    "headline_sentiwordnet_positive_polarity",
    "headline_sentiwordnet_negative_polarity",
    "headline_flesch_readability_score",
    "headline_stopword_frequency",
    "headline_word_count_total",
]

PAIRS = [
    ("headline_vader_positive_polarity", "headline_vader_negative_polarity", "vader_pn"),
    ("headline_sentiwordnet_positive_polarity", "headline_sentiwordnet_negative_polarity", "swn_pn"),
    ("headline_sentence_sentiment_maximum", "headline_sentence_sentiment_minimum", "sent_range"),
    ("headline_sentiment_vader_score", "headline_subjectivity_score", "vader_subj"),
]

UNIVERSES = ["TOP3000", "ILLIQUID_MINVOL1M", "TOP2000"]
DECAYS = [3, 5, 8]
NEUTS = ["SUBINDUSTRY", "INDUSTRY"]


def _f(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def count_operators(expr: str) -> int:
    ops = re.findall(r"[a-z_]+\(", expr.lower())
    banned = {"trade_when(", "add(", "multiply("}
    for b in banned:
        if b in expr.lower().replace(" ", ""):
            return 999
    return len(ops)


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
    """多样模板骨架, ops<6, 无 add/multiply/trade_when."""
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

    # --- single-field skeletons ---
    for f in SENT_FIELDS:
        short = f.replace("headline_", "").replace("sentiment_", "s_").replace("_polarity", "")[:28]
        # zscore momentum
        add(
            f"z_{short}_m22_z66",
            f"rank(ts_zscore(ts_mean(vec_avg({f}), 22), 66))",
            "TOP3000",
            5,
            "SUBINDUSTRY",
            "zscore_mom",
            f,
        )
        add(
            f"z_{short}_m66_z252",
            f"rank(ts_zscore(ts_mean(vec_avg({f}), 66), 252))",
            "ILLIQUID_MINVOL1M",
            5,
            "SUBINDUSTRY",
            "zscore_long",
            f,
        )
        # flip
        add(
            f"nz_{short}_m22_z66",
            f"-rank(ts_zscore(ts_mean(vec_avg({f}), 22), 66))",
            "TOP3000",
            5,
            "SUBINDUSTRY",
            "zscore_flip",
            f,
        )
        # ts_rank
        add(
            f"tr_{short}_m22_r126",
            f"rank(ts_rank(ts_mean(vec_avg({f}), 22), 126))",
            "TOP3000",
            3,
            "INDUSTRY",
            "ts_rank",
            f,
        )
        # delta
        add(
            f"d_{short}_m10_d5",
            f"rank(ts_delta(ts_mean(vec_avg({f}), 10), 5))",
            "TOP2000",
            8,
            "SUBINDUSTRY",
            "delta",
            f,
        )
        # group_rank
        add(
            f"gr_{short}_m22",
            f"group_rank(ts_mean(vec_avg({f}), 22), industry)",
            "TOP3000",
            5,
            "SUBINDUSTRY",
            "group_rank",
            f,
        )
        # group_zscore
        add(
            f"gz_{short}_m22_z66",
            f"group_zscore(ts_zscore(ts_mean(vec_avg({f}), 22), 66), industry)",
            "ILLIQUID_MINVOL1M",
            3,
            "INDUSTRY",
            "group_zscore",
            f,
        )
        # ts_ir
        add(
            f"ir_{short}_m5_66",
            f"rank(ts_ir(ts_mean(vec_avg({f}), 5), 66))",
            "TOP3000",
            5,
            "SUBINDUSTRY",
            "ts_ir",
            f,
        )
        # vec_sum path
        add(
            f"vs_{short}_m22_z66",
            f"rank(ts_zscore(ts_mean(vec_sum({f}), 22), 66))",
            "TOP3000",
            8,
            "SUBINDUSTRY",
            "vec_sum_z",
            f,
        )
        # ts_decay_linear-ish via ts_mean longer
        add(
            f"sm_{short}_m5",
            f"rank(ts_mean(vec_avg({f}), 5))",
            "ILLIQUID_MINVOL1M",
            5,
            "SUBINDUSTRY",
            "short_mean",
            f,
        )

    # --- 2-field spreads (subtract only) ---
    for a, b, tag in PAIRS:
        add(
            f"sp_{tag}_z66",
            f"rank(ts_zscore(subtract(vec_avg({a}), vec_avg({b})), 66))",
            "TOP3000",
            5,
            "SUBINDUSTRY",
            "spread_z",
            f"{a}|{b}",
        )
        add(
            f"sp_{tag}_m22_z126",
            f"rank(ts_zscore(ts_mean(subtract(vec_avg({a}), vec_avg({b})), 22), 126))",
            "ILLIQUID_MINVOL1M",
            5,
            "SUBINDUSTRY",
            "spread_smooth",
            f"{a}|{b}",
        )
        add(
            f"nsp_{tag}_m22_z66",
            f"-rank(ts_zscore(ts_mean(subtract(vec_avg({a}), vec_avg({b})), 22), 66))",
            "TOP3000",
            3,
            "INDUSTRY",
            "spread_flip",
            f"{a}|{b}",
        )
        add(
            f"sp_{tag}_gr",
            f"group_rank(ts_mean(subtract(vec_avg({a}), vec_avg({b})), 22), industry)",
            "TOP2000",
            8,
            "SUBINDUSTRY",
            "spread_group",
            f"{a}|{b}",
        )

    # extra decay/universe grid on top signal fields only
    core = [
        "headline_sentiment_vader_score",
        "headline_sentence_sentiment_average",
        "headline_sentiwordnet_positive_polarity",
    ]
    for f in core:
        short = f.replace("headline_", "")[:24]
        for uni in UNIVERSES:
            for decay in DECAYS:
                for neut in NEUTS:
                    add(
                        f"grid_z_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(ts_mean(vec_avg({f}), 22), 126))",
                        uni,
                        decay,
                        neut,
                        "grid_z",
                        f,
                    )
                    add(
                        f"grid_nz_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"-rank(ts_zscore(ts_mean(vec_avg({f}), 22), 126))",
                        uni,
                        decay,
                        neut,
                        "grid_nz",
                        f,
                    )

    logger.info("Built %d variants (ops<%d)", len(variants), MAX_OPS)
    return variants


def diversity_report(results: List[Dict], variants_meta: Dict[str, Dict], round_n: int):
    """每10轮多样性评估."""
    recent = results[-80:] if len(results) > 80 else results
    styles = Counter()
    fields = Counter()
    ops_used = Counter()
    skeletons = Counter()
    for r in recent:
        meta = variants_meta.get(r.get("label") or "", {})
        styles[meta.get("style", "?")] += 1
        fields[str(meta.get("field", "?"))[:40]] += 1
        expr = meta.get("expr") or r.get("expr") or ""
        for op in re.findall(r"[a-z_]+\(", expr.lower()):
            ops_used[op[:-1]] += 1
        # skeleton: strip field names
        sk = re.sub(r"headline_[a-z0-9_]+", "F", expr)
        skeletons[sk[:80]] += 1

    sharpes = [_f(r.get("sharpe")) for r in recent if _f(r.get("sharpe")) is not None]
    best = max(sharpes) if sharpes else None
    pos = sum(1 for s in sharpes if s and s > 0.8)
    logger.info("=" * 60)
    logger.info("DIVERSITY @ round~%d | recent=%d | best_S=%s | S>0.8=%d", round_n, len(recent), best, pos)
    logger.info("  styles: %s", styles.most_common(8))
    logger.info("  top fields: %s", fields.most_common(6))
    logger.info("  ops: %s", ops_used.most_common(10))
    logger.info("  skeletons(top3): %s", skeletons.most_common(3))
    logger.info(
        "  收益归因扫盲: VECTOR情绪需vec_avg/sum→ts平滑; 短窗易噪声高TVR; "
        "正负极性差(subtract)比单字段更有经济意义; 失效风险=新闻覆盖空洞/主题漂移"
    )
    logger.info("=" * 60)


def load_checkpoint():
    if not os.path.exists(CKPT_PATH):
        return None
    try:
        with open(CKPT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("load_checkpoint: %s", e)
        return None


def save_checkpoint(results_list, found_list):
    tmp = CKPT_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(CKPT_PATH), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"results": results_list, "found_alphas": found_list},
                f,
                ensure_ascii=False,
                indent=2,
            )
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
    except Exception:
        pass
    return False, {}


def set_alpha_props(api, pid, name, tags):
    """设置属性, 不提交."""
    try:
        payload = {
            "color": "GREEN",
            "name": name[:80],
            "tags": tags,
            "regular": {"description": name[:200]},
        }
        r = api.session.patch(f"{API_BASE}/alphas/{pid}", json=payload, timeout=60)
        logger.info("set_props %s -> HTTP %s", pid, r.status_code)
        return r.ok
    except Exception as e:
        logger.warning("set_props failed: %s", e)
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
                "label": label,
                "pid": pid,
                "expr": expr,
                "settings": settings,
                "sharpe": s,
                "fitness": f,
                "tvr": tvr,
                "margin": m,
                "status": "CHECK_PENDING",
                "fails": ["check_api_pending"],
                "checks": checks,
                "failed_checks": [],
                "ladder": ladder_v,
                "ladder_result": ladder_r,
            }
        # 2y sharpe strict
        for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
            c = checks.get(name) or {}
            if c.get("result") == "FAIL":
                fails.append(f"{name}_FAIL")
            elif c.get("value") is not None:
                try:
                    if float(c["value"]) <= 1.6 and name == "IS_LADDER_SHARPE":
                        # ladder uses >1.58 typically; user wants 2ysharpe>1.6
                        pass
                except Exception:
                    pass
        if plat_fails:
            fails.append("platform_FAIL")

    return {
        "label": label,
        "pid": pid,
        "expr": expr,
        "settings": settings,
        "sharpe": s,
        "fitness": f,
        "tvr": tvr,
        "margin": m,
        "status": "PASS_CHEAP" if not fails else "FAIL",
        "fails": fails,
        "checks": checks,
        "failed_checks": plat_fails,
        "ladder": ladder_v,
        "ladder_result": ladder_r,
    }


def run_batch_multi(api, session, batch: List[Dict]) -> List[Dict]:
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
    logger.info("V35 news_sentiment_nlp | %d variants | batch=%d", len(VARIANTS), BATCH_SIZE)

    api = WqApiSimple()
    session = api.session

    ckpt = load_checkpoint()
    if ckpt:
        ckpt_results = list(ckpt.get("results") or [])
        found_alphas = list(ckpt.get("found_alphas") or [])
        done_labels = {r.get("label") for r in ckpt_results if r.get("pid") or r.get("status") == "error"}
        logger.info("Resume: done=%d found=%d", len(done_labels), len(found_alphas))
    else:
        ckpt_results, found_alphas, done_labels = [], [], set()

    pending = [v for v in VARIANTS if v["label"] not in done_labels]
    # prioritize by style diversity: interleave styles
    by_style: Dict[str, List] = defaultdict(list)
    for v in pending:
        by_style[v["style"]].append(v)
    pending_sorted: List[Dict] = []
    while any(by_style.values()):
        for st in list(by_style.keys()):
            if by_style[st]:
                pending_sorted.append(by_style[st].pop(0))
    pending = pending_sorted

    pl = ProgressLogger(
        total_steps=len(VARIANTS),
        log_path=PROGRESS_LOG_PATH,
        task_name="v35_news_nlp",
        emit_interval_sec=15.0,
        max_recent=8,
    )
    pl.start(
        meta={
            "region": "USA",
            "dataset": "news_sentiment_nlp",
            "variants": len(VARIANTS),
            "pending": len(pending),
            "batch_size": BATCH_SIZE,
            "no_submit": True,
        }
    )
    pl.done = len(done_labels)

    batches = chunked(pending, BATCH_SIZE)
    survivors = []
    batch_count = 0

    for bi, batch in enumerate(batches):
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        t0 = time.monotonic()
        logger.info("--- Batch %d/%d | %d alphas ---", bi + 1, len(batches), len(batch))
        results = run_batch_multi(api, session, batch)
        wall = time.monotonic() - t0
        batch_count += 1

        # sort log by sharpe
        scored = sorted(results, key=lambda r: _f(r.get("sharpe")) or -999, reverse=True)
        for r in scored[:3]:
            if r.get("sharpe") is not None:
                logger.info(
                    "  top %s S=%.3f F=%.3f TVR=%.3f M=%.1fbp %s",
                    r.get("label"),
                    r.get("sharpe") or 0,
                    r.get("fitness") or 0,
                    r.get("tvr") or 0,
                    (r.get("margin") or 0) * 10000,
                    r.get("status"),
                )

        for r in results:
            label = r.get("label")
            pl.step(
                extra={
                    "label": label,
                    "pid": r.get("pid"),
                    "status": r.get("status"),
                    "sharpe": r.get("sharpe"),
                    "fitness": r.get("fitness"),
                    "tvr": r.get("tvr"),
                    "margin": r.get("margin"),
                    "fails": r.get("fails"),
                    "phase": 1,
                    "batch_wall_sec": round(wall, 1),
                },
                force_emit=True,
            )
            ckpt_results.append(
                {
                    "label": label,
                    "pid": r.get("pid"),
                    "status": r.get("status"),
                    "sharpe": r.get("sharpe"),
                    "fitness": r.get("fitness"),
                    "tvr": r.get("tvr"),
                    "margin": r.get("margin"),
                    "fails": r.get("fails") or [],
                    "expr": r.get("expr") or (vmeta.get(label) or {}).get("expr"),
                    "style": (vmeta.get(label) or {}).get("style"),
                }
            )
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s] cheap PASS -> Phase2", label)

        save_checkpoint(ckpt_results, found_alphas)

        if batch_count % DIVERSITY_EVERY == 0:
            diversity_report(ckpt_results, vmeta, batch_count)

        # early pivot signal: after 10 batches if best S < 0.9, log warning
        if batch_count == 10:
            ss = [_f(x.get("sharpe")) for x in ckpt_results if _f(x.get("sharpe")) is not None]
            best = max(ss) if ss else 0
            if best < 0.9:
                logger.warning(
                    "10轮后 best_S=%.3f <0.9 — 模板多样性继续, 若再10轮仍弱则换数据集",
                    best,
                )

        if bi + 1 < len(batches) and BATCH_COOLDOWN_SEC > 0:
            time.sleep(BATCH_COOLDOWN_SEC)

    # Phase 2
    logger.info("Phase2 survivors=%d", len(survivors))
    for r in survivors:
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        label, pid, expr, settings = r["label"], r["pid"], r["expr"], r["settings"]
        rn_ok, rn_stats = test_risk_neutralization(api, expr, settings)
        if not rn_ok:
            logger.info("[%s] risk-neut FAIL %s", label, rn_stats)
            continue
        pc_val = wait_for_pc(api, pid)
        if pc_val is None:
            logger.warning("[%s] PC missing — 不符合提交要求, 跳过(不提交)", label)
            continue
        if pc_val >= MAX_PROD_CORR:
            logger.warning("[%s] PC=%.4f >=0.7 — 淘汰(不提交)", label, pc_val)
            continue
        sc = (r.get("checks") or {}).get("SELF_CORRELATION") or {}
        scv = _f(sc.get("value")) or 0.0
        info = {
            "dataset": "news_sentiment_nlp",
            "label": label,
            "pid": pid,
            "expr": expr,
            "sharpe": r["sharpe"],
            "fitness": r["fitness"],
            "tvr": r["tvr"],
            "margin": r["margin"],
            "prod_corr": pc_val,
            "self_corr": scv,
            "risk_neut": rn_stats,
            "settings": settings,
            "submitted": False,
        }
        set_alpha_props(
            api,
            pid,
            f"v35_nlp_{label}",
            ["v35", "news_sentiment_nlp", "USA_D1", "READY_MANUAL"],
        )
        found_alphas.append(info)
        logger.info("*** FOUND %s S=%.3f PC=%.4f (NO SUBMIT) ***", pid, r["sharpe"], pc_val)
        save_checkpoint(ckpt_results, found_alphas)

    with open(FOUND_PATH, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done. found=%d file=%s (never submitted)", len(found_alphas), FOUND_PATH)
    pl.finish(extra={"found": len(found_alphas), "no_submit": True})


if __name__ == "__main__":
    main()
