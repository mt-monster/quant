#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发现 EUR/D1 可用 universe + 未点亮金字塔数据集 (pyramidMultiplier==1.0).

输出: results/eur_unlit_discovery.json
"""
import sys, os, json, logging

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("eur_discover")

from wd_lib_wrapper import WqApiSimple

API = "https://api.worldquantbrain.com"
OUT = os.path.join(_HERE, "results", "eur_unlit_discovery.json")

CANDIDATE_UNIVERSES = ["TOP2500", "TOP1200", "TOP800", "TOP400", "TOPCS1600", "ILLIQUID_MINVOL1M", "MINVOL1M"]


def main():
    api = WqApiSimple()
    s = api.session

    # 1) 探测 EUR D1 各 universe 是否有数据集
    uni_ok = {}
    for uni in CANDIDATE_UNIVERSES:
        r = s.get(f"{API}/data-sets", params={
            "instrumentType": "EQUITY", "region": "EUR", "delay": 1,
            "universe": uni, "limit": 1,
        }, timeout=60)
        cnt = 0
        if r.ok:
            try:
                cnt = r.json().get("count", 0)
            except Exception:
                pass
        uni_ok[uni] = cnt
        logger.info("universe %s -> count=%s http=%s", uni, cnt, r.status_code)

    valid_unis = [u for u, c in uni_ok.items() if c > 0]
    if not valid_unis:
        logger.error("no valid universe found for EUR D1")
        return

    # 2) 各 universe 拉全部数据集, 记录 pyramidMultiplier
    all_ds = {}
    for uni in valid_unis:
        offset, rows = 0, []
        while True:
            r = s.get(f"{API}/data-sets", params={
                "instrumentType": "EQUITY", "region": "EUR", "delay": 1,
                "universe": uni, "limit": 50, "offset": offset,
            }, timeout=60)
            if not r.ok:
                break
            j = r.json()
            res = j.get("results") or []
            rows.extend(res)
            offset += 50
            if offset >= j.get("count", 0) or not res:
                break
        all_ds[uni] = rows
        logger.info("universe %s -> %d datasets", uni, len(rows))

    # 3) 汇总: 未点亮 = pyramidMultiplier == 1.0 (或缺失按None记录)
    summary = {}
    for uni, rows in all_ds.items():
        items = []
        for d in rows:
            pm = d.get("pyramidMultiplier")
            items.append({
                "id": d.get("id"),
                "name": d.get("name"),
                "category": (d.get("category") or {}).get("id"),
                "subcategory": (d.get("subcategory") or {}).get("id"),
                "fieldCount": d.get("fieldCount"),
                "coverage": d.get("coverage"),
                "userCount": d.get("userCount"),
                "alphaCount": d.get("alphaCount"),
                "valueScore": d.get("valueScore"),
                "pyramidMultiplier": pm,
            })
        items.sort(key=lambda x: (x["pyramidMultiplier"] is None, -(x["pyramidMultiplier"] or 0)))
        summary[uni] = items
        unlit = [x for x in items if x["pyramidMultiplier"] == 1.0]
        lit = [x for x in items if (x["pyramidMultiplier"] or 0) > 1.0]
        logger.info("universe %s: total=%d lit(>1.0)=%d unlit(==1.0)=%d", uni, len(items), len(lit), len(unlit))
        for x in sorted(unlit, key=lambda v: -(v["fieldCount"] or 0))[:25]:
            logger.info("  UNLIT %s pm=%s fields=%s cov=%s users=%s alphas=%s vs=%s cat=%s",
                        x["id"], x["pyramidMultiplier"], x["fieldCount"], x["coverage"],
                        x["userCount"], x["alphaCount"], x["valueScore"], x["category"])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"universe_counts": uni_ok, "datasets": summary}, f, ensure_ascii=False, indent=2)
    logger.info("saved -> %s", OUT)


if __name__ == "__main__":
    main()
