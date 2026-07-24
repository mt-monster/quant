#!/usr/bin/env python3
"""V34 v2: USA insider_matrix — 真 multi-simulation + 有效 w 网格 + Phase 分离.

相对 v1 的改动 (参考顾问 machine_lib / v33 HKG v3):
1. POST /simulations 一次提交 N 条 (真 multi), 每批占 1 槽
2. reversal 模板把 w 写进表达式 (v1 只改 label 导致大量重复回测)
3. Phase1 只拿 IS; Phase2 仅对幸存者等 PC / risk-neut
4. /check 拉取失败记 pending, 不误判 platform_FAIL
"""
import sys, os, json, time, logging, re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))
from progress_logger import ProgressLogger
from wd_lib_wrapper import WqApiSimple
from multi_sim import run_multi_batch, chunked, API_BASE, DEFAULT_BATCH_SIZE

BATCH_SIZE = int(os.environ.get("V34_BATCH", str(DEFAULT_BATCH_SIZE)))
PROGRESS_LOG_PATH = os.environ.get(
    "PROGRESS_LOG_PATH",
    os.path.join(_HERE, "results", f"v34_v2_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v34v2")

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
TARGET_ALPHAS = 10
BATCH_COOLDOWN_SEC = float(os.environ.get("V34_COOLDOWN", "45"))

CKPT_PATH = os.path.join(_HERE, "results", "v34_v2_insider_matrix_checkpoint.json")


def _f(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def count_operators(expr: str) -> int:
    ops = re.findall(r"[a-z_]+\(", expr)
    return len([o for o in ops if o != "returns("])


settings_base = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 4,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P6Y",
    "maxTrade": "OFF",
}

KEY_FIELDS = [
    "eur_aggregated_value_1",
    "eur_aggregated_value_2",
    "eur_aggregated_value_3",
    "eur_aggregated_value_4",
    "eur_top_value_1",
    "eur_top_value_2",
    "eur_director_value_1",
    "eur_signal_value_1",
    "director_intensity_score",
]

SIGNAL_PAIRS = [
    ("eur_aggregated_value_3", "eur_aggregated_value_1", "agg_net_buy"),
    ("eur_aggregated_value_4", "eur_aggregated_value_2", "agg_net_buy_sum"),
    ("eur_director_value_1", "eur_top_value_1", "dir_vs_exec"),
    ("eur_aggregated_value_1", "eur_signal_value_1", "signal_premium"),
    ("eur_top_director_signal_value_3", "eur_top_director_signal_value_1", "top_dir_signal_net"),
]

# templates: name -> (needs_pair, builder)
# builder(field_or_pair, w) -> expr; w ignored for non-reversal
TEMPLATES = [
    ("momentum", False, lambda f, w: f"rank(ts_zscore(ts_backfill({f}, 66), 189))"),
    ("ind_momentum", False, lambda f, w: f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))"),
    ("rank_momentum", False, lambda f, w: f"rank(ts_rank(ts_backfill({f}, 66), 252))"),
    (
        "mom_reversal",
        False,
        lambda f, w: (
            f"rank(ts_zscore(ts_backfill({f}, 66), 189)) + scale(-rank(ts_zscore(returns, 42))) * {w}"
        ),
    ),
    (
        "delta_reversal",
        False,
        lambda f, w: (
            f"rank(ts_delta(ts_backfill({f}, 22), 22)) + scale(-rank(ts_zscore(returns, 42))) * {w}"
        ),
    ),
    # ind_mom_reversal / spread_reversal 常 >6 ops, 仅在 ops 达标时纳入
    (
        "ind_mom_reversal",
        False,
        lambda f, w: (
            f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry)) "
            f"+ scale(-rank(ts_zscore(returns, 42))) * {w}"
        ),
    ),
    (
        "spread_reversal",
        True,
        lambda pair, w: (
            f"rank(ts_zscore(subtract(ts_backfill({pair[1]}, 66), ts_backfill({pair[0]}, 66)), 189)) "
            f"+ scale(-rank(ts_zscore(returns, 42))) * {w}"
        ),
    ),
]


