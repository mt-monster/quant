#!/usr/bin/env python3
"""
USA / D1 / TOP3000 / model110 数据集 PPA Alpha 挖掘

基于 alpha_inspiration_model110.md 的 5 个模板:
  T1: 行业中性化残差动量
  T2: 分析师预期修正陡度 (双字段差)
  T3: 因子间价量背离 (相关/背离)
  T4: 组内残差横截面挖掘 (核心)
  T5: trade_when 条件交易

8 个字段: score, quality, growth, value, analyst_sentiment, alternative, tree, price_momentum_reversal
neutralization = NONE + group_neutralize(expr, sta1_top3000c50)
"""
from __future__ import annotations

import argparse, hashlib, json, logging, os, random, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import combinations
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from wd_lib.api.datasets import get_datafields, get_datasets
    from wd_lib_wrapper import get_api
    from database import (save_alpha, alpha_exists, get_session,
                          PipelineAlpha, save_pipeline_alphas,
                          update_pipeline_alpha_backtest, get_pipeline_alpha_by_hash)
    from local_selfcorr import ensure_selfcorr_data
except ImportError:
    from worldquant_alpha.wd_lib.api.datasets import get_datafields, get_datasets
    from worldquant_alpha.wd_lib_wrapper import get_api
    from worldquant_alpha.database import (save_alpha, alpha_exists, get_session,
                          PipelineAlpha, save_pipeline_alphas,
                          update_pipeline_alpha_backtest, get_pipeline_alpha_by_hash)
    from worldquant_alpha.local_selfcorr import ensure_selfcorr_data

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "mine_model110_ppa.log"), encoding="utf-8")])
logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────
REGION = "USA"
UNIVERSE = "TOP3000"
DATASET_ID = "model110"
TARGET_COUNT = 5
MAX_PROD_CORR = 0.7
CONCURRENT_THREADS = 4

SEARCH_SCOPE = {
    "instrumentType": "EQUITY",
    "region": REGION,
    "delay": 1,
    "universe": UNIVERSE,
}

# 使用平台级别 SUBINDUSTRY 中性化，避免 group_neutralize 包裹导致回测卡死
BACKTEST_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": REGION,
    "universe": UNIVERSE,
    "delay": 1,
    "decay": 0,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P0Y",
}

FIELDS = [
    "mdl110_score", "mdl110_quality", "mdl110_growth", "mdl110_value",
    "mdl110_analyst_sentiment", "mdl110_alternative", "mdl110_tree",
    "mdl110_price_momentum_reversal",
]

_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION", "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION", "PRODUCTION_CORR",
)
_found_lock = Lock()
_selfcorr_calc = None


# ── 工具函数 ──────────────────────────────────────────────

def fw(f: str) -> str:
    """字段预处理: 补缺失值 + winsorize"""
    return f"winsorize(ts_backfill({f}, 21), std=4)"


def apply_ram(expr: str) -> str:
    """平台级别已设置 SUBINDUSTRY 中性化，不再额外包裹"""
    return expr


def expr_hash(e: str) -> str:
    return hashlib.sha256(e.encode()).hexdigest()


# ── 表达式生成 ────────────────────────────────────────────

