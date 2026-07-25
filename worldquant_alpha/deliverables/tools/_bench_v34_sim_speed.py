#!/usr/bin/env python3
"""对照测速: v34 假 multi(线程池单 sim) vs 真 multi-simulation.

公平原则:
- 两组各 8 条, 算子复杂度相近, 字段不同, 避免平台缓存互相污染
- 顺序执行: 先 A 再 B (或由 BENCH_ORDER 控制), 不同时抢槽
- 只测回测墙钟时间, 不含 /check / PC
"""
import sys, os, json, time, logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))
from wd_lib_wrapper import WqApiSimple

API_BASE = "https://api.worldquantbrain.com"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v34bench")

N = int(os.environ.get("BENCH_N", "8"))
ORDER = os.environ.get("BENCH_ORDER", "multi,single")  # multi,single | single,multi

settings_base = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 4,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P6Y",
    "maxTrade": "OFF",
}


def run_single_pool(api, batch, max_workers=8):
    """v1 风格: 线程池各自 POST 单 sim."""
    results = {}

    def one(sim):
        t0 = time.monotonic()
        try:
            res = api.run_backtest(sim["expr"], settings=sim["settings"])
            pid = res.get("platform_id") if res else None
            dt = time.monotonic() - t0
            results[sim["label"]] = {"pid": pid, "sec": dt, "ok": bool(pid)}
            logger.info("[single] %s done in %.1fs pid=%s", sim["label"], dt, pid)
        except Exception as e:
            results[sim["label"]] = {"pid": None, "sec": time.monotonic() - t0, "ok": False, "err": str(e)[:80]}
            logger.warning("[single] %s err %s", sim["label"], e)

    wall0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(one, s) for s in batch]
        for f in as_completed(futs):
            f.result()
    wall = time.monotonic() - wall0
    return wall, results


def submit_multi(session, sim_data_list, api, max_retries=12):
    for attempt in range(max_retries):
        try:
            r = session.post(f"{API_BASE}/simulations", json=sim_data_list, timeout=120)
            if r.ok:
                loc = r.headers.get("Location") or ""
                if not loc:
                    try:
                        loc = (r.json() or {}).get("location", "")
                    except Exception:
                        pass
                return loc or None
            if r.status_code == 429:
                time.sleep(min(20 + attempt * 8, 90))
                continue
            if r.status_code == 401:
                api._reauth()
                session.cookies.clear()
                session.cookies.update(api.session.cookies)
                continue
            if r.status_code == 400:
                logger.error("multi 400: %s", r.text[:300])
                return "BAD_REQUEST"
            time.sleep(10)
        except Exception as e:
            logger.warning("multi net: %s", e)
            time.sleep(10)
    return None


def poll_multi(session, prog_url, max_wait=900):
    started = time.monotonic()
    while time.monotonic() - started < max_wait:
        pr = session.get(prog_url, timeout=60)
        try:
            ra = float(pr.headers.get("Retry-After", "0") or 0)
        except Exception:
            ra = 0
        if ra > 0:
            time.sleep(ra)
            continue
        try:
            data = pr.json()
        except Exception:
            time.sleep(5)
            continue
        children = data.get("children") or []
        status = data.get("status", "")
        if status == "ERROR":
            return []
        if status == "COMPLETE" or children:
            return children
        time.sleep(5)
    return None


def get_child(session, child_id, api):
    url = child_id if str(child_id).startswith("http") else f"{API_BASE}/simulations/{child_id}"
    for _ in range(8):
        r = session.get(url, timeout=60)
        if r.ok:
            aid = r.json().get("alpha")
            if aid:
                return aid
            try:
                ra = float(r.headers.get("Retry-After", "0") or 0)
            except Exception:
                ra = 0
            if ra > 0:
                time.sleep(ra)
                continue
        time.sleep(3)
    return None


def run_multi(api, batch):
    """顾问风格: 一次 POST list."""
    session = api.session
    sim_data_list = [
        {"type": "REGULAR", "settings": b["settings"], "regular": b["expr"]} for b in batch
    ]
    wall0 = time.monotonic()
    loc = submit_multi(session, sim_data_list, api)
    if loc == "BAD_REQUEST" or not loc:
        return time.monotonic() - wall0, {"_error": loc or "submit_failed"}, False
    children = poll_multi(session, loc, max_wait=900)
    results = {}
    if children is None:
        return time.monotonic() - wall0, {"_error": "timeout"}, False
    for i, child in enumerate(children):
        label = batch[i]["label"] if i < len(batch) else f"c{i}"
        pid = get_child(session, child, api)
        results[label] = {"pid": pid, "ok": bool(pid)}
        logger.info("[multi] %s pid=%s", label, pid)
    wall = time.monotonic() - wall0
    return wall, results, True


