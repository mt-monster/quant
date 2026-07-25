#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确测量 WorldQuant Brain 主账号的真实并发槽位上限 L。

方法：单机多线程同步突发（burst）。每个线程提交 1 个 multi-sim（8 条 EXPR，占 1 槽）。
同时发出 K 个线程，统计收到 201 与 429 的数量。
  - 若 K 个全 201  -> L >= K
  - 若其中 M 个 201、其余 429 -> 该瞬间 L = M（V44/V45 后台若占槽则 L 更大，取多次试验的 max(M) 即真值）
槽位上限与 sim 计算量无关，故用 P1Y 廉价设置减少额度消耗；每个 burst 后 sleep 55s 让槽位释放。

用法：python -u measure_L.py
输出：results/measure_L_checkpoint.json
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


def make_sim_list():
    return [build_sim_payload(x["expr"], x["settings"]) for x in BATCH]


def main():
    api = WqApiSimple()
    session = api.session
    # pre-warm token
    try:
        session.get(f"{API_BASE}/simulations?limit=1", timeout=30)
    except Exception:
        pass
    print("[MEASURE] warmed up; main account = mthyzx@126.com", flush=True)

    def fire_once():
        try:
            r = session.post(f"{API_BASE}/simulations", json=make_sim_list(), timeout=60)
            return r.status_code
        except Exception as e:
            return f"ERR:{e}"

    def burst(K):
        codes = []
        lock = threading.Lock()

        def worker():
            c = fire_once()
            with lock:
                codes.append(c)

        threads = [threading.Thread(target=worker) for _ in range(K)]
        t0 = time.time()
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        dt = round(time.time() - t0, 2)
        n201 = codes.count(201)
        n429 = sum(1 for c in codes if c == 429)
        return {"K": K, "dt": dt, "n201": n201, "n429": n429, "codes": codes}

    summary = []
    for K in [7, 8, 9, 10, 11, 12]:
        res = burst(K)
        print(f"[MEASURE] K={K} dt={res['dt']}s 201={res['n201']} 429={res['n429']} codes={res['codes']}", flush=True)
        summary.append(res)
        time.sleep(55)
    with open(os.path.join(HERE, "results", "measure_L_checkpoint.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("[MEASURE] DONE -> results/measure_L_checkpoint.json", flush=True)


if __name__ == "__main__":
    main()