def generate_all_expressions() -> List[Tuple[str, str]]:
    """返回 (expression, template_name) 列表
    简化表达式，避免嵌套过深导致平台回测卡死。
    平台级别已设 SUBINDUSTRY 中性化。
    """
    exprs = []

    # ═══ 模板0: 最简单 rank / zscore (快速扫描) ═══
    for f in FIELDS:
        exprs.append((f"rank({f})", f"T0_rank_{f}"))
        exprs.append((f"-1 * rank({f})", f"T0_nrank_{f}"))
        exprs.append((f"ts_zscore({f}, 22)", f"T0_zscore_{f}"))
        exprs.append((f"-1 * ts_zscore({f}, 22)", f"T0_nzscore_{f}"))
        exprs.append((f"ts_decay_linear(rank({f}), 5)", f"T0_decay_{f}"))
        exprs.append((f"ts_delta(rank({f}), 5)", f"T0_delta_{f}"))

    # ═══ 模板4: 组内残差挖掘 (核心，简化版) ═══
    for f in FIELDS:
        for grp in ["sector", "subindustry"]:
            for win in [5, 10, 20]:
                exprs.append((
                    f"rank(ts_mean({f} - group_mean({f}, 1, {grp}), {win}))",
                    f"T4_residual_{f}_{grp}_w{win}"
                ))
            exprs.append((
                f"group_zscore(ts_zscore({f}, 22), {grp})",
                f"T4_zscore_{f}_{grp}"
            ))
            exprs.append((
                f"rank({f} - group_mean({f}, 1, {grp}))",
                f"T4_raw_{f}_{grp}"
            ))

    # ═══ 模板1: 行业中性化残差动量 (简化) ═══
    for f in FIELDS:
        exprs.append((
            f"ts_decay_linear(rank({f}), 5)",
            f"T1_decay_{f}"
        ))
        exprs.append((
            f"rank(ts_delta({f}, 10))",
            f"T1_momentum_{f}"
        ))
        exprs.append((
            f"rank(ts_std_dev({f}, 20))",
            f"T1_vol_{f}"
        ))

    # ═══ 模板2: 双字段差 (analyst_sentiment vs 其他) ═══
    for other_f in ["mdl110_quality", "mdl110_growth", "mdl110_value", "mdl110_score"]:
        for grp in ["sector", "subindustry"]:
            exprs.append((
                f"rank(group_zscore(mdl110_analyst_sentiment - {other_f}, {grp}))",
                f"T2_sentiment_vs_{other_f}_{grp}"
            ))
        exprs.append((
            f"zscore(mdl110_analyst_sentiment - {other_f})",
            f"T2_zscore_sentiment_vs_{other_f}"
        ))

    # score vs 各子因子
    for sub_f in ["mdl110_quality", "mdl110_growth", "mdl110_value", "mdl110_tree"]:
        exprs.append((
            f"rank(group_zscore(mdl110_score - {sub_f}, sector))",
            f"T2_score_vs_{sub_f}"
        ))

    # ═══ 模板3: 因子间相关/背离 ═══
    pairs = [
        ("mdl110_quality", "mdl110_growth"),
        ("mdl110_value", "mdl110_price_momentum_reversal"),
        ("mdl110_score", "mdl110_tree"),
        ("mdl110_alternative", "mdl110_analyst_sentiment"),
        ("mdl110_quality", "mdl110_value"),
        ("mdl110_growth", "mdl110_price_momentum_reversal"),
        ("mdl110_score", "mdl110_alternative"),
        ("mdl110_tree", "mdl110_quality"),
    ]
    for f1, f2 in pairs:
        for win in [10, 20, 60]:
            exprs.append((
                f"rank(ts_corr({f1}, {f2}, {win}))",
                f"T3_corr_{f1}_{f2}_w{win}"
            ))
        exprs.append((
            f"rank({f1} - {f2})",
            f"T3_diff_{f1}_{f2}"
        ))
        exprs.append((
            f"rank({f1} / add(abs({f2}), 0.01))",
            f"T3_ratio_{f1}_{f2}"
        ))

    # ═══ 模板5: trade_when 条件交易 ═══
    for f in FIELDS:
        exprs.append((
            f"trade_when(ts_arg_max(volume, 5) == 0, "
            f"group_zscore(group_rank(ts_mean({f}, 10), subindustry), "
            f"densify(bucket(rank(assets), range='0.1, 1, 0.1'))), "
            f"abs(returns) > 0.1)",
            f"T5_tradewhen_{f}"
        ))
        # 反向版本 (用 -1* 代替 negate)
        exprs.append((
            f"trade_when(ts_arg_max(volume, 5) == 0, "
            f"-1 * group_zscore(group_rank(ts_mean({f}, 10), subindustry), "
            f"densify(bucket(rank(assets), range='0.1, 1, 0.1'))), "
            f"abs(returns) > 0.1)",
            f"T5_tradewhen_neg_{f}"
        ))

    # 去重
    seen = set()
    unique = []
    for expr, name in exprs:
        if expr not in seen:
            seen.add(expr)
            unique.append((expr, name))

    return unique


# ── 平台检查 ─────────────────────────────────────────────

def parse_production_correlation(payload) -> Optional[float]:
    if not payload:
        return None
    for c in (payload.get("is") or {}).get("checks") or []:
        n = (c.get("name") or "").upper()
        if any(k in n for k in _PROD_CORR_NAMES):
            v = c.get("value")
            if v is None:
                return None
            try:
                return abs(float(v))
            except (TypeError, ValueError):
                return None
    for c in (payload.get("is") or {}).get("checks") or []:
        if "PRODUCTION" in (c.get("name") or "").upper():
            v = c.get("value")
            if v is not None:
                try:
                    return abs(float(v))
                except (TypeError, ValueError):
                    pass
    return None


def wait_for_production_correlation(api, aid: str, max_wait: int = 1800, poll: int = 25) -> Optional[float]:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            ch = api.get_alpha_check(aid)
        except Exception as e:
            logger.warning("check fail: %s", e)
            time.sleep(poll)
            continue
        c = parse_production_correlation(ch)
        if c is not None:
            return c
        logger.info("prod corr not ready, %ss retry (%s)", poll, aid)
        time.sleep(poll)
    return None


