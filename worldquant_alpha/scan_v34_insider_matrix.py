#!/usr/bin/env python3
"""V34 v1 已弃用 — 假 multi（线程池单 sim）。

请改用:
  python scan_v34_insider_matrix_v2.py

公共模块:
  from multi_sim import run_multi_batch, chunked

约定:
  .cursor/rules/brain-multi-sim.mdc
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v34")


def main():
    logger.error(
        "scan_v34_insider_matrix.py (v1) 已弃用：禁止线程池单 sim。"
        "请运行: python scan_v34_insider_matrix_v2.py"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
