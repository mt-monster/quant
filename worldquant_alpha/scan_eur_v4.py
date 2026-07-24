#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EUR/D1/TOPCS1600 未点亮金字塔 PPA 挖掘 V4 — 宽撒网 + 结构变体。

教训 (2026-07-17 分析):
- risk72 已知强对 v9 范式全期 S=2.1 但 LADDER~0.9/SUB~0.95 双双 FAIL
  → 高 decay 救 Margin 会进一步压 LADDER, 不再作为主方向
- V4 策略: 全数据集(risk72/risk68/risk62/risk70/imbalance5)全字段对宽撒网,
  多范式(v9组合/gz/纯基金/ts_delta动量/ts_rank) + 双方向,
  找"近期天然强"的信号; Round2 对 S>=1.3 的对做参数扩展

硬规则:
- 单数据集双字段 (returns 为基础价格数据不计入)
- 提交前必须: 平台检查全 PASS + PC 已出且 <0.70 + SC<0.50
- S>=1.58 F>=1.0 TVR 5-20% M>10bp Ret>5% Ret>DD
"""
import sys, os, json, time, logging, itertools, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))

LOG_PATH = os.path.join(_HERE, "results", "eur_v4_mining.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("eur_v4")

from wd_lib_wrapper import WqApiSimple
from wd_lib.api.alphas import update_alpha_properties
from progress_logger import ProgressLogger

PRE_SHARPE = 1.58
PRE_FITNESS = 1.00
HARD_MARGIN_BP = 10.0
HARD_TVR_MIN = 0.05
HARD_TVR_MAX = 0.20
HARD_RETURNS = 0.05
MAX_PROD_CORR = 0.70
MAX_SELF_CORR = 0.50
PC_WAIT_SEC = 3600
TARGET_SUBMIT = 2

SETTINGS_BASE = {
    "instrumentType": "EQUITY", "region": "EUR", "universe": "TOPCS1600",
    "delay": 1, "decay": 5, "neutralization": "SUBINDUSTRY", "truncation": 0.08,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y",
}

DATASETS = {
    "risk72": [
        "cfg2_top1200_residual_return", "rsk72_top1200_dsrt",
        "top2500_equity_residualized_return", "top2500_equity_residualized_return_nocountry",
        "top2500_equity_residualized_return_nogroup", "rsk72_top800_dsrt",
        "cfg2_top800_residual_return",
    ],
    "risk68": [
        "rsk68_residual_return", "rsk68_beta", "rsk68_weight_volatility_short",
        "rsk68_weight_dadv", "rsk68_weight_edadv",
    ],
    "risk62": [
        "rsk62_1_100_intercept", "rsk62_1_100_ksrs", "rsk62_1_100_val3",
        "rsk62_1_100_val10", "rsk62_1_100_val20", "rsk62_1_100_val30",
    ],
    "risk70": [
        "european_hedge_fund_ownership_count", "hedge_fund_ownership_percent_europe",
        "industry_count_short", "current_market_cap_usd", "country_adjustment_factor",
        "industry_adjustment_factor", "broad_market_factor_exposure",
    ],
    "imbalance5": ["imb5_score", "imb5_mktcap"],
}
DATASET_ORDER = ["risk72", "risk68", "risk62", "risk70", "imbalance5"]

RET42 = "scale(-rank(ts_zscore(returns, 42)))"
RET21 = "scale(-rank(ts_zscore(returns, 21)))"


def sm(f, win=22):
    return f"ts_mean(ts_backfill({f}, 66), {win})"


def core_variants(A, B):
    """Round1: 8 个结构互异的范式, 双方向覆盖。"""
    sa, sb = sm(A), sm(B)
    sp_ab = f"subtract({sa}, {sb}, filter=true)"
    sp_ba = f"subtract({sb}, {sa}, filter=true)"
    z126_ab = f"ts_zscore({sp_ab}, 126)"
    z126_ba = f"ts_zscore({sp_ba}, 126)"
    z189_ab = f"ts_zscore({sp_ab}, 189)"
    z189_ba = f"ts_zscore({sp_ba}, 189)"
    return [
        ("v9ab_z126_d5", f"scale(rank({z126_ab})) + {RET42} * 0.35", {"decay": 5}),
        ("v9ba_z126_d5", f"scale(rank({z126_ba})) + {RET42} * 0.35", {"decay": 5}),
        ("gzab_z126_d5", f"scale(rank(group_zscore({z126_ab}, industry))) + {RET42} * 0.35", {"decay": 5}),
        ("pure_ab_z189_d8", f"rank({z189_ab})", {"decay": 8}),
        ("pure_ba_z189_d8", f"rank({z189_ba})", {"decay": 8}),
        ("delta_ab_d22_z126_d6", f"rank(ts_zscore(ts_delta({sp_ab}, 22), 126))", {"decay": 6}),
        ("tsrank_ab_z126_d6", f"rank(ts_rank({sp_ab}, 126))", {"decay": 6}),
        ("ratio_ab_z126_d6", f"rank(ts_zscore(divide({sa}, abs({sb}) + 0.001), 126))", {"decay": 6}),
    ]


def expand_variants(A, B):
    """Round2: 对 S>=1.3 的对做参数/结构扩展 (权重/窗口/decay/neut)。"""
    sa, sb = sm(A), sm(B)
    sp_ab = f"subtract({sa}, {sb}, filter=true)"
    sp_ba = f"subtract({sb}, {sa}, filter=true)"
    out = []
    for tag, sp in (("ab", sp_ab), ("ba", sp_ba)):
        for win in (63, 189):
            z = f"ts_zscore({sp}, {win})"
            out.append((f"v9{tag}_z{win}_w0.40_d4", f"scale(rank({z})) + {RET42} * 0.40", {"decay": 4}))
            out.append((f"v9{tag}_z{win}_w0.30_d6", f"scale(rank({z})) + {RET42} * 0.30", {"decay": 6}))
            out.append((f"v9{tag}_z{win}_r21_w0.35_d5", f"scale(rank({z})) + {RET21} * 0.35", {"decay": 5}))
            out.append((f"gz{tag}_z{win}_d5", f"scale(rank(group_zscore({z}, industry))) + {RET42} * 0.35", {"decay": 5}))
        out.append((f"pure_{tag}_z126_d10", f"rank(ts_zscore({sp}, 126))", {"decay": 10}))
        out.append((f"delta_{tag}_d10_z126_d8", f"rank(ts_zscore(ts_delta({sp}, 10), 126))", {"decay": 8}))
    return out


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _get_check(checks, name):
    return next((c for c in checks if c.get("name") == name), {})


def cheap_gates(is_):
    s = _to_float(is_.get("sharpe")) or 0.0
    f = _to_float(is_.get("fitness")) or 0.0
    tvr = _to_float(is_.get("turnover"))
    marg = _to_float(is_.get("margin"))
    ret = _to_float(is_.get("returns"))
    dd = _to_float(is_.get("drawdown"))
    fails = []
    if s < PRE_SHARPE:
        fails.append(f"S={s:.3f}")
    if f < PRE_FITNESS:
        fails.append(f"F={f:.3f}")
    if tvr is not None and not (HARD_TVR_MIN <= tvr <= HARD_TVR_MAX):
        fails.append(f"TVR={tvr:.3f}")
    if marg is not None and marg * 10000 < HARD_MARGIN_BP:
        fails.append(f"M={marg*10000:.1f}bp")
    if ret is not None and ret < HARD_RETURNS:
        fails.append(f"Ret={ret:.3f}")
    if ret is not None and dd is not None and ret <= dd:
        fails.append(f"Ret<=DD({ret:.3f}<={dd:.3f})")
    metrics = {"sharpe": s, "fitness": f, "tvr": tvr, "margin": marg, "returns": ret, "drawdown": dd}
    return (not fails), fails, metrics


def wait_prod_corr(api, pid, max_wait=PC_WAIT_SEC, poll=60):
    deadline = time.time() + max_wait
    checks = []
    while time.time() < deadline:
        try:
            ch = api.get_alpha_check(pid)
            checks = (ch.get("is") or {}).get("checks") or []
            pcv = _to_float(_get_check(checks, "PROD_CORRELATION").get("value"))
            if pcv is not None:
                scv = _to_float(_get_check(checks, "SELF_CORRELATION").get("value"))
                return pcv, scv, checks
        except Exception as e:
            logger.warning("get_alpha_check(%s) 异常: %s", pid, e)
        time.sleep(poll)
    return None, None, checks


_submit_lock = threading.Lock()
_submitted = []
_best = {}          # pair_key -> max sharpe (round2 选对用)
_best_lock = threading.Lock()


def try_submit(api, pid, label, dataset, expr, metrics, pcv, scv):
    global _submitted
    with _submit_lock:
        if len(_submitted) >= TARGET_SUBMIT:
            return False
        if pcv is None or pcv >= MAX_PROD_CORR:
            logger.warning("[%s] 终审否决: PC=%s", label, pcv)
            return False
        if scv is not None and scv >= MAX_SELF_CORR:
            logger.warning("[%s] 终审否决: SC=%s", label, scv)
            return False
        try:
            update_alpha_properties(pid, {
                "name": f"ppa_eur_{dataset}_{label}"[:60],
                "tags": ["PowerPoolSelected"],
                "regular.description": f"EUR D1 PPA. Unlit pyramid dataset {dataset}. Two-field combo signal.",
            }, session=api.session)
            update_alpha_properties(pid, {"color": "GREEN"}, session=api.session)
        except Exception as e:
            logger.error("[%s] 提交属性设置失败: %s", label, e)
            return False
        rec = {"pid": pid, "label": label, "dataset": dataset, "expr": expr,
               "prod_corr": pcv, "self_corr": scv, **metrics,
               "submitted_at": datetime.now().isoformat()}
        _submitted.append(rec)
        logger.info(">>> SUBMITTED #%d/%d [%s] pid=%s PC=%.4f SC=%s S=%.3f F=%.3f",
                    len(_submitted), TARGET_SUBMIT, label, pid, pcv, scv,
                    metrics["sharpe"], metrics["fitness"])
        out = os.path.join(_HERE, "results", "eur_v4_submitted.json")
        with open(out, "w", encoding="utf-8") as fp:
            json.dump({"target": TARGET_SUBMIT, "submitted": _submitted}, fp, indent=2, ensure_ascii=False)
        return True


def run_variant(api, dataset, pair_key, label, expr, overrides, pl):
    if len(_submitted) >= TARGET_SUBMIT:
        return None
    settings = SETTINGS_BASE.copy()
    settings.update(overrides)
    full_label = f"{dataset}.{label}"
    try:
        res = api.run_backtest(expr, settings=settings)
    except Exception as e:
        logger.warning("[%s] 回测异常: %s", full_label, e)
        return None
    if not res or not res.get("platform_id"):
        pl.step(extra={"label": full_label, "result": "no_id"})
        return None
    pid = res["platform_id"]
    try:
        det = api.get_alpha_details(pid)
    except Exception as e:
        logger.warning("[%s] 详情异常: %s", full_label, e)
        return None
    is_ = det.get("is") or {}
    ok, fails, metrics = cheap_gates(is_)
    s = metrics["sharpe"]
    with _best_lock:
        k = (dataset, pair_key)
        if s > _best.get(k, -9):
            _best[k] = s
    tvr = metrics["tvr"]; marg = metrics["margin"]
    logger.info("[%s] pid=%s S=%.3f F=%.3f TVR=%s M=%s %s",
                full_label, pid, s, metrics["fitness"],
                f"{tvr*100:.1f}%" if tvr is not None else "?",
                f"{marg*10000:.1f}bp" if marg is not None else "?",
                "PASS-cheap" if ok else "; ".join(fails))
    pl.step(extra={"label": full_label, "pid": pid, "S": round(s, 3),
                   "F": round(metrics["fitness"], 3), "cheap": ok})
    try:
        ch = api.get_alpha_check(pid)
        checks = (ch.get("is") or {}).get("checks") or []
    except Exception:
        checks = []
    if s >= 1.3:
        for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE", "LOW_SUB_UNIVERSE_SHARPE"):
            c = _get_check(checks, name)
            if c:
                logger.info("[%s] %s=%s/%s %s", full_label, name,
                            c.get("value"), c.get("limit"), c.get("result"))
    if not ok:
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": fails}
    fail_names = [c.get("name") for c in checks
                  if c.get("result") == "FAIL" and c.get("name") not in ("PROD_CORRELATION", "SELF_CORRELATION")]
    if fail_names:
        logger.info("[%s] 平台检查 FAIL: %s", full_label, ",".join(fail_names))
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": fail_names}
    logger.info("[%s] 廉价闸门+平台检查通过, 等待 PROD_CORRELATION...", full_label)
    pcv, scv, checks = wait_prod_corr(api, pid)
    if pcv is None:
        logger.warning("[%s] PC 未出 — 不提交", full_label)
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": ["PC_PENDING"]}
    if pcv >= MAX_PROD_CORR:
        logger.info("[%s] PC=%.4f >= %.2f 淘汰", full_label, pcv, MAX_PROD_CORR)
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": [f"PC={pcv:.4f}"]}
    if scv is not None and scv >= MAX_SELF_CORR:
        logger.info("[%s] SC=%.4f 淘汰", full_label, scv)
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": [f"SC={scv:.4f}"]}
    fail_names = [c.get("name") for c in checks if c.get("result") == "FAIL"]
    if fail_names:
        logger.info("[%s] PC 后复校 FAIL: %s", full_label, ",".join(fail_names))
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": fail_names}
    submitted = try_submit(api, pid, label, dataset, expr, metrics, pcv, scv)
    return {"label": full_label, "pid": pid, **metrics, "prod_corr": pcv, "self_corr": scv,
            "passed": submitted, "fails": []}


def gen_round1_tasks():
    tasks = []
    for ds in DATASET_ORDER:
        for A, B in itertools.combinations(DATASETS[ds], 2):
            for label, expr, ov in core_variants(A, B):
                tasks.append((ds, f"{A}||{B}", f"{A[-10:]}__{B[-10:]}.{label}", expr, ov))
    return tasks


def gen_round2_tasks():
    tasks = []
    with _best_lock:
        hot = sorted([(k, v) for k, v in _best.items() if v >= 1.3], key=lambda x: -x[1])
    for (ds, pair_key), v in hot:
        A, B = pair_key.split("||")
        for label, expr, ov in expand_variants(A, B):
            tasks.append((ds, pair_key, f"{A[-10:]}__{B[-10:]}.{label}", expr, ov))
    return tasks


def main():
    logger.info("=" * 76)
    logger.info("EUR V4 宽撒网 | 5 数据集全字段对 | 目标提交 %d 个", TARGET_SUBMIT)
    logger.info("红线: PC 已出且 <%.2f; SC<%.2f; S>=%.2f F>=%.2f M>%.0fbp TVR 5-20%%",
                MAX_PROD_CORR, MAX_SELF_CORR, PRE_SHARPE, PRE_FITNESS, HARD_MARGIN_BP)
    logger.info("=" * 76)
    api = WqApiSimple()
    seen = set()
    round_no = 1
    while len(_submitted) < TARGET_SUBMIT:
        if round_no == 1:
            tasks = gen_round1_tasks()
        else:
            tasks = gen_round2_tasks()
        tasks = [t for t in tasks if t[3] not in seen]
        if not tasks:
            logger.info("Round %d 无新任务, 300s 后重估", round_no)
            time.sleep(300)
            round_no += 1
            if round_no > 30:
                round_no = 2
            continue
        logger.info("--- Round %d: %d 条表达式 ---", round_no, len(tasks))
        pl = ProgressLogger(total_steps=len(tasks),
                            log_path=os.path.join(_HERE, "results", "eur_v4_progress.log"),
                            task_name=f"eur_v4_r{round_no}", emit_interval_sec=60)
        pl.start(meta={"round": round_no, "submitted": len(_submitted)})
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="v4") as ex:
            futs = {}
            for ds, pair_key, label, expr, ov in tasks:
                if len(_submitted) >= TARGET_SUBMIT:
                    break
                seen.add(expr)
                futs[ex.submit(run_variant, api, ds, pair_key, label, expr, ov, pl)] = label
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as e:
                    logger.warning("[%s] future 异常: %s", futs[fut], e)
                if len(_submitted) >= TARGET_SUBMIT:
                    break
        pl.finish(summary={"submitted": len(_submitted)})
        # Round1 结束后保存 pair 强度表
        out = os.path.join(_HERE, "results", f"eur_v4_best_r{round_no}.json")
        with _best_lock:
            snap = {f"{k[0]}|{k[1]}": v for k, v in sorted(_best.items(), key=lambda x: -x[1])}
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(snap, fp, indent=2, ensure_ascii=False)
        logger.info("Round %d 结束 | 已提交 %d/%d | pair 强度: %s", round_no, len(_submitted), TARGET_SUBMIT, out)
        round_no += 1
        if len(_submitted) < TARGET_SUBMIT:
            time.sleep(30)
    logger.info("完成! 已提交 %d 个 EUR PPA", len(_submitted))


def supervisor():
    import traceback
    attempt = 0
    while True:
        try:
            main()
            return
        except KeyboardInterrupt:
            logger.info("中断, 退出。已提交 %d/%d", len(_submitted), TARGET_SUBMIT)
            return
        except Exception:
            attempt += 1
            logger.error("主循环崩溃(第 %d 次), 120s 后重启:\n%s", attempt, traceback.format_exc())
            if len(_submitted) >= TARGET_SUBMIT:
                return
            time.sleep(120)


if __name__ == "__main__":
    supervisor()