def passes_submission_shape(api, aid: str, ms: float, mf: float) -> Tuple[bool, float, float]:
    d = api.get_alpha_details(aid)
    i = d.get("is") or {}
    try:
        s = float(i.get("sharpe") or 0)
        f = float(i.get("fitness") or 0)
    except (TypeError, ValueError):
        return False, 0.0, 0.0
    return (True, s, f) if s >= ms and f >= mf else (False, s, f)


# ── Pipeline DB ──────────────────────────────────────────

def save_pipeline_exprs_to_db(expressions, round_num):
    db = get_session()
    to_sim = {}
    try:
        raw_exprs = [e for e, _ in expressions]
        names = {expr_hash(e): n for e, n in expressions}
        for expr in raw_exprs:
            h = expr_hash(expr)
            ex = get_pipeline_alpha_by_hash(db, h)
            if ex and ex.backtest_status in ("completed", "running"):
                continue
            to_sim[h] = expr
        ne = list(to_sim.values())
        if ne:
            save_pipeline_alphas(db, ne, order=1,
                                 stage=f"usa_model110_r{round_num}",
                                 settings={**BACKTEST_SETTINGS, "dataset_id": DATASET_ID},
                                 dataset_id=DATASET_ID)
    except Exception as e:
        logger.warning("pipeline db err: %s", e)
    finally:
        db.close()
    return to_sim, names


def update_pipeline_db(h, **kw):
    try:
        db = get_session()
        try:
            update_pipeline_alpha_backtest(db, h, **kw)
        finally:
            db.close()
    except Exception as e:
        logger.warning("update pipeline err: %s", e)


# ── 单次回测 ─────────────────────────────────────────────

def backtest_one(api, expr, eh, name, ms, mf, pcw, sn):
    ram_expr = apply_ram(expr)
    logger.info("SIM #%d [%s] %s", sn, name, ram_expr[:100])
    update_pipeline_db(eh, backtest_status="running")

    try:
        res = api.run_backtest(ram_expr, settings=BACKTEST_SETTINGS.copy())
    except Exception as e:
        logger.warning("bt err [%s]: %s", name, e)
        update_pipeline_db(eh, backtest_status="failed", error_message=str(e))
        return None

    if not res:
        update_pipeline_db(eh, backtest_status="failed", error_message="no result")
        return None
    pid = res.get("platform_id")
    if not pid:
        update_pipeline_db(eh, backtest_status="failed", error_message="no pid")
        return None

    ok, sh, fi = passes_submission_shape(api, pid, ms, mf)
    if not ok:
        logger.info("[%s] IS fail S=%.3f F=%.3f", name, sh, fi)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                           platform_alpha_id=pid, sharpe=sh, fitness=fi)
        return None

    logger.info("[%s] IS ok S=%.3f F=%.3f, checking self-corr…", name, sh, fi)

    # 本地快速预筛选自相关性
    if _selfcorr_calc is not None:
        try:
            local_sc = _selfcorr_calc.calc_self_corr(pid, region=REGION)
            if local_sc > MAX_PROD_CORR:
                logger.info("[%s] local self-corr %.4f > %.2f, skip", name, local_sc, MAX_PROD_CORR)
                update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                                   platform_alpha_id=pid, sharpe=sh, fitness=fi,
                                   checks_payload={"local_self_corr": local_sc})
                return None
            logger.info("[%s] local self-corr %.4f <= %.2f, checking prod corr", name, local_sc, MAX_PROD_CORR)
        except Exception as e:
            logger.debug("local self-corr skip: %s", e)

    pc = wait_for_production_correlation(api, pid, max_wait=pcw)
    if pc is None:
        logger.warning("[%s] no prod corr for %s", name, pid)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                           platform_alpha_id=pid, sharpe=sh, fitness=fi)
        return None
    if pc > MAX_PROD_CORR:
        logger.info("[%s] prod corr %.4f > %.2f, skip", name, pc, MAX_PROD_CORR)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                           platform_alpha_id=pid, sharpe=sh, fitness=fi,
                           checks_payload={"production_correlation": pc})
        return None

    rec = {
        "platform_alpha_id": pid,
        "dataset_id": DATASET_ID,
        "expression": ram_expr,
        "base_expression": expr,
        "template": name,
        "sharpe": sh,
        "fitness": fi,
        "production_correlation": pc,
        "found_at": datetime.now().isoformat(),
        "simulation_number": sn,
    }
    update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                       platform_alpha_id=pid, sharpe=sh, fitness=fi,
                       checks_payload={"production_correlation": pc, "passed": True},
                       candidate_status="candidate")
    return rec


