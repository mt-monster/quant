#!/usr/bin/env python3
"""
USA / delay=1 / RAM PPA Alpha 挖掘 —— 内置字段版（应对自定义数据集拥堵）。
使用 close/open/high/low/volume/returns/vwap/cap 等内置字段，
这些字段在平台拥堵时仍能较快完成 simulation（已验证 ~100s）。
"""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from wd_lib_wrapper import get_api
    from database import (
        save_alpha, alpha_exists,
        get_session, save_pipeline_alphas, update_pipeline_alpha_backtest, get_pipeline_alpha_by_hash
    )
except ImportError:
    from worldquant_alpha.wd_lib_wrapper import get_api
    from worldquant_alpha.database import (
        save_alpha, alpha_exists,
        get_session, save_pipeline_alphas, update_pipeline_alpha_backtest, get_pipeline_alpha_by_hash
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_RAM_FIELD = os.environ.get("WQ_RAM_NEUTRAL_FIELD", "sta1_top3000c50")

BACKTEST_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 4,
    "neutralization": "NONE",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P0Y",
}

MAX_PROD_CORR = 0.7
TARGET_COUNT = 2

# 内置字段池
BUILTIN_FIELDS = ["close", "open", "high", "low", "volume", "returns", "vwap", "cap"]

# 生产相关性常见名称
_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION", "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION", "PRODUCTION_CORR",
)


def apply_ram_neutralization(expr: str, ram_field: str = DEFAULT_RAM_FIELD) -> str:
    if "group_neutralize(" in expr:
        return expr
    return f"group_neutralize({expr}, {ram_field})"


def build_builtin_expressions() -> List[str]:
    """生成内置字段的经典 price/volume alpha 表达式。"""
    exprs = []

    # ===== 第1批：最简单，无历史数据，当天即可完成 =====
    # 这些在平台轻度拥堵时曾在 ~100s 完成
    simple = [
        "rank(subtract(close, open))",
        "rank(subtract(high, low))",
        "rank(divide(close, vwap))",
        "zscore(subtract(close, open))",
        "rank(subtract(open, close))",  # reverse
        "rank(divide(subtract(close, open), subtract(high, low) + 0.01))",
    ]

    # ===== 第2批：短窗口时序（1-5天） =====
    short_ts = []
    for field in ["close", "volume", "returns"]:
        for window in [1, 2, 3, 5]:
            short_ts.append(f"rank(ts_delta({field}, {window}))")
            short_ts.append(f"zscore(ts_delta({field}, {window}))")
            short_ts.append(f"rank(ts_returns({field}, {window}))")
    short_ts.append("rank(ts_corr(close, volume, 5))")
    short_ts.append("rank(ts_corr(returns, volume, 5))")
    short_ts.append("rank(divide(volume, ts_mean(volume, 5) + 1))")
    short_ts.append("rank(subtract(close, ts_delay(close, 5)))")
    short_ts.append("rank(divide(ts_std_dev(returns, 5), ts_std_dev(returns, 20) + 0.01))")

    # ===== 第3批：中等窗口（10-20天） =====
    medium_ts = []
    for field in ["close", "volume", "returns", "vwap"]:
        for window in [10, 20]:
            medium_ts.append(f"rank(ts_delta({field}, {window}))")
            medium_ts.append(f"zscore(ts_delta({field}, {window}))")
            medium_ts.append(f"rank(ts_returns({field}, {window}))")
            medium_ts.append(f"rank(ts_mean({field}, {window}))")
        medium_ts.append(f"rank(ts_std_dev({field}, 20))")
    medium_ts.append("rank(ts_corr(close, volume, 20))")
    medium_ts.append("rank(ts_corr(returns, volume, 20))")
    medium_ts.append("rank(divide(volume, ts_mean(volume, 20) + 1))")
    medium_ts.append("rank(subtract(close, ts_mean(close, 20)))")
    medium_ts.append("zscore(subtract(close, ts_mean(close, 20)))")
    medium_ts.append("rank(ts_regression(returns, volume, 20, lag=0, rettype=2))")
    medium_ts.append("rank(ts_regression(close, volume, 20, lag=0, rettype=2))")

    # ===== 第4批：长窗口（60天） =====
    long_ts = []
    for field in ["close", "volume", "returns"]:
        long_ts.append(f"rank(ts_std_dev({field}, 60))")
        long_ts.append(f"rank(ts_mean({field}, 60))")
        long_ts.append(f"rank(ts_returns({field}, 60))")

    # ===== 第5批：组合 =====
    combo = [
        "rank(subtract(ts_corr(close, volume, 20), ts_corr(open, volume, 20)))",
        "rank(divide(ts_delta(close, 5), abs(ts_delta(open, 5)) + 0.01))",
    ]

    exprs = simple + short_ts + medium_ts + long_ts + combo
    return list(dict.fromkeys(exprs))  # 去重，保持优先级顺序


