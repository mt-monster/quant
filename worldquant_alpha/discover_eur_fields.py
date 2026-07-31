#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取 EUR/D1/TOP2500 指定数据集全部字段, 按覆盖率排序.

输出: results/eur_fields_<dataset>.json
"""
import sys, os, json, logging

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("eur_fields")

from wd_lib_wrapper import WqApiSimple

API = "https://api.worldquantbrain.com"
DATASETS = sys.argv[1:] or ["risk62"]


def pull(s, ds):
    rows, offset = [], 0
    while True:
        r = s.get(f"{API}/data-fields", params={
            "instrumentType": "EQUITY", "region": "EUR", "delay": 1,
            "universe": "TOP2500", "dataset.id": ds, "limit": 50, "offset": offset,
        }, timeout=60)
        if not r.ok:
            logger.warning("%s offset=%d HTTP %s", ds, offset, r.status_code)
            import time; time.sleep(5)
            continue
        j = r.json()
        res = j.get("results") or []
        rows.extend(res)
        offset += 50
        if offset >= j.get("count", 0) or not res:
            break
    return rows


def main():
    api = WqApiSimple()
    s = api.session
    for ds in DATASETS:
        rows = pull(s, ds)
        items = [{
            "id": f.get("id"), "type": f.get("type"),
            "coverage": f.get("coverage"), "userCount": f.get("userCount"),
            "alphaCount": f.get("alphaCount"), "description": f.get("description"),
        } for f in rows]
        items.sort(key=lambda x: -(x["coverage"] or 0))
        out = os.path.join(_HERE, "results", f"eur_fields_{ds}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)
        logger.info("%s: %d fields saved -> %s", ds, len(items), out)
        for x in items[:40]:
            logger.info("  %s %s cov=%s users=%s alphas=%s | %s",
                        x["id"], x["type"], x["coverage"], x["userCount"], x["alphaCount"],
                        (x["description"] or "")[:60])


if __name__ == "__main__":
    main()