# ── 主流程 ───────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="USA model110 PPA Alpha Mining")
    ap.add_argument("--min-sharpe", type=float, default=1.25, help="IS Sharpe 下限")
    ap.add_argument("--min-fitness", type=float, default=1.0, help="IS Fitness 下限")
    ap.add_argument("--prod-corr-wait", type=int, default=1800, help="等待生产相关性秒数")
    ap.add_argument("--target", type=int, default=TARGET_COUNT, help="目标命中数")
    args = ap.parse_args()

    target = args.target

    logger.info("=" * 72)
    logger.info("USA D1 PPA | model110 (Big data ML model) | 5-template mining")
    logger.info("Region=%s Universe=%s RAM=group_neutralize(%s) Target=%d",
                REGION, UNIVERSE, DEFAULT_RAM_FIELD, target)
    logger.info("Fields: %s", ", ".join(FIELDS))
    logger.info("=" * 72)

    api = get_api()

    # 初始化本地自相关性数据
    global _selfcorr_calc
    try:
        _selfcorr_calc = ensure_selfcorr_data(session=api.session)
        logger.info("本地自相关性数据已就绪")
    except Exception as e:
        logger.warning("本地自相关性初始化失败: %s", e)

    # 生成所有表达式
    all_exprs = generate_all_expressions()
    logger.info("共生成 %d 个唯一表达式", len(all_exprs))

    # 保存到 pipeline DB
    to_sim, names = save_pipeline_exprs_to_db(all_exprs, 1)
    if not to_sim:
        logger.warning("所有表达式已在 DB 中完成，无需回测")
        return
    logger.info("待回测: %d 个 (已跳过 %d 个已完成)", len(to_sim), len(all_exprs) - len(to_sim))

    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)

    found: List[Dict[str, Any]] = []
    total_sim = 0
    items = list(to_sim.items())
    random.Random(42).shuffle(items)

    # 并发回测
    with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS, thread_name_prefix="M") as ex:
        futs = {}
        for eh, expr in items:
            if len(found) >= target:
                break
            with _found_lock:
                total_sim += 1
                sn = total_sim
            name = names.get(eh, "unknown")
            futs[ex.submit(backtest_one, api, expr, eh, name,
                           args.min_sharpe, args.min_fitness,
                           args.prod_corr_wait, sn)] = (expr, name, eh)

        for fut in as_completed(futs):
            expr, name, eh = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                logger.warning("future err: %s", e)
                continue

            if rec:
                with _found_lock:
                    found.append(rec)
                    logger.info(
                        "✅ HIT #%d/%d id=%s tpl=%s corr=%.4f S=%.3f F=%.3f",
                        len(found), target, rec["platform_alpha_id"],
                        rec["template"], rec["production_correlation"],
                        rec["sharpe"], rec["fitness"],
                    )

                try:
                    save_alpha(
                        rec["expression"],
                        f"USA_MODEL110_PPA",
                        {**BACKTEST_SETTINGS, "dataset_id": DATASET_ID,
                         "template": name, "base_expression": expr},
                    )
                except Exception:
                    pass

                # 增量保存
                with _found_lock:
                    p = os.path.join(rdir, f"model110_ppa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                    with open(p, "w", encoding="utf-8") as fout:
                        json.dump({
                            "target": target, "found": len(found),
                            "dataset": DATASET_ID,
                            "region": REGION, "universe": UNIVERSE,
                            "total_simulations": total_sim,
                            "alphas": found,
                        }, fout, indent=2, ensure_ascii=False)
                    logger.info("saved to %s", p)

            with _found_lock:
                if len(found) >= target:
                    logger.info("TARGET REACHED, cancelling remaining…")
                    for fc in futs:
                        fc.cancel()
                    break

    # 最终保存
    p = os.path.join(rdir, f"model110_ppa_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as fout:
        json.dump({
            "target": target, "found": len(found),
            "dataset": DATASET_ID,
            "region": REGION, "universe": UNIVERSE,
            "total_simulations": total_sim,
            "alphas": found,
        }, fout, indent=2, ensure_ascii=False)
    logger.info("FINAL saved to %s", os.path.abspath(p))

    for i, a in enumerate(found, 1):
        logger.info("  Alpha #%d: %s [%s] S=%.3f F=%.3f PC=%.4f",
                     i, a["platform_alpha_id"], a["template"],
                     a["sharpe"], a["fitness"], a["production_correlation"])

    if len(found) >= target:
        logger.info("目标完成！共找到 %d 个 model110 PPA 候选", len(found))
    else:
        logger.warning("仅找到 %d/%d 个", len(found), target)


if __name__ == "__main__":
    main()
