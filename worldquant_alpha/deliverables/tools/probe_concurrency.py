#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并发探针：在主账号上拉起"第3个"multi-sim 回测，探测平台真实并发槽位上限 L。

- 与 V44/V45 完全相同的提交路径（POST /simulations 传 8 条 list，一次占 1 槽跑 8 子任务）。
- 自带 429 即时自检：提交或轮询一旦收到 HTTP 429，立即打印 PROBE_429 并以 exit(42) 关停（不重试）。
- 写入独立 checkpoint（results/probe_concurrency_checkpoint.json），不与 V44/V45 文件冲突。
- 用法：python -u probe_concurrency.py   （环境变量 PROBE_BATCHES / PROBE_COOLDOWN 可调）
"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wd_lib_wrapper import WqApiSimple, API_BASE
from multi_sim import build_sim_payload

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE_TAG = os.getenv("PROBE_TAG", "main")
PROBE_CKPT = os.path.join(HERE, "results", f"probe_concurrency_{PROBE_TAG}_checkpoint.json")
PROBE_PID = os.path.join(HERE, "results", f"probe_{PROBE_TAG}.pid")
NBATCHES = int(os.getenv("PROBE_BATCHES", "12"))
COOLDOWN = float(os.getenv("PROBE_COOLDOWN", "3"))

# 8 条廉价但合法的 FASTEXPR 表达式，凑满一个 multi-sim 批次（占 1 槽）
EXPRS = [
    "rank(close)", "rank(-close)", "rank(volume)", "rank(-volume)",
    "rank(returns(close,5))", "rank(-returns(close,5))", "rank(adv20)", "rank(-adv20)",
]
SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "NONE", "truncation": 0.01,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
}
BATCH = [{"expr": EXPRS[i % len(EXPRS)], "settings": SETTINGS} for i in range(8)]


def log(msg):
    print(f"[PROBE-{PROBE_TAG} {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _save(results):
    try:
        os.makedirs(os.path.dirname(PROBE_CKPT), exist_ok=True)
        with open(PROBE_CKPT, "w", encoding="utf-8") as f:
            json.dump({"n_batches": len(results),
                       "any_429": any(r.get("status") == 429 for r in results),
                       "results": results}, f, indent=2)
    except Exception as e:
        log(f"save err: {e}")


def _poll(session, loc, b):
    started = time.time()
    while time.time() - started < 600:
        try:
            pr = session.get(loc, timeout=60)
        except Exception as e:
            log(f"poll err b{b}: {e}"); time.sleep(10); continue
        if pr.status_code == 429:
            log(f"*** 429 during POLL batch {b} -> IMMEDIATE SHUTDOWN ***")
            sys.exit(42)
        try:
            data = pr.json()
        except Exception:
            time.sleep(5); continue
        st = data.get("status", "")
        if st == "COMPLETE" or data.get("children"):
            return
        if st == "ERROR":
            log(f"poll b{b} ERROR"); return
        time.sleep(5)


def main():
    # 写 PID 文件，便于后续精确关停（避免误杀其他进程）
    try:
        with open(PROBE_PID, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    log(f"init WqApiSimple (main account mthyzx@126.com), NBATCHES={NBATCHES}")
    api = WqApiSimple()
    session = api.session
    results = []
    for b in range(NBATCHES):
        sim_list = [build_sim_payload(x["expr"], x["settings"]) for x in BATCH]
        t0 = time.time()
        try:
            r = session.post(f"{API_BASE}/simulations", json=sim_list, timeout=120)
        except Exception as e:
            log(f"network error batch {b}: {e}")
            time.sleep(10); continue
        dt = round(time.time() - t0, 1)
        if r.status_code == 429:
            ra = r.headers.get("Retry-After", "?")
            log(f"*** 429 DETECTED at batch {b} (dt={dt}s, Retry-After={ra}) -> IMMEDIATE SHUTDOWN ***")
            results.append({"batch": b, "status": 429, "dt": dt, "retry_after": ra})
            _save(results)
            sys.exit(42)  # 信号：429 -> 主进程据此确认已关停
        if not r.ok:
            log(f"batch {b}: HTTP {r.status_code} (dt={dt}s) body={r.text[:200]}")
            results.append({"batch": b, "status": r.status_code, "dt": dt})
            _save(results)
            time.sleep(15); continue
        loc = r.headers.get("Location") or ""
        if not loc:
            try:
                loc = (r.json() or {}).get("location", "")
            except Exception:
                pass
        log(f"batch {b}: HTTP {r.status_code} OK (dt={dt}s) loc={'yes' if loc else 'no'}")
        if loc:
            _poll(session, loc, b)  # 占住槽位，维持与 V44/V45 的三方并发
        results.append({"batch": b, "status": r.status_code, "dt": dt})
        _save(results)
        time.sleep(COOLDOWN)
    log(f"COMPLETED all {NBATCHES} batches with NO 429 -> 证据支持 L>=3（3 个并发 multi-sim 均成功）")
    _save(results)


if __name__ == "__main__":
    main()