def summarize(name, wall, results, n):
    oks = sum(1 for k, v in results.items() if k != "_error" and v.get("ok"))
    per = wall / max(n, 1)
    thr = (oks / max(wall, 1e-6)) * 3600
    return {
        "mode": name,
        "n": n,
        "ok": oks,
        "wall_sec": round(wall, 1),
        "sec_per_alpha_wall": round(per, 1),
        "throughput_alpha_per_hour": round(thr, 1),
        "results": results,
    }


def main():
    # 两组字段尽量错开; window 189 vs 188, 降低平台缓存互相偏袒
    fields_m = [
        "eur_aggregated_value_1",
        "eur_aggregated_value_2",
        "eur_aggregated_value_3",
        "eur_aggregated_value_4",
        "eur_top_value_1",
        "eur_top_value_2",
        "eur_director_value_1",
        "eur_signal_value_1",
    ]
    fields_s = [
        "director_intensity_score",
        "eur_top_director_signal_value_1",
        "eur_top_director_signal_value_3",
        "eur_signal_value_1",
        "eur_aggregated_value_4",
        "eur_top_value_2",
        "eur_director_value_1",
        "eur_aggregated_value_3",
    ]
    batch_multi = []
    for i, f in enumerate(fields_m[:N]):
        decay = 3 + (i % 4)
        st = settings_base.copy()
        st["decay"] = decay
        batch_multi.append(
            {
                "label": f"M_{f}_d{decay}",
                "expr": f"rank(ts_zscore(ts_backfill({f}, 66), 189))",
                "settings": st,
            }
        )
    batch_single = []
    for i, f in enumerate(fields_s[:N]):
        decay = 5 + (i % 2)
        st = settings_base.copy()
        st["decay"] = decay
        batch_single.append(
            {
                "label": f"S_{f}_d{decay}",
                "expr": f"rank(ts_zscore(ts_backfill({f}, 66), 188))",
                "settings": st,
            }
        )

    api = WqApiSimple()
    report = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "n": N,
        "order": ORDER,
        "modes": [],
    }

    def run_mode(name):
        if name == "multi":
            logger.info("===== MODE multi-sim (N=%d) =====", N)
            wall, results, ok = run_multi(api, batch_multi)
            if not ok:
                logger.error("multi failed: %s", results)
            return summarize("multi", wall, results, N)
        logger.info("===== MODE single-threadpool (N=%d, workers=%d) =====", N, N)
        wall, results = run_single_pool(api, batch_single, max_workers=N)
        return summarize("single", wall, results, N)

    for name in [x.strip() for x in ORDER.split(",") if x.strip()]:
        # 批间冷却, 降低限流干扰下一模式
        if report["modes"]:
            logger.info("cooldown 60s between modes...")
            time.sleep(60)
        report["modes"].append(run_mode(name))

    # 对比
    by = {m["mode"]: m for m in report["modes"]}
    if "multi" in by and "single" in by:
        m, s = by["multi"], by["single"]
        speedup = (s["wall_sec"] / m["wall_sec"]) if m["wall_sec"] > 0 else None
        report["comparison"] = {
            "single_wall_sec": s["wall_sec"],
            "multi_wall_sec": m["wall_sec"],
            "speedup_x": round(speedup, 2) if speedup else None,
            "single_per_hour": s["throughput_alpha_per_hour"],
            "multi_per_hour": m["throughput_alpha_per_hour"],
            "verdict": (
                "MULTI_FASTER"
                if speedup and speedup >= 1.3
                else ("SIMILAR" if speedup and speedup >= 0.85 else "MULTI_NOT_FASTER")
            ),
        }
        logger.info("=" * 60)
        logger.info(
            "RESULT: single=%.1fs (%.1f/h) | multi=%.1fs (%.1f/h) | speedup=%.2fx | %s",
            s["wall_sec"],
            s["throughput_alpha_per_hour"],
            m["wall_sec"],
            m["throughput_alpha_per_hour"],
            speedup or 0,
            report["comparison"]["verdict"],
        )
        logger.info("=" * 60)

    out = os.path.join(
        _HERE, "results", f"bench_v34_sim_speed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Saved %s", out)
    print(json.dumps(report.get("comparison") or report["modes"], indent=2))


if __name__ == "__main__":
    main()
