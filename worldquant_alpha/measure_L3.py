#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确测定 token-bucket 容量 C：长空闲让桶充满，再突发 K=8，观察接纳数。

设计：2 轮，每轮先 idle 200s 让桶充满（覆盖慢 refill），再真正同时发起 8 个 multi-sim。
取各轮 201 数之最大值 = min(8, C)（当 V44/V45 恰空闲时即为真值，消除背景噪声）。
  - 若两轮均 8/0 -> C>=8
  - 若均 7/1 -> C=7
  - 若 6/2 -> C=6
用法：python -u measure_L3.py
输出：results/measure_L3_checkpoint.json
"""
import os, sys, time, json, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wd_lib_wrapper import WqApiSimple, API_BASE
from multi_sim import build_sim_payload
import dotenv
dotenv.load_dotenv(".env")

HERE = os.path.dirname(os.path.abspath(__file__))
EXPRS = ["rank(close)", "rank(-close)", "rank(volume)", "rank(-volume)",
         "rank(returns(close,5))", "rank(-returns(close,5))", "rank(adv20)", "rank(-adv20)"]
SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "NONE", "truncation": 0.01,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P1Y", "maxTrade": "OFF",
}
BATCH = [{"expr": EXPRS[i % len(EXPRS)], "settings": SETTINGS} for i in range(8)]


def sim_list():
    return [build_sim_payload(x["expr"], x["settings"]) for x in BATCH]


def main():
    api = WqApiSimple()
    session = api.session
    print("[L3] init; main account = mthyzx@126.com", flush=True)

    def fire():
        try:
            return session.post(f"{API_BASE}/simulations", json=sim_list(), timeout=60).status_code
        except Exception as e:
            return f"ERR:{e}"

    def burst(K):
        codes = []
        lock = threading.Lock()

        def worker():
            c = fire()
            with lock:
                codes.append(c)

        threads = [threading.Thread(target=worker) for _ in range(K)]
        t0 = time.time()
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        dt = round(time.time() - t0, 2)
        return {"K": K, "dt": dt, "n201": codes.count(201),
                "n429": sum(1 for c in codes if c == 429), "codes": codes}

    summary = []
    for trial in [1, 2]:
        print(f"[L3] trial {trial}: idle 200s to refill bucket...", flush=True)
        time.sleep(200)
        r = burst(8)
        print(f"[L3] trial {trial} K=8 dt={r['dt']}s 201={r['n201']} 429={r['n429']} codes={r['codes']}", flush=True)
        summary.append(r)
    with open(os.path.join(HERE, "results", "measure_L3_checkpoint.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("[L3] DONE -> results/measure_L3_checkpoint.json", flush=True)


if __name__ == "__main__":
    main()
