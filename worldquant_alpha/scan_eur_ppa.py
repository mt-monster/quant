#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EUR/D1/TOPCS1600 未点亮金字塔 PPA 挖掘（单数据集双字段组合）。

规则（用户硬约束）:
- 未点亮 = pyramidMultiplier == 1.0（本轮: risk72/risk68/risk70/risk62/imbalance5）
- 每条 alpha 只用一个数据集内的 2 个字段（returns/close 为基础价格数据，不计入数据集）
- PROD_CORRELATION 必须已出且 < 0.70 才可提交；未出或 >0.7 绝不提交
- SELF_CORRELATION >= 0.50 硬淘汰
- 目标: 成功提交 2 个 PPA（tags=PowerPoolSelected + color=GREEN），否则不停

范式来源 (memory/skill V9+V17 突破):
- scale(rank(ts_zscore(SPREAD, 189))) + scale(-rank(ts_zscore(returns, z))) * 0.35, decay 4/5
- group_zscore(ts_zscore(SPREAD,189), industry) 变体
- EUR Margin 门槛 > 10bp（区别于 USA 的 5bp）
"""
import sys, os, json, time, logging, itertools, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))

LOG_PATH = os.path.join(_HERE, "results", "eur_ppa_mining.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("eur_ppa")

from wd_lib_wrapper import WqApiSimple
from wd_lib.api.alphas import update_alpha_properties
from progress_logger import ProgressLogger

# ---------------- 闸门常量 (memory 2026-07-14 硬化版; EUR margin 10bp) ----------------
PRE_SHARPE = 1.58
PRE_FITNESS = 1.00
HARD_MARGIN_BP = 10.0        # EUR > 10bp
HARD_TVR_MIN = 0.05
HARD_TVR_MAX = 0.20
HARD_RETURNS = 0.05
MAX_PROD_CORR = 0.70         # 红线
MAX_SELF_CORR = 0.50
PC_WAIT_SEC = 3600
TARGET_SUBMIT = 2

SETTINGS_BASE = {
    "instrumentType": "EQUITY", "region": "EUR", "universe": "TOPCS1600",
    "delay": 1, "decay": 4, "neutralization": "SUBINDUSTRY", "truncation": 0.08,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y",
}

# ---------------- 未点亮数据集与高覆盖 MATRIX 字段 (discover_eur_unlit 结果) ----------------
DATASETS = {
    # 残差收益类：天然适合反转范式（优先）
    "risk72": [
        "cfg2_top1200_residual_return",
        "rsk72_top1200_dsrt",
        "top2500_equity_residualized_return",
        "top2500_equity_residualized_return_nocountry",
        "top2500_equity_residualized_return_nogroup",
        "rsk72_top800_dsrt",
        "cfg2_top800_residual_return",
    ],
    # 预测数据：beta/残差收益/权重
    "risk68": [
        "rsk68_residual_return",
        "rsk68_beta",
        "rsk68_weight_volatility_short",
        "rsk68_weight_dadv",
        "rsk68_weight_edadv",
    ],
    # 多因子模型：挑信号型字段（对冲基金持仓/卖空/市值/调整因子）
    "risk70": [
        "european_hedge_fund_ownership_count",
        "hedge_fund_ownership_percent_europe",
        "industry_count_short",
        "current_market_cap_usd",
        "country_adjustment_factor",
        "industry_adjustment_factor",
        "broad_market_factor_exposure",
    ],
    # Beta 风险因子：截距/ksrs + 因子值样本
    "risk62": [
        "rsk62_1_100_intercept",
        "rsk62_1_100_ksrs",
        "rsk62_1_100_val3",
        "rsk62_1_100_val10",
        "rsk62_1_100_val20",
        "rsk62_1_100_val30",
    ],
    # 仅 2 字段（USA 经验偏弱，垫底）
    "imbalance5": [
        "imb5_score",
        "imb5_mktcap",
    ],
}
# 本轮只挖 risk72（用户指定）
DATASET_ORDER = ["risk72"]

RET42 = "scale(-rank(ts_zscore(returns, 42)))"
RET21 = "scale(-rank(ts_zscore(returns, 21)))"
RET10 = "scale(-rank(ts_zscore(returns, 10)))"

# 已验证强信号对 + Stage5 扩展优先对
_PA = "cfg2_top1200_residual_return"
_PB = "top2500_equity_residualized_return"
_PRIORITY_PAIRS = [
    (_PA, _PB),
    ("cfg2_top1200_residual_return", "rsk72_top1200_dsrt"),
    ("cfg2_top800_residual_return", "rsk72_top800_dsrt"),
    ("cfg2_top1200_residual_return", "cfg2_top800_residual_return"),
    ("rsk72_top1200_dsrt", "rsk72_top800_dsrt"),
    ("top2500_equity_residualized_return", "rsk72_top1200_dsrt"),
    ("cfg2_top1200_residual_return", "top2500_equity_residualized_return_nocountry"),
    ("cfg2_top800_residual_return", "top2500_equity_residualized_return"),
]


def sm(f, win=22):
    return f"ts_mean(ts_backfill({f}, 66), {win})"


def bf(f):
    """仅 backfill，无平滑 — 更跟近端，利于 LADDER。"""
    return f"ts_backfill({f}, 66)"


def _priority_tasks():
    """Stage5：专攻 IS_LADDER（先前最高仅~1.19）+ EUR Margin>10bp。"""
    tasks = []
    for a, b in _PRIORITY_PAIRS:
        tag = f"{a[-12:]}__{b[-12:]}"
        for sm_name, sa, sb in (
            ("sm22", sm(a, 22), sm(b, 22)),
            ("sm11", sm(a, 11), sm(b, 11)),
            ("raw", bf(a), bf(b)),
        ):
            for direction, left, right in (("ab", sa, sb), ("ba", sb, sa)):
                spread = f"subtract({left}, {right}, filter=true)"
                fund189 = f"rank(ts_zscore({spread}, 189))"
                fund126 = f"rank(ts_zscore({spread}, 126))"
                fund63 = f"rank(ts_zscore({spread}, 63))"
                gz = f"rank(group_zscore(ts_zscore({spread}, 189), industry))"
                gz126 = f"rank(group_zscore(ts_zscore({spread}, 126), industry))"
                # memory: z21 returns + w0.35-0.45 + decay3/4/5 + group_zscore
                for w in ("0.35", "0.40", "0.45"):
                    for d in (3, 4, 5):
                        tasks.append((
                            "risk72",
                            f"S5.{tag}.{sm_name}_{direction}_gz_z21_w{w}_d{d}",
                            f"scale({gz}) + {RET21} * {w}",
                            {"decay": d},
                        ))
                # 短基金窗 + z21：抬近端 LADDER
                for w, d in (("0.40", 4), ("0.45", 4), ("0.40", 3)):
                    tasks.append((
                        "risk72",
                        f"S5.{tag}.{sm_name}_{direction}_f63_z21_w{w}_d{d}",
                        f"scale({fund63}) + {RET21} * {w}",
                        {"decay": d},
                    ))
                    tasks.append((
                        "risk72",
                        f"S5.{tag}.{sm_name}_{direction}_gz126_z21_w{w}_d{d}",
                        f"scale({gz126}) + {RET21} * {w}",
                        {"decay": d},
                    ))
                # 极短 returns 窗（抬近 2Y）
                tasks.append((
                    "risk72",
                    f"S5.{tag}.{sm_name}_{direction}_gz_z10_w0.40_d4",
                    f"scale({gz}) + {RET10} * 0.40",
                    {"decay": 4},
                ))
                # 压 TVR/提 Margin：更高 decay 的 gz+returns
                for d in (6, 8):
                    tasks.append((
                        "risk72",
                        f"S5.{tag}.{sm_name}_{direction}_gz_z21_w0.30_d{d}",
                        f"scale({gz}) + {RET21} * 0.30",
                        {"decay": d},
                    ))
                # 纯 fund 高 decay：冲 Margin（若 LADDER 仍 fail 也记录）
                tasks.append(("risk72", f"S5.{tag}.{sm_name}_{direction}_pure189_d10",
                              fund189, {"decay": 10}))
                tasks.append(("risk72", f"S5.{tag}.{sm_name}_{direction}_pure126_d8",
                              fund126, {"decay": 8}))
                # EUR 多国：COUNTRY 中性化试探（memory 禁 SECTOR/MARKET）
                tasks.append((
                    "risk72",
                    f"S5.{tag}.{sm_name}_{direction}_gz_z21_w0.40_d4_cty",
                    f"scale({gz}) + {RET21} * 0.40",
                    {"decay": 4, "neutralization": "COUNTRY"},
                ))
    return tasks


def build_variants(A, B):
    """单数据集双字段 A/B -> 表达式变体（含已验证 V9/V17 范式）。"""
    spread_ba = f"subtract({sm(B)}, {sm(A)}, filter=true)"
    spread_ab = f"subtract({sm(A)}, {sm(B)}, filter=true)"
    fund_ba = f"rank(ts_zscore({spread_ba}, 189))"
    fund_ab = f"rank(ts_zscore({spread_ab}, 189))"
    gz_ba = f"rank(group_zscore(ts_zscore({spread_ba}, 189), industry))"
    gz_ab = f"rank(group_zscore(ts_zscore({spread_ab}, 189), industry))"
    raw_ab = f"subtract({bf(A)}, {bf(B)}, filter=true)"
    gz_raw = f"rank(group_zscore(ts_zscore({raw_ab}, 189), industry))"
    out = [
        ("pure_ba_d6", fund_ba, {"decay": 6}),
        ("pure_ab_d6", fund_ab, {"decay": 6}),
        ("v9_ba_z42_d4", f"scale({fund_ba}) + {RET42} * 0.35", {"decay": 4}),
        ("v9_ab_z42_d4", f"scale({fund_ab}) + {RET42} * 0.35", {"decay": 4}),
        ("v9_ba_z21_d5", f"scale({fund_ba}) + {RET21} * 0.35", {"decay": 5}),
        ("v9_ab_z21_d4", f"scale({fund_ab}) + {RET21} * 0.40", {"decay": 4}),
        ("gz_ba_z42_d4", f"scale({gz_ba}) + {RET42} * 0.35", {"decay": 4}),
        ("gz_ba_z21_d4", f"scale({gz_ba}) + {RET21} * 0.40", {"decay": 4}),
        ("gz_ab_z21_d4", f"scale({gz_ab}) + {RET21} * 0.40", {"decay": 4}),
        ("gz_raw_z21_d4", f"scale({gz_raw}) + {RET21} * 0.40", {"decay": 4}),
        ("ratio_d6", f"rank(ts_zscore(divide({sm(A)}, abs({sm(B)}) + 0.001), 126))", {"decay": 6}),
    ]
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
    """PC 等待前的廉价闸门。返回 (ok, fails, metrics)"""
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


def wait_prod_corr(api, pid, max_wait=PC_WAIT_SEC, poll=30):
    """等待 PROD_CORRELATION 数值。返回 (pc_value|None, self_corr|None, checks)"""
    deadline = time.time() + max_wait
    checks = []
    while time.time() < deadline:
        ch = api.get_alpha_check(pid)
        checks = (ch.get("is") or {}).get("checks") or []
        pc = _get_check(checks, "PROD_CORRELATION")
        pcv = _to_float(pc.get("value"))
        if pcv is not None:
            scv = _to_float(_get_check(checks, "SELF_CORRELATION").get("value"))
            return pcv, scv, checks
        time.sleep(poll)
    return None, None, checks


_submit_lock = threading.Lock()
_submitted = []


def try_submit(api, pid, label, dataset, expr, metrics, pcv, scv):
    """终审 + 提交（PowerPoolSelected + GREEN）。"""
    global _submitted
    with _submit_lock:
        if len(_submitted) >= TARGET_SUBMIT:
            return False
        # 防御性终审
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
                "regular.description": f"EUR D1 PPA. Unlit pyramid dataset {dataset}. Two-field signal.",
            }, session=api.session)
            update_alpha_properties(pid, {"color": "GREEN"}, session=api.session)
        except Exception as e:
            logger.error("[%s] 提交属性设置失败: %s", label, e)
            return False
        rec = {
            "pid": pid, "label": label, "dataset": dataset, "expr": expr,
            "prod_corr": pcv, "self_corr": scv, **metrics,
            "submitted_at": datetime.now().isoformat(),
        }
        _submitted.append(rec)
        logger.info(">>> SUBMITTED #%d/%d [%s] pid=%s PC=%.4f SC=%s S=%.3f F=%.3f",
                    len(_submitted), TARGET_SUBMIT, label, pid, pcv, scv,
                    metrics["sharpe"], metrics["fitness"])
        _save_state()
        return True


def _save_state():
    out = os.path.join(_HERE, "results", "eur_ppa_submitted.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"target": TARGET_SUBMIT, "submitted": _submitted}, f, indent=2, ensure_ascii=False)


def run_variant(api, dataset, label, expr, overrides, pl, seen):
    if len(_submitted) >= TARGET_SUBMIT:
        seen.discard(expr)
        return None
    settings = SETTINGS_BASE.copy()
    settings.update(overrides)
    full_label = f"{dataset}.{label}"
    try:
        res = api.run_backtest(expr, settings=settings)
    except Exception as e:
        logger.warning("[%s] 回测异常: %s", full_label, e)
        seen.discard(expr)  # 允许下一轮重试
        return None
    if not res or not res.get("platform_id"):
        pl.step(extra={"label": full_label, "result": "no_id"})
        seen.discard(expr)  # 429 耗尽/超时不算已试
        return None
    pid = res["platform_id"]
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    ok, fails, metrics = cheap_gates(is_)
    tvr = metrics["tvr"]; marg = metrics["margin"]
    logger.info("[%s] pid=%s S=%.3f F=%.3f TVR=%s M=%s %s",
                full_label, pid, metrics["sharpe"], metrics["fitness"],
                f"{tvr*100:.1f}%" if tvr is not None else "?",
                f"{marg*10000:.1f}bp" if marg is not None else "?",
                "PASS-cheap" if ok else "; ".join(fails))
    pl.step(extra={"label": full_label, "pid": pid, "S": round(metrics["sharpe"], 3),
                   "F": round(metrics["fitness"], 3), "cheap": ok})
    # 平台检查：S 够高时即使廉价门未过也查 LADDER，便于 Stage5 调参
    ch = api.get_alpha_check(pid)
    checks = (ch.get("is") or {}).get("checks") or []
    if metrics["sharpe"] >= PRE_SHARPE:
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

    # 硬闸门: 等 PROD_CORRELATION
    logger.info("[%s] 廉价闸门通过，等待 PROD_CORRELATION（红线 <%.2f）…", full_label, MAX_PROD_CORR)
    pcv, scv, checks = wait_prod_corr(api, pid)
    if pcv is None:
        logger.warning("[%s] PC 在 %ds 内未出 — 按规则不提交", full_label, PC_WAIT_SEC)
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": ["PC_PENDING"]}
    if pcv >= MAX_PROD_CORR:
        logger.info("[%s] PC=%.4f >= %.2f 淘汰", full_label, pcv, MAX_PROD_CORR)
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": [f"PC={pcv:.4f}"]}
    if scv is not None and scv >= MAX_SELF_CORR:
        logger.info("[%s] SC=%.4f >= %.2f 淘汰", full_label, scv, MAX_SELF_CORR)
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": [f"SC={scv:.4f}"]}
    # 复校 FAIL（PC 出来后检查列表可能更新）
    fail_names = [c.get("name") for c in checks if c.get("result") == "FAIL"]
    if fail_names:
        logger.info("[%s] PC 后复校 FAIL: %s", full_label, ",".join(fail_names))
        return {"label": full_label, "pid": pid, **metrics, "passed": False, "fails": fail_names}

    submitted = try_submit(api, pid, label, dataset, expr, metrics, pcv, scv)
    return {"label": full_label, "pid": pid, **metrics, "prod_corr": pcv, "self_corr": scv,
            "passed": submitted, "fails": []}


def gen_tasks(round_no):
    """一轮任务：按数据集优先级轮转，每数据集限量字段对。Round1 前置精调任务。"""
    tasks = []
    if round_no == 1:
        tasks.extend(_priority_tasks())
    for ds in DATASET_ORDER:
        fields = DATASETS[ds]
        pairs = list(itertools.combinations(fields, 2))
        # 每轮扩大配对范围
        lo = (round_no - 1) * 6
        batch = pairs[lo:lo + 6] if lo < len(pairs) else []
        if not batch and round_no > 1:
            batch = pairs[:6]  # 重循环
        for a, b in batch:
            for label, expr, ov in build_variants(a, b):
                tasks.append((ds, f"{a[-18:]}__{b[-18:]}.{label}", expr, ov))
    return tasks


def main():
    logger.info("=" * 76)
    logger.info("EUR D1 TOPCS1600 PPA | 专挖 risk72 Stage5(LADDER+Margin) | 目标提交 %d 个",
                TARGET_SUBMIT)
    logger.info("红线: PC 必须已出且 <%.2f; SC<%.2f; S>=%.2f F>=%.2f M>%.0fbp TVR %d-%d%%",
                MAX_PROD_CORR, MAX_SELF_CORR, PRE_SHARPE, PRE_FITNESS,
                HARD_MARGIN_BP, HARD_TVR_MIN * 100, HARD_TVR_MAX * 100)
    logger.info("=" * 76)

    api = WqApiSimple()
    seen = set()
    all_results = []
    round_no = 1

    while len(_submitted) < TARGET_SUBMIT:
        tasks = [t for t in gen_tasks(round_no) if t[2] not in seen]
        if round_no == 1:
            resume_skip = int(os.environ.get("WQ_ROUND1_SKIP", "0"))
            if resume_skip:
                logger.info("Round 1 断点恢复：跳过前 %d 个已处理任务", resume_skip)
                tasks = tasks[resume_skip:]
        if not tasks:
            round_no += 1
            if round_no > 20:
                round_no = 1  # 回卷重扫（seen 中失败项已被释放）
            time.sleep(60)
            continue
        logger.info("--- Round %d: %d 条表达式 ---", round_no, len(tasks))
        pl = ProgressLogger(total_steps=len(tasks),
                            log_path=os.path.join(_HERE, "results", "eur_risk72_progress.log"),
                            task_name=f"eur_r72_r{round_no}", emit_interval_sec=30)
        pl.start(meta={"round": round_no, "submitted": len(_submitted), "dataset": "risk72"})
        # 并发 3：降低 SSL/代理僵死概率（C=5 仍留余量）
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="r72") as ex:
            futs = {}
            for ds, label, expr, ov in tasks:
                if len(_submitted) >= TARGET_SUBMIT:
                    break
                seen.add(expr)
                futs[ex.submit(run_variant, api, ds, label, expr, ov, pl, seen)] = label
            for fut in as_completed(futs):
                try:
                    r = fut.result()
                except Exception as e:
                    logger.warning("[%s] future 异常: %s", futs[fut], e)
                    continue
                if r:
                    all_results.append(r)
                if len(_submitted) >= TARGET_SUBMIT:
                    break
        pl.finish(summary={"submitted": len(_submitted), "results": len(all_results)})
        out = os.path.join(_HERE, "results",
                           f"eur_ppa_scan_r{round_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Round %d 结束 | 已提交 %d/%d | 累计回测 %d | 结果: %s",
                    round_no, len(_submitted), TARGET_SUBMIT, len(all_results), out)
        round_no += 1
        if len(_submitted) < TARGET_SUBMIT:
            time.sleep(30)

    logger.info("完成! 已提交 %d 个 EUR PPA:", len(_submitted))
    for r in _submitted:
        logger.info("  pid=%s [%s] S=%.3f PC=%.4f", r["pid"], r["label"], r["sharpe"], r["prod_corr"])


def supervisor():
    """自愈循环：任何未捕获异常记录 traceback 后 120s 重启，直到提交满目标。"""
    import traceback
    attempt = 0
    while True:
        try:
            main()
            return
        except KeyboardInterrupt:
            logger.info("收到中断，退出。已提交 %d/%d", len(_submitted), TARGET_SUBMIT)
            return
        except Exception:
            attempt += 1
            logger.error("主循环崩溃（第 %d 次），120s 后自动重启:\n%s",
                         attempt, traceback.format_exc())
            if len(_submitted) >= TARGET_SUBMIT:
                return
            time.sleep(120)


if __name__ == "__main__":
    supervisor()
