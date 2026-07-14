#!/usr/bin/env python3
"""侦察：全量枚举 USA/D1/TOP3000 中 PM==1.0（未点亮金字塔）的数据集，
打印其 fieldCount，并对候选取 MATRIX 字段数以选单数据集双字段挖掘。"""
import sys, os, json, time, logging
sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv(os.path.abspath(".env"))
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
API = "https://api.worldquantbrain.com"
U = os.environ["WQ_USERNAME"]; P = os.environ["WQ_PASSWORD"]

def get_session():
    s = requests.Session(); s.auth = (U, P)
    s.post(f"{API}/authentication", timeout=30).raise_for_status()
    return s

def list_all(s, max_pages=20):
    out = []
    for off in range(0, max_pages * 50, 50):
        url = (f"{API}/data-sets?instrumentType=EQUITY&region=USA&delay=1"
               f"&universe=TOP3000&limit=50&offset={off}")
        r = s.get(url, timeout=30); r.raise_for_status()
        res = r.json().get("results", [])
        if not res:
            break
        for d in res:
            try: pm = float(d.get("pyramidMultiplier", 1.0))
            except (TypeError, ValueError): pm = 1.0
            out.append({
                "id": d.get("id"), "name": d.get("name"),
                "pm": pm, "fc": int(d.get("fieldCount") or 0),
                "cat": (d.get("category") or {}).get("id", ""),
            })
        if len(res) < 50:
            break
        time.sleep(0.2)
    return out

def matrix_count(s, ds_id):
    url = (f"{API}/data-fields?instrumentType=EQUITY&region=USA&delay=1"
           f"&universe=TOP3000&dataset.id={ds_id}&limit=50&offset=0")
    r = s.get(url, timeout=30)
    if r.status_code != 200:
        return 0, []
    res = r.json().get("results", [])
    mtx = [f["id"] for f in res if f.get("type") == "MATRIX"]
    return len(mtx), mtx

def main():
    s = get_session()
    all_ds = list_all(s)
    logger.info("扫描数据集总数: %d", len(all_ds))
    unlit = [d for d in all_ds if abs(d["pm"] - 1.0) < 1e-9 and d["fc"] >= 2]
    logger.info("未点亮(PM==1.0)且字段>=2 的数据集: %d 个", len(unlit))
    # 评估候选 MATRIX 字段数
    ranked = []
    for d in unlit:
        n, mtx = matrix_count(s, d["id"])
        d["mtx"] = n; d["fields"] = mtx
        ranked.append(d)
        logger.info("  %-24s fc=%-4d mtx=%-4d cat=%-12s %s", d["id"], d["fc"], n, d["cat"], d["name"])
        time.sleep(0.2)
    ranked.sort(key=lambda x: -x["mtx"])
    logger.info("=" * 72)
    logger.info("按 MATRIX 字段数排序的 Top 候选:")
    for d in ranked[:12]:
        logger.info("  %-24s mtx=%-4d fc=%-4d | %s", d["id"], d["mtx"], d["fc"], d["name"])
    os.makedirs("results", exist_ok=True)
    with open("results/unlit_datasets.json", "w", encoding="utf-8") as f:
        json.dump({"total_unlit": len(unlit), "candidates": ranked}, f, indent=2, ensure_ascii=False)
    logger.info("已保存 -> results/unlit_datasets.json")
    if ranked:
        logger.info("推荐: %s (%s) mtx=%d", ranked[0]["id"], ranked[0]["name"], ranked[0]["mtx"])

if __name__ == "__main__":
    main()
