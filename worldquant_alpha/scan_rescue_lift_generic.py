#!/usr/bin/env python3
"""通用抬 S/F 救援 (B 类近关): 少平滑 + 略低 decay。

用法:
  python -u scan_rescue_lift_generic.py --dataset forum_sentiment --field common_word_frequency_count
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# 复用 R3 实现: 通过环境/猴子补丁字段过重, 直接复制核心太长 — 调 R3 模块级常量
import scan_rescue_r3_web_lift as r3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--field", required=True)
    ap.add_argument("--ckpt", default="")
    args = ap.parse_args()

    r3.DATASET = args.dataset
    r3.FIELD = args.field
    if args.ckpt:
        r3.CKPT = args.ckpt
    else:
        tag = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in args.dataset.lower())[:28]
        r3.CKPT = os.path.join(_HERE, "results", f"rescue_auto_{tag}_lift_checkpoint.json")

    # build_variants / harvest 用模块级 FIELD/DATASET/CKPT
    r3.main = r3.main  # keep
    # 重写 argv 让 r3.main 的 --ckpt 生效
    sys.argv = ["scan_rescue_r3_web_lift.py", "--ckpt", r3.CKPT]
    r3.logger.info("GENERIC lift-SF dataset=%s field=%s ckpt=%s", r3.DATASET, r3.FIELD, r3.CKPT)
    r3.main()


if __name__ == "__main__":
    main()