def parse_production_correlation(check_payload: Dict[str, Any]) -> Optional[float]:
    if not check_payload:
        return None
    checks = (check_payload.get("is") or {}).get("checks") or []
    for c in checks:
        name = (c.get("name") or "").upper()
        if any(k in name for k in _PROD_CORR_NAMES):
            v = c.get("value")
            if v is None:
                return None
            try:
                return abs(float(v))
            except (TypeError, ValueError):
                return None
    for c in checks:
        if "PRODUCTION" in (c.get("name") or "").upper():
            v = c.get("value")
            if v is not None:
                try:
                    return abs(float(v))
                except (TypeError, ValueError):
                    pass
    return None


def wait_for_production_correlation(
    api, platform_alpha_id: str, max_wait_s: int = 1800, poll_s: int = 25
) -> Optional[float]:
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        ch = api.get_alpha_check(platform_alpha_id)
        corr = parse_production_correlation(ch)
        if corr is not None:
            return corr
        logger.info("Production correlation not ready, %ss retry... (%s)", poll_s, platform_alpha_id)
        time.sleep(poll_s)
    return None


def passes_submission_shape(
    api, platform_alpha_id: str, min_sharpe: float, min_fitness: float
) -> Tuple[bool, float, float]:
    det = api.get_alpha_details(platform_alpha_id)
    is_ = det.get("is") or {}
    try:
        sharpe = float(is_.get("sharpe") or 0)
        fitness = float(is_.get("fitness") or 0)
    except (TypeError, ValueError):
        return False, 0.0, 0.0
    if sharpe < min_sharpe or fitness < min_fitness:
        return False, sharpe, fitness
    return True, sharpe, fitness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-sharpe", type=float, default=1.58, help="IS Sharpe threshold")
    parser.add_argument("--min-fitness", type=float, default=1.0, help="IS Fitness threshold")
    parser.add_argument("--prod-corr-wait", type=int, default=600, help="max wait for prod corr")
    parser.add_argument("--max-sim", type=int, default=0, help="max simulations, 0=unlimited")
    args = parser.parse_args()
    if args.max_sim == 0:
        logger.info("Max sim = 0 (unlimited) — will run until %d alphas found", TARGET_COUNT)

    logger.info("=" * 72)
    logger.info("USA D1 RAM PPA mining | BUILTIN FIELDS | target=%d", TARGET_COUNT)
    logger.info("=" * 72)

    api = get_api()
    expressions = build_builtin_expressions()
    logger.info("Built %d unique expressions from builtin fields", len(expressions))

    # 生成 RAM 表达式（实际回测用的）
    ram_expressions = [apply_ram_neutralization(e) for e in expressions]

    # 初始化 pipeline_alphas 数据库会话
    db_session = get_session()
    # 预先将所有 RAM 表达式保存到 pipeline_alphas（跳过已存在的）
    save_pipeline_alphas(
        db_session,
        ram_expressions,
        order=1,
        stage="usa_ram_ppa_builtin",
        settings=BACKTEST_SETTINGS,
    )
    logger.info("Saved expressions to pipeline_alphas")

    found = []
    total_sim = 0

    for idx, expr in enumerate(expressions):
        if len(found) >= TARGET_COUNT:
            break
        if args.max_sim and total_sim >= args.max_sim:
            logger.warning("Reached max simulation limit %d", args.max_sim)
            break

        ram_expr = ram_expressions[idx]
        total_sim += 1
        logger.info("SIM #%d | %s...", total_sim, ram_expr[:80])

        # 计算表达式 hash 用于更新 pipeline_alphas
        expr_hash = hashlib.sha256(ram_expr.encode()).hexdigest()

        try:
            res = api.run_backtest(
                ram_expr,
                settings=BACKTEST_SETTINGS.copy(),
                max_wait_time=600,
                stall_limit=300,
            )
        except Exception as e:
            logger.warning("Backtest error: %s", e)
            # 更新 pipeline_alphas 为失败状态
            try:
                update_pipeline_alpha_backtest(
                    db_session, expr_hash,
                    is_tested=True, backtest_status='failed',
                    error_message=str(e), backtested_at=datetime.now()
                )
            except Exception as db_err:
                logger.warning("Update pipeline_alpha error: %s", db_err)
            continue

        if not res or not res.get("platform_id"):
            # 更新 pipeline_alphas 为失败状态（无 platform_id）
            try:
                update_pipeline_alpha_backtest(
                    db_session, expr_hash,
                    is_tested=True, backtest_status='failed',
                    error_message="No platform_id returned", backtested_at=datetime.now()
                )
            except Exception as db_err:
                logger.warning("Update pipeline_alpha error: %s", db_err)
            continue

        pid = res["platform_id"]
        ok, sharpe, fitness = passes_submission_shape(api, pid, args.min_sharpe, args.min_fitness)
        if not ok:
            logger.info("IS fail S=%.3f F=%.3f", sharpe, fitness)
            # 更新 pipeline_alphas 为完成状态（IS 未通过）
            try:
                update_pipeline_alpha_backtest(
                    db_session, expr_hash,
                    is_tested=True, backtest_status='completed',
                    platform_alpha_id=pid, sharpe=sharpe, fitness=fitness,
                    backtested_at=datetime.now()
                )
            except Exception as db_err:
                logger.warning("Update pipeline_alpha error: %s", db_err)
            continue

        logger.info("IS ok S=%.3f F=%.3f, waiting prod corr...", sharpe, fitness)
        pc = wait_for_production_correlation(api, pid, max_wait_s=args.prod_corr_wait)
        if pc is None:
            logger.warning("No prod corr for %s", pid)
            continue
        if pc > MAX_PROD_CORR:
            logger.info("Prod corr %.4f > %.2f, skip", pc, MAX_PROD_CORR)
            continue

        rec = {
            "platform_alpha_id": pid,
            "expression": expr,
            "ram_expression": ram_expr,
            "sharpe": sharpe,
            "fitness": fitness,
            "production_correlation": pc,
            "found_at": datetime.now().isoformat(),
            "simulation_number": total_sim,
        }
        found.append(rec)
        logger.info(
            "HIT #%d/%d id=%s corr=%.4f S=%.3f F=%.3f",
            len(found), TARGET_COUNT, pid, pc, sharpe, fitness,
        )

        # 更新 pipeline_alphas 为候选状态
        try:
            update_pipeline_alpha_backtest(
                db_session, expr_hash,
                is_tested=True, backtest_status='completed',
                platform_alpha_id=pid, sharpe=sharpe, fitness=fitness,
                candidate_status='candidate', backtested_at=datetime.now()
            )
        except Exception as db_err:
            logger.warning("Update pipeline_alpha error: %s", db_err)

        try:
            save_alpha(
                rec["expression"],
                "USA_RAM_PPA_BUILTIN",
                {**BACKTEST_SETTINGS, "type": "builtin"},
            )
        except Exception as ex:
            logger.warning("Save db error: %s", ex)

    # Save results
    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)
    p = os.path.join(rdir, f"usa_ram_ppa_builtin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as fout:
        json.dump(
            {
                "target": TARGET_COUNT,
                "found": len(found),
                "max_prod_corr": MAX_PROD_CORR,
                "total_simulations": total_sim,
                "alphas": found,
            },
            fout,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("Saved to %s", os.path.abspath(p))
    for i, a in enumerate(found, 1):
        logger.info(
            "  Alpha #%d: %s S=%.3f F=%.3f PC=%.4f",
            i, a["platform_alpha_id"], a["sharpe"], a["fitness"], a["production_correlation"],
        )


if __name__ == "__main__":
    main()
