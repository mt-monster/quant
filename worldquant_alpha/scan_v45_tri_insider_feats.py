#!/usr/bin/env python3
"""V45: insider_feats 三轨 multi-sim (8 槽 = 3 explore + 3 improve + 2 settings-rescue).

- Explore: 新字段/骨架
- Improve: 对 V44 Top 与本轮结果做表达式突变
- Rescue: 近关候选只改 decay/neut/trunc/universe (抬 TVR/SUB)
ops<6; 禁 add/multiply/trade_when; 绝不提交.

仅含配置+表达式; simulate/checkpoint/深检由 wd_lib.scan.tri_runner 承担。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

from tri_track import select_top_candidates
from wd_lib.scan import ScanConfig, make_variant_adder, run_tri_scan

logger = logging.getLogger("v45")

DATASET = "insider_feats"
TRUNC = 0.08
SEED_CKPT = os.path.join(_HERE, "results", "v44_insider_feats_checkpoint.json")

# Explore 侧重未充分扫的字段 + 新骨架
EXPLORE_FIELDS = [
    "buy_sell_ratio_top20_60d_filled",  # V44 最强
    "buy_sell_ratio_top5_60d_filled",
    "buy_sell_ratio_all_60d_filled",
    "buy_sell_ratio_all_5d_filled",
    "buy_sell_tx_count_ratio_all_60d_filled",
    "buy_sell_ratio_all_250d_filled",
]
PAIRS = [
    ("buy_sell_ratio_top20_60d_filled", "buy_sell_ratio_all_60d_filled", "top20_vs_all"),
    ("buy_sell_ratio_all_5d_filled", "buy_sell_ratio_all_250d_filled", "bs_5_250"),
]


def build_explore_variants() -> List[Dict[str, Any]]:
    """新字段探索: 侧重短窗/backfill/高 TVR 倾向骨架."""
    variants, seen = [], set()
    add = make_variant_adder(variants, seen, default_trunc=TRUNC)

    for f in EXPLORE_FIELDS:
        short = f.replace("buy_sell_ratio_", "bsr_").replace("buy_sell_tx_count_ratio_", "bscr_").replace("_filled", "")[:16]
        for uni in ("TOP3000", "ILLIQUID_MINVOL1M"):
            for decay in (1, 2, 3):  # 低 decay 抬 TVR
                for neut in ("SECTOR", "INDUSTRY"):
                    # backfill 骨架 (V39 成功路径)
                    add(f"ex_bf_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_backfill(vec_avg({f}), 66), 189), industry))",
                        uni, decay, neut, "explore_bf", f)
                    add(f"ex_bfz_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(ts_backfill(vec_avg({f}), 66), 189))",
                        uni, decay, neut, "explore_bfz", f)
                    # 短 mean → 更高换手
                    add(f"ex_sm_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_mean(vec_avg({f}), 5), 63), industry))",
                        uni, decay, neut, "explore_short", f)
                    add(f"ex_dl_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_delta(vec_avg({f}), 5), industry))",
                        uni, decay, neut, "explore_delta", f)
                    add(f"ex_tr_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_rank(vec_avg({f}), 60))",
                        uni, decay, neut, "explore_rank", f)

    for a, b, tag in PAIRS:
        for uni in ("TOP3000",):
            for decay in (1, 2, 3):
                for neut in ("SECTOR", "INDUSTRY"):
                    add(f"ex_sp_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(subtract(vec_avg({a}), vec_avg({b})), 63))",
                        uni, decay, neut, "explore_spread", f"{a}|{b}")
                    add(f"ex_spgz_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(subtract(vec_avg({a}), vec_avg({b})), 126), industry))",
                        uni, decay, neut, "explore_spgz", f"{a}|{b}")

    logger.info("explore pool: %d", len(variants))
    return variants


def load_seed_tops() -> List[Dict[str, Any]]:
    if not os.path.exists(SEED_CKPT):
        return []
    try:
        d = json.load(open(SEED_CKPT, encoding="utf-8"))
        tops = select_top_candidates(d.get("results") or [], top_k=10, min_abs_sharpe=0.35)
        logger.info("seed tops from V44: %d", len(tops))
        for t in tops[:5]:
            logger.info("  seed S=%.3f TVR=%s %s", t.get("sharpe") or 0, t.get("tvr"), t.get("label"))
        return tops
    except Exception as e:
        logger.warning("load seed: %s", e)
        return []


# 优先 explore: 短窗/低 decay
def ex_prio(v):
    s = 0
    if "top20" in str(v.get("field")): s += 8
    if v.get("style") in ("explore_bf", "explore_short"): s += 6
    if (v.get("settings") or {}).get("decay") <= 2: s += 3
    return -s


CONFIG = ScanConfig(
    version="v45",
    dataset=DATASET,
    task_name="v45_tri_insider_feats",
    ckpt_name="v45_tri_insider_feats_checkpoint.json",
    style="insider_buy_sell_ratio_tri",
    build_explore=build_explore_variants,
    build_seeds=load_seed_tops,
    explore_priority=ex_prio,
    progress_meta={"slots": [3, 3, 2]},
)


if __name__ == "__main__":
    run_tri_scan(CONFIG)
