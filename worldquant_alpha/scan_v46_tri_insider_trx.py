#!/usr/bin/env python3
"""V46: USA D1 insider_trx_matrix 三轨 multi-sim + Token-Bucket 提交闸门.

- 数据集: insider_trx_matrix (未点亮 MATRIX, cov~0.77)
- 骨架: 移植 V39b 赢家 ts_backfill+group_zscore (无 vec_avg)
- 槽位: 3 explore / 3 improve / 2 settings-rescue
- 提交: submit_gate (≥18s 间隔, ≥45s 批间); 绝不提交 alpha
- 与 YPgAa3WR 相关需 <0.4 (收割时再验)

仅含配置+表达式; simulate/checkpoint/深检由 wd_lib.scan.tri_runner 承担。
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

from wd_lib.scan import ScanConfig, base_settings, make_variant_adder, run_tri_scan

logger = logging.getLogger("v46")

DATASET = "insider_trx_matrix"
TRUNC = 0.01
KNOWN_PID = "YPgAa3WR"  # 已有 ready，相关须 <0.4
MAX_PAIR_CORR = 0.40

# 高 cov USD 信号 + 方向分 + 买卖计数 (类比 eur_top_value)
FIELDS = [
    "usd_top_primary_signal_value",
    "usd_top_secondary_signal_value",
    "usd_top_tertiary_signal_value",
    "usd_top_quaternary_signal_value",
    "usd_primary_signal_value",
    "usd_secondary_signal_value",
    "usd_tertiary_signal_value",
    "usd_quaternary_signal_value",
    "usd_top_direct_signal_value_1",
    "usd_top_direct_signal_value_2",
    "directional_indicator_score",
    "total_top_buy_transaction_count",
    "total_top_sell_transaction_count",
    "mean_top_buy_transaction_count",
]
PAIRS = [
    ("usd_top_primary_signal_value", "usd_top_quaternary_signal_value", "buy_vs_sell_top"),
    ("usd_primary_signal_value", "usd_quaternary_signal_value", "buy_vs_sell_dir"),
    ("total_top_buy_transaction_count", "total_top_sell_transaction_count", "cnt_buy_sell"),
]


def build_explore_variants() -> List[Dict[str, Any]]:
    variants, seen = [], set()
    add = make_variant_adder(variants, seen, default_trunc=TRUNC)

    for f in FIELDS:
        short = f.replace("usd_", "").replace("_signal_value", "").replace("transaction_count", "cnt")[:18]
        for uni in ("TOP3000", "TOP2000", "ILLIQUID_MINVOL1M"):
            for decay in (2, 3, 4):
                for neut in ("SECTOR", "INDUSTRY", "SUBINDUSTRY"):
                    # V39b 赢家骨架
                    add(f"ex_bf_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))",
                        uni, decay, neut, "v39_bf", f)
                    add(f"ex_bfz_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(ts_backfill({f}, 66), 189))",
                        uni, decay, neut, "bf_z", f)
                    add(f"ex_gz_{short}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(ts_mean({f}, 22), 189), industry))",
                        uni, decay, neut, "gz_mean", f)
                    if decay == 3 and neut == "SECTOR":
                        add(f"ex_flip_{short}_{uni}_d{decay}_{neut[:3]}",
                            f"-rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))",
                            uni, decay, neut, "v39_flip", f)
                        add(f"ex_tr_{short}_{uni}_d{decay}_{neut[:3]}",
                            f"rank(ts_rank(ts_backfill({f}, 66), 126))",
                            uni, decay, neut, "ts_rank", f)

    for a, b, tag in PAIRS:
        for uni in ("TOP3000",):
            for decay in (2, 3):
                for neut in ("SECTOR", "INDUSTRY"):
                    add(f"ex_sp_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(ts_zscore(subtract(ts_backfill({a}, 66), ts_backfill({b}, 66)), 189))",
                        uni, decay, neut, "spread", f"{a}|{b}")
                    add(f"ex_spgz_{tag}_{uni}_d{decay}_{neut[:3]}",
                        f"rank(group_zscore(ts_zscore(subtract({a}, {b}), 189), industry))",
                        uni, decay, neut, "spread_gz", f"{a}|{b}")

    logger.info("explore pool: %d", len(variants))
    return variants


def seed_from_v39_template() -> List[Dict[str, Any]]:
    """用 V39b 赢家骨架+本集字段伪种子，立刻喂 Improve/Rescue."""
    seeds = []
    for f in FIELDS[:6]:
        expr = f"rank(group_zscore(ts_zscore(ts_backfill({f}, 66), 189), industry))"
        seeds.append({
            "label": f"seed_{f[:20]}",
            "expr": expr,
            "settings": base_settings("TOP3000", 3, "SECTOR", 0.01),
            "sharpe": 0.5,  # 占位，供 select/improve 用
            "field": f,
        })
    return seeds


def ex_prio(v):
    s = 0
    fld = str(v.get("field") or "")
    if "usd_top" in fld: s += 10
    if "primary" in fld or "secondary" in fld: s += 4
    if v.get("style") == "v39_bf": s += 12
    if (v.get("settings") or {}).get("universe") == "TOP3000": s += 3
    if (v.get("settings") or {}).get("neutralization") == "SECTOR": s += 3
    if (v.get("settings") or {}).get("decay") == 3: s += 2
    return -s


CONFIG = ScanConfig(
    version="v46",
    dataset=DATASET,
    task_name="v46_tri_insider_trx",
    ckpt_name="v46_tri_insider_trx_checkpoint.json",
    style="insider_trx_usd_signal",
    build_explore=build_explore_variants,
    build_seeds=seed_from_v39_template,
    explore_priority=ex_prio,
    known_pid=KNOWN_PID,
    max_pair_corr=MAX_PAIR_CORR,
    progress_meta={"submit_gate": True},
)


if __name__ == "__main__":
    run_tri_scan(CONFIG)
