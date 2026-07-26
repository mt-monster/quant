#!/usr/bin/env python3
"""Import results/*_checkpoint.json into local MySQL (idempotent)."""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

for _s in (sys.stdout, sys.stderr):
    try:
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from db_store import init_db, upsert_backtest_results, upsert_found_alphas

logger = logging.getLogger("import_ckpt")

RESULTS_DIR = os.path.join(_HERE, "results")
_TRI_RE = re.compile(r"^(.+)_tri_(.+)$")


def parse_job_dataset(stem: str, payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Derive job_id / dataset from checkpoint stem and payload."""
    m = _TRI_RE.match(stem)
    if m:
        return m.group(1), m.group(2)

    found = payload.get("found_alphas") or []
    results = payload.get("results") or []
    dataset = None
    job_id = stem
    for src in (found, results):
        for row in src:
            if not dataset and row.get("dataset"):
                dataset = row.get("dataset")
            if row.get("job"):
                job_id = row.get("job") or job_id
            if dataset and row.get("job"):
                break
        if dataset:
            break
    return job_id, dataset


def import_file(path: str) -> Tuple[int, int]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    # Legacy measure_* dumps are bare lists — wrap as results
    if isinstance(payload, list):
        payload = {"results": payload, "found_alphas": []}
    if not isinstance(payload, dict):
        raise ValueError(f"unsupported checkpoint type: {type(payload)}")
    stem = os.path.basename(path).replace("_checkpoint.json", "")
    job_id, dataset = parse_job_dataset(stem, payload)
    results = payload.get("results") or []
    found = payload.get("found_alphas") or []
    if not isinstance(results, list):
        results = []
    if not isinstance(found, list):
        found = []
    # Enrich found rows missing job/dataset
    for row in found:
        if not isinstance(row, dict):
            continue
        row.setdefault("job", job_id)
        if dataset and not row.get("dataset"):
            row["dataset"] = dataset
    n1 = upsert_backtest_results(job_id, dataset, [r for r in results if isinstance(r, dict)])
    n2 = upsert_found_alphas([r for r in found if isinstance(r, dict)])
    return n1, n2


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Import scan checkpoints into MySQL")
    ap.add_argument("--dir", default=RESULTS_DIR, help="Directory with *_checkpoint.json")
    ap.add_argument("--file", default=None, help="Import a single checkpoint file")
    args = ap.parse_args()

    if not init_db():
        logger.error("init_db failed; check DB_* in .env and that database exists")
        return 1

    if args.file:
        files = [args.file]
    else:
        files = sorted(
            os.path.join(args.dir, n)
            for n in os.listdir(args.dir)
            if n.endswith("_checkpoint.json")
        )

    if not files:
        logger.warning("No checkpoint files found under %s", args.dir)
        return 0

    total_r, total_f = 0, 0
    for path in files:
        try:
            n1, n2 = import_file(path)
            total_r += n1
            total_f += n2
            logger.info("%s -> results=%d found=%d", os.path.basename(path), n1, n2)
        except Exception as e:
            logger.warning("skip %s: %s", path, e)

    logger.info("Done files=%d results_upserts=%d found_upserts=%d", len(files), total_r, total_f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
