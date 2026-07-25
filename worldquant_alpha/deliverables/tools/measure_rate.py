#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隔离测量 WorldQuant Brain 主账号的"提交速率上限"（排除并发槽位干扰）。

每个提交 = 1 个 multi-sim（1 条 EXPR，仍占 1 槽，但计算量最小以省额度）。
单线程、按固定 pace 匀速提交，观察不同 pace 下的 429 数量。
  - 若某 pace 下 429=0 -> 该速率安全
  - 若 429>0 -> 超过速率上限
结论：平台真正限制的是"每秒提交数"，而非"同时在跑的槽位数"。

用法：python -u measure_rate.py
输出：results/measure_rate_checkpoint.json
"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wd_lib_wrapper import WqApiSimple, API_BASE
from multi_sim import build_sim_payload
import dotenv
dotenv.load_dotenv(".env")

HERE = os.path.dirname(os.path.abspath(__file__))
EXPR = "rank(close)"
SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "NONE", "truncation": 0.01,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P1Y", "maxTrade": "OFF",
}
PAYLOAD = build_sim_payload(EXPR, SETTINGS)  # dict: 单次提交 = 1 个 simulation（占 1 槽）


def main():
    api = WqApiSimple()
    session = api.session
    try:
        session.get(f"{API_BASE}/simulations?limit=1", timeout=30)
    except Exception:
        pass
    print("[RATE] warmed up; main account = mthyzx@126.com", flush=True)

    def submit_one():
        try:
            r = session.post(f"{API_BASE}/simulations", json=PAYLOAD, timeout=60)
            return r.status_code
        except Exception as e:
            return f"ERR:{e}"

    summary = []
    for pace in [3.0, 2.0, 1.5, 1.0, 0.6]:
        n = 8
        codes = []
        t0 = time.time()
        for i in range(n):
            codes.append(submit_one())
            time.sleep(pace)
        dt = round(time.time() - t0, 1)
        n201 = codes.count(201)
        n429 = sum(1 for c in codes if c == 429)
        rate = round(n / dt, 3)
        rec = {"pace_s": pace, "n": n, "dt_s": dt, "rate_per_s": rate,
               "n201": n201, "n429": n429, "codes": codes}
        print(f"[RATE] pace={pace}s rate={rate}/s 201={n201} 429={n429} codes={codes}", flush=True)
        summary.append(rec)
    with open(os.path.join(HERE, "results", "measure_rate_checkpoint.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("[RATE] DONE -> results/measure_rate_checkpoint.json", flush=True)


if __name__ == "__main__":
    main()
