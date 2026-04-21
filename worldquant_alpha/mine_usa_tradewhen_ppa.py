#!/usr/bin/env python3
"""
USA / delay=D1 / universe=TOP3000 / trade_when 模板 PPA 挖掘

模板:
  trade_when(
    ts_arg_max(volume, 5) == 0,
    group_zscore(
      group_rank(ts_sum(FIELD1/FIELD2, WINDOW), subindustry),
      densify(bucket(rank(assets), range='0.1, 1, 0.1'))
    ),
    abs(returns) > 0.1
  )

变量:
  - FIELD1/FIELD2: 来自同一数据集的 MATRIX 字段对
  - WINDOW: ts_sum 窗口 [10, 20, 30, 60]
  - 额外变体: ts_arg_max 窗口, exit 阈值

要点:
  - 扫描 pyramidMultiplier==1.0 的未点亮数据集
  - neutralization=NONE + group_neutralize(expr, sta1_top3000c50)
  - 4线程并发回测
  - 本地自相关性快筛 + 平台生产相关性双重检查
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
                                               "mine_usa_tradewhen_ppa.log"), encoding="utf-8")])
logger = logging.getLogger(__name__)

# ── USA PPA 配置 ──────────────────────────────────────────
REGION = "USA"
UNIVERSE = "TOP3000"
TARGET_COUNT = 5
MAX_PROD_CORR = 0.7
CONCURRENT_THREADS = 4

SEARCH_SCOPE = {
    "instrumentType": "EQUITY",
    "region": REGION,
    "delay": 1,
    "universe": UNIVERSE,
}

# neutralization=NONE + 表达式侧 group_neutralize
DEFAULT_RAM_FIELD = os.environ.get("WQ_RAM_NEUTRAL_FIELD", "sta1_top3000c50")

BACKTEST_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": REGION,
    "universe": UNIVERSE,
    "delay": 1,
    "decay": 0,
    "neutralization": "NONE",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P0Y",
}

# trade_when 模板参数
TS_SUM_WINDOWS = [10, 20, 30, 60]
TS_ARG_MAX_WINDOWS = [5, 10]
EXIT_THRESHOLDS = [0.1]

_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION", "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION", "PRODUCTION_CORR",
)
_found_lock = Lock()
_selfcorr_calc = None


# ── 工具函数 ──────────────────────────────────────────────

def _unwrap_session(api):
    return api.session


def apply_ram_neutralization(expr: str) -> str:
    """RAM: neutralization=NONE + group_neutralize(expr, sta1_top3000c50)"""
    if "group_neutralize(" in expr:
        return expr
    return f"group_neutralize({expr}, {DEFAULT_RAM_FIELD})"


def expr_hash(e: str) -> str:
    return hashlib.sha256(e.encode()).hexdigest()


# ── trade_when 模板表达式生成 ─────────────────────────────

def build_trade_when_expressions(f1: str, f2: str) -> List[str]:
    """
    trade_when 模板: 双字段比率 + volume 触发 + asset-bucket z-score

    trade_when(
      ts_arg_max(volume, V) == 0,
      group_zscore(
        group_rank(ts_sum(F1/F2, W), subindustry),
        densify(bucket(rank(assets), range='0.1, 1, 0.1'))
      ),
      abs(returns) > T
    )
    """
    exprs = []

    for w in TS_SUM_WINDOWS:
        for v in TS_ARG_MAX_WINDOWS:
            for t in EXIT_THRESHOLDS:
                # 原始模板: F1/F2
                exprs.append(
                    f"trade_when(ts_arg_max(volume, {v}) == 0, "
                    f"group_zscore(group_rank(ts_sum({f1}/{f2}, {w}), subindustry), "
                    f"densify(bucket(rank(assets), range='0.1, 1, 0.1'))), "
                    f"abs(returns) > {t})"
                )

                # 反向: F2/F1
                exprs.append(
                    f"trade_when(ts_arg_max(volume, {v}) == 0, "
                    f"group_zscore(group_rank(ts_sum({f2}/{f1}, {w}), subindustry), "
                    f"densify(bucket(rank(assets), range='0.1, 1, 0.1'))), "
                    f"abs(returns) > {t})"
                )

                # 差值变体: F1 - F2
                exprs.append(
                    f"trade_when(ts_arg_max(volume, {v}) == 0, "
                    f"group_zscore(group_rank(ts_sum({f1} - {f2}, {w}), subindustry), "
                    f"densify(bucket(rank(assets), range='0.1, 1, 0.1'))), "
                    f"abs(returns) > {t})"
                )

    # 不带 trade_when 的纯信号变体 (更多变化)
    for w in TS_SUM_WINDOWS:
        # 纯 group_zscore 版本
        exprs.append(
            f"group_zscore(group_rank(ts_sum({f1}/{f2}, {w}), subindustry), "
            f"densify(bucket(rank(assets), range='0.1, 1, 0.1')))"
        )
        # rank 版本
        exprs.append(
            f"rank(ts_sum({f1}/{f2}, {w}))"
        )

    return exprs


# ── 数据集与字段获取 ──────────────────────────────────────

def list_usa_unlit_datasets(api, min_fields: int = 2) -> List[Dict[str, Any]]:
    """pyramidMultiplier==1.0 的 USA D1 数据集"""
    df = get_datasets(
        session=_unwrap_session(api),
        instrument_type=SEARCH_SCOPE["instrumentType"],
        region=SEARCH_SCOPE["region"],
        delay=SEARCH_SCOPE["delay"],
        universe=SEARCH_SCOPE["universe"],
    )
    if df is None or df.empty:
        return []

    rows = []
    for _, r in df.iterrows():
        try:
            pm = float(r.get("pyramidMultiplier", 1.0))
        except (TypeError, ValueError):
            pm = 1.0
        fc = int(r.get("fieldCount") or 0)
        if abs(pm - 1.0) < 1e-9 and fc >= min_fields:
            rows.append({
                "id": r["id"],
                "name": r.get("name", ""),
                "fieldCount": fc,
                "pyramidMultiplier": pm,
                "category": (r.get("category") or {}).get("id", ""),
            })

    rows.sort(key=lambda x: -x["fieldCount"])
    return rows


def fetch_matrix_fields(api, dataset_id: str, limit: int = 40) -> List[str]:
    """获取指定数据集的 MATRIX 类型字段"""
    df = get_datafields(
        search_scope=SEARCH_SCOPE,
        dataset_id=dataset_id,
        field_type="MATRIX",
        session=_unwrap_session(api),
    )
    if df is None or df.empty:
        return []
    ids = df[df["type"] == "MATRIX"]["id"].tolist()
    return ids[:limit]


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

def save_pipeline_exprs_to_db(expressions, round_num, dataset_id):
    db = get_session()
    to_sim = {}
    try:
        for expr, f1, f2 in expressions:
            h = expr_hash(expr)
            ex = get_pipeline_alpha_by_hash(db, h)
            if ex and ex.backtest_status in ("completed", "running"):
                continue
            to_sim[h] = (expr, f1, f2)
        ne = [it[0] for it in to_sim.values()]
        if ne:
            save_pipeline_alphas(db, ne, order=1,
                                 stage=f"usa_tradewhen_{dataset_id}_r{round_num}",
                                 settings={**BACKTEST_SETTINGS, "dataset_id": dataset_id},
                                 dataset_id=dataset_id)
    except Exception as e:
        logger.warning("pipeline db err: %s", e)
    finally:
        db.close()
    return to_sim


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

def backtest_one(api, expr, f1, f2, eh, ms, mf, pcw, sn, dataset_id):
    ram_expr = apply_ram_neutralization(expr)
    logger.info("SIM #%d [%s] %s/%s %s", sn, dataset_id, f1[:20], f2[:20], ram_expr[:100])
    update_pipeline_db(eh, backtest_status="running")

    try:
        res = api.run_backtest(ram_expr, settings=BACKTEST_SETTINGS.copy())
    except Exception as e:
        logger.warning("bt err: %s", e)
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
        logger.info("IS fail S=%.3f F=%.3f", sh, fi)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                           platform_alpha_id=pid, sharpe=sh, fitness=fi)
        return None

    logger.info("IS ok S=%.3f F=%.3f, checking local self-corr…", sh, fi)

    # 本地快速预筛选自相关性
    if _selfcorr_calc is not None:
        try:
            local_sc = _selfcorr_calc.calc_self_corr(pid, region=REGION)
            if local_sc > MAX_PROD_CORR:
                logger.info("local self-corr %.4f > %.2f, skip", local_sc, MAX_PROD_CORR)
                update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                                   platform_alpha_id=pid, sharpe=sh, fitness=fi,
                                   checks_payload={"local_self_corr": local_sc})
                return None
            logger.info("local self-corr %.4f <= %.2f, proceeding to prod corr", local_sc, MAX_PROD_CORR)
        except Exception as e:
            logger.debug("local self-corr skip: %s", e)

    pc = wait_for_production_correlation(api, pid, max_wait=pcw)
    if pc is None:
        logger.warning("no prod corr for %s", pid)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                           platform_alpha_id=pid, sharpe=sh, fitness=fi)
        return None
    if pc > MAX_PROD_CORR:
        logger.info("prod corr %.4f > %.2f, skip", pc, MAX_PROD_CORR)
        update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                           platform_alpha_id=pid, sharpe=sh, fitness=fi,
                           checks_payload={"production_correlation": pc})
        return None

    rec = {
        "platform_alpha_id": pid,
        "dataset_id": dataset_id,
        "expression": ram_expr,
        "base_expression": expr,
        "field_1": f1,
        "field_2": f2,
        "sharpe": sh,
        "fitness": fi,
        "production_correlation": pc,
        "found_at": datetime.now().isoformat(),
        "simulation_number": sn,
        "template": "trade_when",
    }
    update_pipeline_db(eh, backtest_status="completed", is_tested=True,
                       platform_alpha_id=pid, sharpe=sh, fitness=fi,
                       checks_payload={"production_correlation": pc, "passed": True},
                       candidate_status="candidate")
    return rec


# ── 主流程 ───────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="USA trade_when PPA Alpha Mining")
    ap.add_argument("--min-sharpe", type=float, default=1.25, help="IS Sharpe 下限")
    ap.add_argument("--min-fitness", type=float, default=1.0, help="IS Fitness 下限")
    ap.add_argument("--field-sample", type=int, default=40, help="每个数据集最多字段数")
    ap.add_argument("--max-pairs", type=int, default=15, help="每轮双字段最多取对数")
    ap.add_argument("--prod-corr-wait", type=int, default=1800, help="等待生产相关性秒数")
    ap.add_argument("--target", type=int, default=TARGET_COUNT, help="目标命中数")
    ap.add_argument("--dataset", type=str, default=None, help="指定单个数据集 ID")
    ap.add_argument("--max-rounds", type=int, default=3, help="最大轮数")
    args = ap.parse_args()

    target = args.target

    logger.info("=" * 72)
    logger.info("USA D1 PPA | trade_when template | unlit datasets")
    logger.info("Region=%s Universe=%s Neutralization=RAM(group_neutralize) Target=%d",
                REGION, UNIVERSE, target)
    logger.info("Template: trade_when(ts_arg_max(volume,V)==0, group_zscore(group_rank(ts_sum(F1/F2,W),subindustry), ...), abs(returns)>T)")
    logger.info("=" * 72)

    api = get_api()
    rng = random.Random(42)

    # 初始化本地自相关性数据
    global _selfcorr_calc
    try:
        _selfcorr_calc = ensure_selfcorr_data(session=api.session)
        logger.info("本地自相关性数据已就绪")
    except Exception as e:
        logger.warning("本地自相关性初始化失败（不影响主流程）: %s", e)

    # 获取未点亮数据集
    if args.dataset:
        datasets = [{"id": args.dataset, "name": args.dataset, "fieldCount": 0,
                      "pyramidMultiplier": 1.0, "category": ""}]
        logger.info("使用指定数据集: %s", args.dataset)
    else:
        datasets = list_usa_unlit_datasets(api, min_fields=2)

    if not datasets:
        logger.error("未找到 pyramidMultiplier==1.0 的数据集")
        return

    logger.info("候选未点亮数据集 %d 个:", len(datasets))
    for ds in datasets[:20]:
        logger.info("  %s (%s) fields=%s pm=%.2f", ds["id"], ds["name"],
                     ds["fieldCount"], ds["pyramidMultiplier"])
    if len(datasets) > 20:
        logger.info("  ... 及另外 %d 个", len(datasets) - 20)

    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)

    found: List[Dict[str, Any]] = []
    tried: set = set()
    total_sim = 0
    rnd = 0

    while len(found) < target:
        rnd += 1
        logger.info("=== Round %d | found %d/%d | total sims %d ===", rnd, len(found), target, total_sim)

        for ds in datasets:
            if len(found) >= target:
                break

            dataset_id = ds["id"]
            fields = fetch_matrix_fields(api, dataset_id, limit=args.field_sample)
            if len(fields) < 2:
                logger.warning("数据集 %s 可用 MATRIX 字段不足 2，跳过", dataset_id)
                continue

            logger.info("数据集 %s: %d MATRIX 字段", dataset_id, len(fields))

            # ── 生成表达式 ────────────────────────────
            raw = []
            pairs = list(combinations(fields, 2))
            rng.shuffle(pairs)
            for f1, f2 in pairs[:args.max_pairs]:
                for expr in build_trade_when_expressions(f1, f2):
                    h = expr_hash(expr)
                    if h not in tried:
                        tried.add(h)
                        raw.append((expr, f1, f2))

            rng.shuffle(raw)
            logger.info("数据集 %s 本轮表达式数: %d", dataset_id, len(raw))

            if not raw:
                continue

            # 保存到 pipeline DB
            to_sim = save_pipeline_exprs_to_db(raw, rnd, dataset_id)
            if not to_sim:
                logger.info("所有表达式已在 DB 中，跳过")
                continue

            items = list(to_sim.items())
            logger.info("数据集 %s: %d 个待回测", dataset_id, len(items))

            # 并发回测
            with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS, thread_name_prefix="T") as ex:
                futs = {}
                for eh, (expr, f1, f2) in items:
                    if len(found) >= target:
                        break
                    with _found_lock:
                        total_sim += 1
                        sn = total_sim
                    futs[ex.submit(backtest_one, api, expr, f1, f2, eh,
                                   args.min_sharpe, args.min_fitness,
                                   args.prod_corr_wait, sn, dataset_id)] = (expr, f1, f2, eh)

                for fut in as_completed(futs):
                    expr, f1, f2, eh = futs[fut]
                    try:
                        rec = fut.result()
                    except Exception as e:
                        logger.warning("future err: %s", e)
                        continue

                    if rec:
                        with _found_lock:
                            found.append(rec)
                            logger.info(
                                "✅ HIT #%d/%d id=%s ds=%s corr=%.4f S=%.3f F=%.3f",
                                len(found), target, rec["platform_alpha_id"],
                                rec["dataset_id"], rec["production_correlation"],
                                rec["sharpe"], rec["fitness"],
                            )

                        try:
                            save_alpha(
                                rec["expression"],
                                f"USA_TRADEWHEN_PPA_{dataset_id}",
                                {**BACKTEST_SETTINGS, "dataset_id": dataset_id,
                                 "base_expression": expr, "field_1": f1, "field_2": f2,
                                 "template": "trade_when"},
                            )
                        except Exception:
                            pass

                        # 增量保存结果
                        with _found_lock:
                            p = os.path.join(rdir, f"usa_tradewhen_ppa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                            with open(p, "w", encoding="utf-8") as fout:
                                json.dump({
                                    "target": target, "found": len(found),
                                    "max_prod_corr": MAX_PROD_CORR,
                                    "region": REGION, "universe": UNIVERSE,
                                    "template": "trade_when",
                                    "total_simulations": total_sim,
                                    "rounds": rnd,
                                    "alphas": found,
                                }, fout, indent=2, ensure_ascii=False)
                            logger.info("saved to %s", p)

                    with _found_lock:
                        if len(found) >= target:
                            logger.info("TARGET REACHED, cancelling remaining…")
                            for fc in futs:
                                fc.cancel()
                            break

        if len(found) < target:
            logger.info("Round %d done, %d/%d found, continuing…", rnd, len(found), target)
            time.sleep(2)

        if rnd >= args.max_rounds:
            logger.warning("已扫描 %d 轮，停止。共找到 %d/%d", rnd, len(found), target)
            break

    # 最终保存
    p = os.path.join(rdir, f"usa_tradewhen_ppa_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as fout:
        json.dump({
            "target": target, "found": len(found),
            "max_prod_corr": MAX_PROD_CORR,
            "region": REGION, "universe": UNIVERSE,
            "template": "trade_when",
            "total_simulations": total_sim,
            "rounds": rnd,
            "alphas": found,
        }, fout, indent=2, ensure_ascii=False)
    logger.info("FINAL saved to %s", os.path.abspath(p))

    for i, a in enumerate(found, 1):
        logger.info("  Alpha #%d: %s [%s] S=%.3f F=%.3f PC=%.4f",
                     i, a["platform_alpha_id"], a["dataset_id"],
                     a["sharpe"], a["fitness"], a["production_correlation"])

    if len(found) >= target:
        logger.info("目标完成！共找到 %d 个 PPA 候选 alpha", len(found))
    else:
        logger.warning("仅找到 %d/%d 个，可尝试 --dataset 指定其他数据集或降低 --min-sharpe",
                       len(found), target)


if __name__ == "__main__":
    main()
