#!/usr/bin/env python3
"""
USA / delay=1 / neutralization=RAM 下的「PPA 向」Alpha 挖掘（单数据集、≥2 个原始字段组合）。

要点：
- 「未点亮金字塔」：使用 data-sets 接口返回的 pyramidMultiplier == 1.0（与 BRAIN 金字塔页一致）。
- 单数据集：一次只用一个 dataset_id 的 MATRIX 字段；表达式中至少包含两个不同字段。
- 生产相关性：仅从 alphas/{id}/check 的 checks 中解析；无数值则轮询等待；>0.7 或仍无结果则绝不视为可提交。
- **严禁**向生产环境提交：本脚本不包含 submit 调用；请勿在未满足相关性条件时手动提交。

模拟类型：使用平台标准 REGULAR 回测（FASTEXPR）。PPA 任务通常仍要求 USA+D1+RAM 等设置，奖励侧由「未点亮数据集」体现。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
from datetime import datetime
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

try:
    from wd_lib.api.datasets import get_datafields, get_datasets
    from wd_lib_wrapper import get_api
    from database import save_alpha, alpha_exists
except ImportError:
    from worldquant_alpha.wd_lib.api.datasets import get_datafields, get_datasets
    from worldquant_alpha.wd_lib_wrapper import get_api
    from worldquant_alpha.database import save_alpha, alpha_exists

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SEARCH_SCOPE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "delay": 1,
    "universe": "TOP3000",
}

# 平台 simulations API 不接受 settings.neutralization="RAM"，需 NONE + 表达式侧 group_neutralize（RAM 语义）
DEFAULT_RAM_FIELD = os.environ.get("WQ_RAM_NEUTRAL_FIELD", "sta1_top3000c50")

BACKTEST_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
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

MAX_PROD_CORR = 0.7
TARGET_COUNT = 2
# 生产相关性常见名称（平台可能调整文案，多匹配）
_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION",
    "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION",
    "PRODUCTION_CORR",
)


def _unwrap_session(api) -> Any:
    return api.session


def list_usa_d1_unlit_datasets(api, min_fields: int = 2) -> List[Dict[str, Any]]:
    """pyramidMultiplier==1.0 且字段数足够的 USA D1 数据集。"""
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
        if pm >= 1.0 - 1e-9 and pm <= 1.0 + 1e-9 and fc >= min_fields:
            rows.append(
                {
                    "id": r["id"],
                    "name": r.get("name", ""),
                    "fieldCount": fc,
                    "category": (r.get("category") or {}).get("id", ""),
                }
            )
    # 字段多的优先，便于组合
    rows.sort(key=lambda x: -x["fieldCount"])
    return rows


def fetch_matrix_fields(api, dataset_id: str, limit: int = 40) -> List[str]:
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


def field_wrap(f: str) -> str:
    return f"winsorize(ts_backfill({f}, 63), std=4)"


def apply_ram_neutralization(expr: str, ram_field: str) -> str:
    if "group_neutralize(" in expr:
        return expr
    return f"group_neutralize({expr}, {ram_field})"


def build_two_field_expressions(f1: str, f2: str) -> List[str]:
    """同一数据集内两个字段；每条表达式均使用 f1、f2。"""
    a, b = field_wrap(f1), field_wrap(f2)
    out = [
        f"rank(subtract({a}, {b}))",
        f"rank(divide({a}, abs({b}) + 0.01))",
        f"rank(ts_corr({a}, {b}, 10))",
        f"rank(ts_corr({a}, {b}, 20))",
        f"rank(ts_corr({a}, {b}, 60))",
        f"rank(add(ts_rank({a}, 22), ts_rank({b}, 22)))",
    ]
    return out


def iter_expression_batch(
    fields: List[str], max_pairs: int, rng: random.Random
) -> List[str]:
    pairs = list(combinations(fields, 2))
    rng.shuffle(pairs)
    pairs = pairs[:max_pairs]
    exprs: List[str] = []
    for f1, f2 in pairs:
        exprs.extend(build_two_field_expressions(f1, f2))
    return exprs


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
    # 部分返回用嵌套字段
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
    """无结果则返回 None（禁止当作可提交）。"""
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        ch = api.get_alpha_check(platform_alpha_id)
        corr = parse_production_correlation(ch)
        if corr is not None:
            return corr
        logger.info(
            "生产相关性尚未出现在 check 中，%ss 后重试… (%s)",
            poll_s,
            platform_alpha_id,
        )
        time.sleep(poll_s)
    return None


def passes_submission_shape(
    api, platform_alpha_id: str, min_sharpe: float, min_fitness: float
) -> Tuple[bool, float, float]:
    """基础 IS 门槛（可按需调）。"""
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
    parser.add_argument(
        "--min-sharpe", type=float, default=1.25, help="IS Sharpe 下限（挖掘用）"
    )
    parser.add_argument(
        "--min-fitness", type=float, default=1.0, help="IS Fitness 下限（挖掘用）"
    )
    parser.add_argument(
        "--max-pairs-per-dataset",
        type=int,
        default=12,
        help="每个数据集每轮最多尝试的字段对数量",
    )
    parser.add_argument(
        "--field-sample",
        type=int,
        default=30,
        help="每个数据集最多拉取的 MATRIX 字段数（用于组合）",
    )
    parser.add_argument(
        "--max-total-simulations",
        type=int,
        default=0,
        help="总回测次数上限，0 表示不限制（直到找到 2 个）",
    )
    parser.add_argument(
        "--prod-corr-wait",
        type=int,
        default=1800,
        help="等待生产相关性出现的最大秒数",
    )
    parser.add_argument(
        "--ram-neutral-field",
        type=str,
        default=DEFAULT_RAM_FIELD,
        help="RAM 语义：group_neutralize 第二参数（USA，默认 sta1_top3000c50，可用环境变量 WQ_RAM_NEUTRAL_FIELD）",
    )
    args = parser.parse_args()

    logger.info("=" * 72)
    logger.info("USA D1 RAM 挖掘 | 未点亮数据集 pyramidMultiplier==1.0 | 双字段组合")
    logger.info("本脚本不会调用生产提交 API。")
    logger.info("=" * 72)

    api = get_api()
    rng = random.Random(42)

    unlit = list_usa_d1_unlit_datasets(api, min_fields=2)
    if not unlit:
        logger.error("未找到 pyramidMultiplier==1.0 的数据集，请检查网络或凭证。")
        return

    logger.info(
        "候选未点亮数据集 %s 个: %s",
        len(unlit),
        [x["id"] for x in unlit[:15]] + (["..."] if len(unlit) > 15 else []),
    )

    found: List[Dict[str, Any]] = []
    total_sim = 0
    ds_idx = 0

    while len(found) < TARGET_COUNT:
        if args.max_total_simulations and total_sim >= args.max_total_simulations:
            logger.warning(
                "已达总回测上限 %s，停止（已找到 %s 个符合条件的 alpha）。",
                args.max_total_simulations,
                len(found),
            )
            break

        ds = unlit[ds_idx % len(unlit)]
        ds_idx += 1
        dataset_id = ds["id"]
        fields = fetch_matrix_fields(api, dataset_id, limit=args.field_sample)
        if len(fields) < 2:
            logger.warning("数据集 %s 可用 MATRIX 字段不足，跳过", dataset_id)
            continue

        expressions = iter_expression_batch(
            fields, max_pairs=args.max_pairs_per_dataset, rng=rng
        )
        logger.info(
            "数据集 %s (%s fields) 本轮表达式数 %s",
            dataset_id,
            len(fields),
            len(expressions),
        )

        for expr in expressions:
            if len(found) >= TARGET_COUNT:
                break
            if args.max_total_simulations and total_sim >= args.max_total_simulations:
                break

            try:
                if alpha_exists(expr):
                    continue
            except Exception as ex:
                logger.debug("alpha_exists 跳过（数据库表可能未初始化）: %s", ex)

            total_sim += 1
            ram_expr = apply_ram_neutralization(expr, args.ram_neutral_field)
            logger.info("回测 #%s [%s] %s…", total_sim, dataset_id, ram_expr[:90])

            res = api.run_backtest(ram_expr, settings=BACKTEST_SETTINGS.copy())
            if not res:
                continue
            platform_id = res.get("platform_id")
            if not platform_id:
                continue

            ok, sharpe, fitness = passes_submission_shape(
                api, platform_id, args.min_sharpe, args.min_fitness
            )
            if not ok:
                logger.info("IS 未达标 Sharpe=%s fitness=%s，跳过", sharpe, fitness)
                continue

            prod_corr = wait_for_production_correlation(
                api, platform_id, max_wait_s=args.prod_corr_wait
            )
            if prod_corr is None:
                logger.warning(
                    "平台 alpha %s 在 %ss 内仍无生产相关性结果 — 按规则不收录、严禁提交。",
                    platform_id,
                    args.prod_corr_wait,
                )
                continue
            if prod_corr > MAX_PROD_CORR:
                logger.info(
                    "生产相关性 %.4f > %.2f，跳过（禁止提交）", prod_corr, MAX_PROD_CORR
                )
                continue

            rec = {
                "platform_alpha_id": platform_id,
                "dataset_id": dataset_id,
                "expression": ram_expr,
                "base_two_field_expression": expr,
                "ram_neutral_field": args.ram_neutral_field,
                "sharpe": sharpe,
                "fitness": fitness,
                "production_correlation": prod_corr,
                "found_at": datetime.now().isoformat(),
            }
            found.append(rec)
            logger.info(
                "✅ 命中 #%s platform=%s prod_corr=%.4f Sharpe=%.3f fitness=%.3f",
                len(found),
                platform_id,
                prod_corr,
                sharpe,
                fitness,
            )

            try:
                save_alpha(
                    ram_expr,
                    f"USA_RAM_PPA_UNLIT_{dataset_id}",
                    {
                        **BACKTEST_SETTINGS,
                        "dataset_id": dataset_id,
                        "ram_neutral_field": args.ram_neutral_field,
                        "base_expression": expr,
                    },
                )
            except Exception as ex:
                logger.warning("写入数据库失败（可忽略）: %s", ex)

    os.makedirs("results", exist_ok=True)
    out_path = os.path.join(
        "results",
        f"usa_ram_ppa_unlit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "target": TARGET_COUNT,
                "found": len(found),
                "max_prod_corr": MAX_PROD_CORR,
                "alphas": found,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("已写入 %s", os.path.abspath(out_path))

    if len(found) < TARGET_COUNT:
        logger.warning(
            "当前仅找到 %s / %s 个满足条件的 alpha，可增大 --max-total-simulations 或多轮运行。",
            len(found),
            TARGET_COUNT,
        )
    else:
        logger.info("已找到 %s 个可提交候选（请自行在平台确认后提交；相关性>0.7 勿提交）。", TARGET_COUNT)


if __name__ == "__main__":
    main()