def build_variants() -> List[Dict[str, Any]]:
    variants = []
    for field in KEY_FIELDS:
        for tname, needs_pair, tfn in TEMPLATES:
            if needs_pair:
                continue
            is_rev = "reversal" in tname
            weights = [0.30, 0.35, 0.40] if is_rev else [0.35]
            for decay in [3, 4, 5, 6]:
                for w in weights:
                    expr = tfn(field, w)
                    if count_operators(expr) > MAX_OPS:
                        continue
                    settings = settings_base.copy()
                    settings["decay"] = decay
                    label = f"{tname}_{field}_d{decay}_w{w}"
                    variants.append({"label": label, "expr": expr, "settings": settings})

    for fA, fB, sig_name in SIGNAL_PAIRS:
        tname, needs_pair, tfn = TEMPLATES[-1]
        for decay in [3, 4, 5, 6]:
            for w in [0.30, 0.35, 0.40]:
                expr = tfn((fA, fB), w)
                if count_operators(expr) > MAX_OPS:
                    continue
                settings = settings_base.copy()
                settings["decay"] = decay
                label = f"spread_{sig_name}_d{decay}_w{w}"
                variants.append({"label": label, "expr": expr, "settings": settings})

    # 去重: 同 expr+decay 只留一条
    seen = set()
    uniq = []
    for v in variants:
        key = (v["expr"], v["settings"]["decay"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(v)
    return uniq


def _settings_hash():
    h = {k: settings_base.get(k) for k in ("region", "universe", "neutralization", "delay", "testPeriod")}
    h["batch"] = BATCH_SIZE
    h["arch"] = "multi_sim_v2"
    return json.dumps(h, sort_keys=True)


def load_checkpoint():
    if os.environ.get("V34_FRESH") == "1":
        return None
    try:
        if os.path.exists(CKPT_PATH):
            d = json.load(open(CKPT_PATH, encoding="utf-8"))
            if d.get("settings_hash") != _settings_hash():
                logger.warning("Checkpoint settings mismatch -> fresh run")
                return None
            return d
    except Exception as e:
        logger.warning("load_checkpoint failed: %s", e)
    return None


def save_checkpoint(results_list, found_list):
    tmp = CKPT_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(CKPT_PATH), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "settings_hash": _settings_hash(),
                    "results": results_list,
                    "found_alphas": found_list,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp, CKPT_PATH)
    except Exception as e:
        logger.warning("save_checkpoint failed: %s", e)


def fetch_checks(api, pid, retries=5):
    """返回 (checks_dict, fail_names, fetch_ok). fetch_ok=False 表示 API 未拿到, 勿当 FAIL."""
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


def test_risk_neutralization(api, expr, base_settings):
    settings = base_settings.copy()
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
    if s < GATE_SHARPE:
        fails.append(f"S={s:.3f}")
    if f < GATE_FITNESS:
        fails.append(f"F={f:.3f}")
    if tvr < GATE_TVR_MIN or tvr > GATE_TVR_MAX:
        fails.append(f"TVR={tvr:.4f}")
    if m_bp < GATE_MARGIN_BP:
        fails.append(f"M={m_bp:.1f}bp")
    if ret < GATE_RETURNS:
        fails.append(f"Ret={ret:.4f}")

    checks, plat_fails, fetch_ok = {}, [], True
    ladder_v, ladder_r = "?", "?"
    if not fails:
        # 仅廉价数值过线才拉 /check (省时间)
        checks, plat_fails, fetch_ok = fetch_checks(api, pid)
        ladder = checks.get("IS_LADDER_SHARPE") or checks.get("LOW_2Y_SHARPE") or {}
        ladder_v, ladder_r = ladder.get("value", "?"), ladder.get("result", "?")
        if not fetch_ok:
            # 不误判 FAIL — 进入待复核
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
    """提交一批真 multi-sim, 返回 evaluate_is 结果列表."""
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
    logger.info(
        "V34 v2 insider_matrix | %d unique variants | batch=%d | log=%s",
        len(VARIANTS),
        BATCH_SIZE,
        PROGRESS_LOG_PATH,
    )

    api = WqApiSimple()
    session = api.session

    ckpt = load_checkpoint()
    if ckpt:
        ckpt_results = list(ckpt.get("results") or [])
        found_alphas = list(ckpt.get("found_alphas") or [])
        done_labels = {r.get("label") for r in ckpt_results if r.get("pid") or r.get("status") == "error"}
        logger.info("Resume: %d done, %d found", len(done_labels), len(found_alphas))
    else:
        ckpt_results, found_alphas, done_labels = [], [], set()

    pending = [v for v in VARIANTS if v["label"] not in done_labels]
    pl = ProgressLogger(
        total_steps=len(VARIANTS),
        log_path=PROGRESS_LOG_PATH,
        task_name="v34_insider_matrix_v2",
        emit_interval_sec=15.0,
        max_recent=8,
    )
    pl.start(
        meta={
            "region": "USA",
            "dataset": "insider_matrix",
            "variants": len(VARIANTS),
            "pending": len(pending),
            "architecture": "multi_sim_v2",
            "batch_size": BATCH_SIZE,
            "target": TARGET_ALPHAS,
        }
    )
    pl.done = len(done_labels)

    phase1_start = time.monotonic()
    batches = chunked(pending, BATCH_SIZE)
    survivors = []  # PASS_CHEAP -> Phase2

    logger.info("Phase 1: multi-sim %d batches x up to %d", len(batches), BATCH_SIZE)

    for bi, batch in enumerate(batches):
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        t0 = time.monotonic()
        logger.info("--- Batch %d/%d | %d alphas ---", bi + 1, len(batches), len(batch))
        results = run_batch_multi(api, session, batch)
        wall = time.monotonic() - t0
        n_ok = sum(1 for r in results if r.get("pid"))
        logger.info(
            "Batch %d done in %.1fs | %.1fs/alpha (wall) | ok=%d/%d",
            bi + 1,
            wall,
            wall / max(len(batch), 1),
            n_ok,
            len(batch),
        )

        for r in results:
            label = r.get("label")
            pid = r.get("pid")
            status = r.get("status")
            pl.step(
                extra={
                    "label": label,
                    "pid": pid,
                    "status": status,
                    "sharpe": r.get("sharpe"),
                    "fitness": r.get("fitness"),
                    "tvr": r.get("tvr"),
                    "margin": r.get("margin"),
                    "ladder": r.get("ladder"),
                    "ladder_result": r.get("ladder_result"),
                    "fails": r.get("fails"),
                    "failed_checks": r.get("failed_checks"),
                    "checks": r.get("checks"),
                    "batch_wall_sec": round(wall, 1),
                    "phase": 1,
                },
                force_emit=True,
            )
            ckpt_results.append(
                {
                    "label": label,
                    "pid": pid,
                    "found": False,
                    "status": status,
                    "sharpe": r.get("sharpe"),
                    "fitness": r.get("fitness"),
                    "tvr": r.get("tvr"),
                    "margin": r.get("margin"),
                    "ladder": r.get("ladder"),
                    "ladder_result": r.get("ladder_result"),
                    "fails": r.get("fails") or [],
                    "checks": r.get("checks") or {},
                    "failed_checks": r.get("failed_checks") or [],
                }
            )
            if status == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s] cheap PASS -> Phase2 queue (S=%.3f)", label, r.get("sharpe") or 0)

        save_checkpoint(ckpt_results, found_alphas)
        if bi + 1 < len(batches) and BATCH_COOLDOWN_SEC > 0:
            time.sleep(BATCH_COOLDOWN_SEC)

    phase1_elapsed = time.monotonic() - phase1_start
    done_p1 = sum(1 for r in ckpt_results if r.get("label") in {v["label"] for v in pending} or True)
    logger.info(
        "Phase 1 complete: wall=%.0fs, survivors=%d, sec/alpha≈%.1f",
        phase1_elapsed,
        len(survivors),
        phase1_elapsed / max(len(pending) - len([v for v in pending if v["label"] in done_labels]), 1)
        if pending
        else 0,
    )

    # Phase 2: risk-neut + PC (仅幸存者)
    logger.info("Phase 2: %d survivors", len(survivors))
    for r in survivors:
        if len(found_alphas) >= TARGET_ALPHAS:
            break
        label, pid, expr, settings = r["label"], r["pid"], r["expr"], r["settings"]
        logger.info("[%s] risk-neut...", label)
        rn_ok, rn_stats = test_risk_neutralization(api, expr, settings)
        if not rn_ok:
            logger.info("[%s] risk-neut FAIL %s", label, rn_stats)
            continue
        logger.info("[%s] waiting PC...", label)
        pc_val = wait_for_pc(api, pid)
        if pc_val is None:
            logger.warning("[%s] PC timeout", label)
            continue
        if pc_val >= MAX_PROD_CORR:
            logger.warning("[%s] PC=%.4f", label, pc_val)
            continue
        sc = (r.get("checks") or {}).get("SELF_CORRELATION") or {}
        scv = _f(sc.get("value")) or 0.0
        if scv >= MAX_ALPHA_CORR:
            logger.warning("[%s] SC=%.4f", label, scv)
            continue
        alpha_info = {
            "label": label,
            "pid": pid,
            "expr": expr,
            "sharpe": r["sharpe"],
            "fitness": r["fitness"],
            "tvr": r["tvr"],
            "margin": r["margin"],
            "ladder": r.get("ladder"),
            "ladder_result": r.get("ladder_result"),
            "prod_corr": pc_val,
            "self_corr": scv,
            "risk_neut": rn_stats,
            "settings": settings,
        }
        found_alphas.append(alpha_info)
        logger.info(
            "*** FOUND [%s] (%d/%d) S=%.3f PC=%.4f ***",
            label,
            len(found_alphas),
            TARGET_ALPHAS,
            r["sharpe"],
            pc_val,
        )
        for row in ckpt_results:
            if row.get("label") == label:
                row["found"] = True
                break
        save_checkpoint(ckpt_results, found_alphas)
        pl.step(
            extra={"label": label, "pid": pid, "status": "FOUND", "prod_corr": pc_val, "phase": 2},
            force_emit=True,
        )

    save_checkpoint(ckpt_results, found_alphas)
    pl.finish(summary={"found": len(found_alphas), "variants": len(VARIANTS), "arch": "multi_sim_v2"})

    out_path = os.path.join(
        _HERE, "results", f"scan_v34_insider_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"found_alphas": found_alphas, "n_results": len(ckpt_results)}, f, indent=2)
    logger.info("V34 v2 done | found=%d | saved %s", len(found_alphas), out_path)
    logger.info(
        "Phase1 wall=%.0fs for %d pending | throughput≈%.1f alpha/hour",
        phase1_elapsed,
        len(pending),
        (len(pending) / max(phase1_elapsed, 1)) * 3600,
    )


if __name__ == "__main__":
    main()
