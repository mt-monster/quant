#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确认性测试：精确测定"瞬时并发提交接纳上限" L。

之前 measure_L 的 K=10 全 201 是因提交被连接池/平台序列化、在 34s 内陆续到达（瞬时并发从未超过 L）；
measure_rate 的首阶段（无残留）显示 6 接纳 / 第7个 429。
本测试：真正同时发起 K 个 multi-sim（8 线程同时 POST），统计 201/429，每轮间隔 120s 清空残留槽位。
  - K=5 -> 应全 201 (L>=5)
  - K=6 -> 应全 201 (L>=6)
  - K=7 -> 若 L=6, 应 6 接纳 / 1 个 429
用法：python -u measure_L2.py
输出：results/measure_L2_checkpoint.json
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
    try:
        session.get(f"{API_BASE}/simulations?limit=1", timeout=30)
    except Exception:
        pass
    print("[L2] warmed up; main account = mthyzx@126.com", flush=True)

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
    for K in [5, 6, 7]:
        r = burst(K)
        print(f"[L2] K={K} dt={r['dt']}s 201={r['n201']} 429={r['n429']} codes={r['codes']}", flush=True)
        summary.append(r)
        time.sleep(120)  # 清空残留在跑 sim，避免污染下一轮
    with open(os.path.join(HERE, "results", "measure_L2_checkpoint.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("[L2] DONE -> results/measure_L2_checkpoint.json", flush=True)


if __name__ == "__main__":
    main()
