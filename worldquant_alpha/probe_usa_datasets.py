#!/usr/bin/env python3
"""
USA 数据集拥堵探测脚本（方案B）。
对每个低饱和度数据集提交极简表达式，180s内完成的标记为"可用"。
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from wd_lib.api.datasets import get_datafields, get_datasets
    from wd_lib_wrapper import get_api
except ImportError:
    from worldquant_alpha.wd_lib.api.datasets import get_datafields, get_datasets
    from worldquant_alpha.wd_lib_wrapper import get_api

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

DEFAULT_RAM_FIELD = os.environ.get("WQ_RAM_NEUTRAL_FIELD", "sta1_top3000c50")
PROBE_MAX_WAIT = 300  # 探测超时 5 分钟
PROBE_STALL_LIMIT = 180  # 停滞阈值 3 分钟


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
    rows.sort(key=lambda x: -x["fieldCount"])
    return rows


def fetch_first_matrix_field(api, dataset_id: str) -> Optional[str]:
    df = get_datafields(
        search_scope=SEARCH_SCOPE,
        dataset_id=dataset_id,
        field_type="MATRIX",
        session=_unwrap_session(api),
    )
    if df is None or df.empty:
        return None
    ids = df[df["type"] == "MATRIX"]["id"].tolist()
    return ids[0] if ids else None


def probe_dataset(api, dataset_id: str, field: str) -> Dict[str, Any]:
    """对单个数据集提交极简探测表达式，记录完成时间。"""
    expr = f"group_neutralize(rank(ts_backfill({field}, 5)), {DEFAULT_RAM_FIELD})"
    logger.info("[PROBE] %s | %s", dataset_id, expr[:80])
    t0 = time.time()
    try:
        res = api.run_backtest(
            expr,
            settings=BACKTEST_SETTINGS.copy(),
            max_wait_time=PROBE_MAX_WAIT,
            stall_limit=PROBE_STALL_LIMIT,
        )
    except Exception as e:
        elapsed = time.time() - t0
        logger.warning("[PROBE] %s 异常: %s (%.1fs)", dataset_id, e, elapsed)
        return {
            "dataset_id": dataset_id,
            "field": field,
            "status": "ERROR",
            "elapsed_sec": round(elapsed, 1),
            "error": str(e),
        }

    elapsed = time.time() - t0
    if not res or not res.get("platform_id"):
        logger.info("[PROBE] %s 超时/无结果 (%.1fs)", dataset_id, elapsed)
        return {
            "dataset_id": dataset_id,
            "field": field,
            "status": "TIMEOUT",
            "elapsed_sec": round(elapsed, 1),
        }

    sharpe = res.get("sharpe", 0)
    fitness = res.get("fitness", 0)
    logger.info(
        "[PROBE] %s 完成 (%.1fs) | S=%.3f F=%.3f",
        dataset_id, elapsed, sharpe or 0, fitness or 0,
    )
    return {
        "dataset_id": dataset_id,
        "field": field,
        "status": "OK",
        "elapsed_sec": round(elapsed, 1),
        "sharpe": sharpe,
        "fitness": fitness,
        "platform_id": res.get("platform_id"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-datasets", type=int, default=20, help="最多探测的数据集数量")
    parser.add_argument("--output", type=str, default=None, help="结果保存路径")
    args = parser.parse_args()

    logger.info("=" * 72)
    logger.info("USA D1 数据集拥堵探测 | max_wait=%ds | stall_limit=%ds", PROBE_MAX_WAIT, PROBE_STALL_LIMIT)
    logger.info("=" * 72)

    api = get_api()
    unlit = list_usa_d1_unlit_datasets(api, min_fields=2)
    if not unlit:
        logger.error("未找到未点亮数据集")
        return

    logger.info("候选数据集共 %d 个，本次探测前 %d 个", len(unlit), args.max_datasets)

    results = []
    for ds in unlit[:args.max_datasets]:
        ds_id = ds["id"]
        field = fetch_first_matrix_field(api, ds_id)
        if not field:
            logger.warning("%s 无 MATRIX 字段，跳过", ds_id)
            results.append({
                "dataset_id": ds_id,
                "field": None,
                "status": "NO_FIELDS",
                "elapsed_sec": 0,
            })
            continue
        rec = probe_dataset(api, ds_id, field)
        results.append(rec)
        # 单线程顺序执行，避免并发拥堵
        time.sleep(2)

    # 统计
    ok = [r for r in results if r["status"] == "OK"]
    timeout = [r for r in results if r["status"] == "TIMEOUT"]
    error = [r for r in results if r["status"] == "ERROR"]
    no_fields = [r for r in results if r["status"] == "NO_FIELDS"]

    logger.info("=" * 72)
    logger.info("探测完成 | OK=%d | TIMEOUT=%d | ERROR=%d | NO_FIELDS=%d", len(ok), len(timeout), len(error), len(no_fields))
    logger.info("可用数据集 (180s内完成):")
    for r in ok:
        logger.info("  - %s: %.1fs | S=%.3f F=%.3f", r["dataset_id"], r["elapsed_sec"], r.get("sharpe", 0) or 0, r.get("fitness", 0) or 0)
    logger.info("拥堵数据集 (超时/异常):")
    for r in timeout + error:
        logger.info("  - %s: %s (%.1fs)", r["dataset_id"], r["status"], r["elapsed_sec"])

    # 保存结果
    out = {
        "probe_time": datetime.now().isoformat(),
        "probe_max_wait": PROBE_MAX_WAIT,
        "probe_stall_limit": PROBE_STALL_LIMIT,
        "total": len(results),
        "ok": len(ok),
        "timeout": len(timeout),
        "error": len(error),
        "available_datasets": [r["dataset_id"] for r in ok],
        "results": results,
    }
    if args.output:
        out_path = args.output
    else:
        out_path = os.path.join(
            "results",
            f"usa_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    logger.info("结果已保存至 %s", os.path.abspath(out_path))


if __name__ == "__main__":
    main()
