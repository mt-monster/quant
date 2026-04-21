#!/usr/bin/env python3
"""
平台拥堵监控脚本。
每 INTERVAL 分钟测试一次最简单的表达式，记录完成时间。
当完成时间 < RECOVER_THRESHOLD 秒时，视为平台恢复。
"""
from __future__ import annotations
import json
import logging
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from wd_lib_wrapper import get_api
except ImportError:
    from worldquant_alpha.wd_lib_wrapper import get_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 配置
PROBE_EXPR = "group_neutralize(rank(subtract(close, open)), sta1_top3000c50)"
SETTINGS = {
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
MAX_WAIT = 300  # 单次探测最多等 5 分钟
STALL_LIMIT = 180  # 3 分钟无进展视为卡住
INTERVAL_MIN = 30  # 每 30 分钟探测一次
RECOVER_THRESHOLD = 180  # 完成时间 < 180s 视为恢复


def probe_once(api) -> dict:
    """提交一次极简探测，记录耗时和结果。"""
    logger.info("[PROBE] Submitting: %s", PROBE_EXPR)
    t0 = time.time()
    try:
        res = api.run_backtest(
            PROBE_EXPR,
            settings=SETTINGS.copy(),
            max_wait_time=MAX_WAIT,
            stall_limit=STALL_LIMIT,
        )
    except Exception as e:
        elapsed = time.time() - t0
        logger.error("[PROBE] Exception after %.1fs: %s", elapsed, e)
        return {
            "timestamp": datetime.now().isoformat(),
            "elapsed_sec": round(elapsed, 1),
            "status": "ERROR",
            "error": str(e),
        }

    elapsed = time.time() - t0
    if not res or not res.get("platform_id"):
        logger.warning("[PROBE] TIMEOUT after %.1fs", elapsed)
        return {
            "timestamp": datetime.now().isoformat(),
            "elapsed_sec": round(elapsed, 1),
            "status": "TIMEOUT",
        }

    sharpe = res.get("sharpe")
    fitness = res.get("fitness")
    logger.info(
        "[PROBE] OK after %.1fs | S=%s F=%s | id=%s",
        elapsed, sharpe, fitness, res.get("platform_id"),
    )
    return {
        "timestamp": datetime.now().isoformat(),
        "elapsed_sec": round(elapsed, 1),
        "status": "OK",
        "sharpe": sharpe,
        "fitness": fitness,
        "platform_id": res.get("platform_id"),
    }


def main() -> None:
    api = get_api()
    history = []
    consecutive_timeout = 0

    logger.info("=" * 72)
    logger.info("Platform congestion monitor started")
    logger.info("Probe interval: %d min | Recovery threshold: %ds", INTERVAL_MIN, RECOVER_THRESHOLD)
    logger.info("=" * 72)

    while True:
        rec = probe_once(api)
        history.append(rec)

        # 保存历史记录
        out_path = os.path.join(
            "results", f"platform_monitor_{datetime.now().strftime('%Y%m%d')}.json"
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        if rec["status"] == "OK" and rec["elapsed_sec"] < RECOVER_THRESHOLD:
            logger.info("=" * 72)
            logger.info(
                "PLATFORM RECOVERED! Elapsed=%.1fs < %ds threshold. Ready to mine.",
                rec["elapsed_sec"], RECOVER_THRESHOLD,
            )
            logger.info("=" * 72)
            consecutive_timeout = 0
            # 继续监控，不退出
        elif rec["status"] in ("TIMEOUT", "ERROR"):
            consecutive_timeout += 1
            logger.info(
                "Platform still congested (%d consecutive failures). Next probe in %d min.",
                consecutive_timeout, INTERVAL_MIN,
            )
        else:
            # OK but slower than threshold
            logger.info(
                "Platform partially recovered (%.1fs) but still above %ds threshold. Next probe in %d min.",
                rec["elapsed_sec"], RECOVER_THRESHOLD, INTERVAL_MIN,
            )
            consecutive_timeout = 0

        time.sleep(INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
