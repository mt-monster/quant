#!/usr/bin/env python3
"""
USA / delay=1 / RAM PPA Alpha 挖掘 —— snt21 (sentiment21) 数据集版。
基于历史最佳表现：pipeline_bak_0417 中 USA RAM 最高 sharpe=1.71 (snt21)。
尝试历史最佳表达式 + 变体（不同 decay / truncation / 窗口）。
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

# snt21 fields discovered from pipeline_bak_0417
SNT21_FIELDS = [
    "snt21_neg_median",
    "snt21_pos_mean",
    "snt21_2neg_median",
    "snt21_2pos_max",
    "snt21_2pos_mean",
    "snt21_3neut_median_261",
    "snt21_3pos_mean_266",
    "snt21_5neg_median",
    "snt21_5pos_mean_212",
]

_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION", "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION", "PRODUCTION_CORR",
)


def apply_ram_neutralization(expr: str, ram_field: str = DEFAULT_RAM_FIELD) -> str:
    if "group_neutralize(" in expr:
        return expr
    return f"group_neutralize({expr}, {ram_field})"


def build_snt21_expressions() -> List[Tuple[str, dict]]:
    """
    生成 snt21 表达式 + 对应的 settings 覆盖。
    返回 (expression, settings_override) 列表。
    """
    exprs = []

    # ===== 第1批：历史最佳表达式的精确复刻 + decay 变体 =====
    # 历史最佳: S=1.71 F=0.51, decay=0, truncation=0.0
    best_expr_winsorize = (
        "-1 * rank(ts_zscore(subtract("
        "winsorize(ts_backfill(snt21_2pos_max, 252), std=4), "
        "winsorize(ts_backfill(snt21_2neg_median, 252), std=4)"
        "), 66))"
    )
    # 历史次佳: S=1.65 F=0.48
    best2_expr_winsorize = (
        "-1 * rank(ts_zscore(subtract("
        "winsorize(ts_backfill(snt21_2pos_mean, 252), std=4), "
        "winsorize(ts_backfill(snt21_2neg_median_161, 252), std=4)"
        "), 66))"
    )

    # 历史最佳用了 decay=0, truncation=0.0。尝试不同组合：
    for decay in [0, 4, 6]:
        for trunc in [0.0, 0.08]:
            settings = {"decay": decay, "truncation": trunc}
            exprs.append((best_expr_winsorize, settings))
            exprs.append((best2_expr_winsorize, settings))

    # ===== 第2批：简化版（去掉 winsorize，更可能通过拥堵期） =====
    # 核心逻辑: pos_sentiment - neg_sentiment
    simple_pairs = [
        ("snt21_pos_mean", "snt21_neg_median"),
        ("snt21_2pos_max", "snt21_2neg_median"),
        ("snt21_2pos_mean", "snt21_2neg_median"),
        ("snt21_3pos_mean_266", "snt21_3neut_median_261"),
        ("snt21_5pos_mean_212", "snt21_5neg_median"),
    ]
    for pos_f, neg_f in simple_pairs:
        for window in [66, 126, 252]:
            # 最简形式
            exprs.append((
                f"rank(ts_zscore(subtract(ts_backfill({pos_f}, 252), ts_backfill({neg_f}, 252)), {window}))",
                {"decay": 4, "truncation": 0.08}
            ))
            # 带 -1 反转
            exprs.append((
                f"-1 * rank(ts_zscore(subtract(ts_backfill({pos_f}, 252), ts_backfill({neg_f}, 252)), {window}))",
                {"decay": 4, "truncation": 0.08}
            ))
            # ts_rank 变体
            exprs.append((
                f"ts_rank(subtract(ts_backfill({pos_f}, 252), ts_backfill({neg_f}, 252)), {window})",
                {"decay": 10, "truncation": 0.08}
            ))
            # zscore 变体
            exprs.append((
                f"zscore(subtract(ts_backfill({pos_f}, 252), ts_backfill({neg_f}, 252)), {window})",
                {"decay": 6, "truncation": 0.08}
            ))

    # ===== 第3批：ratio 变体 =====
    for pos_f, neg_f in simple_pairs[:3]:
        for window in [66, 126]:
            exprs.append((
                f"rank(ts_zscore(divide(ts_backfill({pos_f}, 252), add(abs(ts_backfill({neg_f}, 252)), 0.01)), {window}))",
                {"decay": 4, "truncation": 0.08}
            ))
            exprs.append((
                f"-1 * rank(ts_zscore(divide(ts_backfill({pos_f}, 252), add(abs(ts_backfill({neg_f}, 252)), 0.01)), {window}))",
                {"decay": 4, "truncation": 0.08}
            ))

    # ===== 第4批：signed_power 变体（pipeline_bak_0419 中表现好） =====
    for pos_f, neg_f in simple_pairs[:3]:
        for window in [66, 126]:
            exprs.append((
                f"signed_power(rank(ts_zscore(subtract(ts_backfill({pos_f}, 252), ts_backfill({neg_f}, 252)), {window})), 2)",
                {"decay": 6, "truncation": 0.08}
            ))

    # 去重
    seen = set()
    unique = []
    for expr, settings in exprs:
        key = expr + str(settings)
        if key not in seen:
            seen.add(key)
            unique.append((expr, settings))
    return unique


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
    logger.info("USA D1 RAM PPA mining | SNT21 DATASET | target=%d", TARGET_COUNT)
    logger.info("=" * 72)

    api = get_api()
    expressions = build_snt21_expressions()
    logger.info("Built %d unique snt21 expressions", len(expressions))

    # 生成 RAM 表达式（实际回测用的）
    ram_expressions = [apply_ram_neutralization(e) for e, _ in expressions]

    # 初始化 pipeline_alphas 数据库会话
    db_session = get_session()
    # 预先将所有 RAM 表达式保存到 pipeline_alphas（跳过已存在的）
    save_pipeline_alphas(
        db_session,
        ram_expressions,
        order=1,
        stage="usa_ram_ppa_snt21",
        settings=BACKTEST_SETTINGS,
        dataset_id="snt21",
    )
    logger.info("Saved expressions to pipeline_alphas")

    found = []
    total_sim = 0

    for idx, (expr, settings_override) in enumerate(expressions):
        if len(found) >= TARGET_COUNT:
            break
        if args.max_sim and total_sim >= args.max_sim:
            logger.warning("Reached max simulation limit %d", args.max_sim)
            break

        ram_expr = ram_expressions[idx]
        total_sim += 1

        # 合并 settings
        sim_settings = BACKTEST_SETTINGS.copy()
        sim_settings.update(settings_override)

        logger.info("SIM #%d | decay=%d trunc=%.2f | %s...", total_sim,
                    sim_settings["decay"], sim_settings["truncation"], ram_expr[:80])

        # 计算表达式 hash 用于更新 pipeline_alphas
        expr_hash = hashlib.sha256(ram_expr.encode()).hexdigest()

        try:
            res = api.run_backtest(
                ram_expr,
                settings=sim_settings,
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
            "settings_override": settings_override,
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
                "USA_RAM_PPA_SNT21",
                {**sim_settings, "type": "snt21"},
            )
        except Exception as ex:
            logger.warning("Save db error: %s", ex)

    # Save results
    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)
    p = os.path.join(rdir, f"usa_ram_ppa_snt21_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
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
