#!/usr/bin/env python3
"""舰队扩容/降级: 先加到 target=7, 若 429 风暴则 7→6→5→4 直到稳定.

用法:
  python fleet_scale.py --target 7 --add v50 v51 v52
  # 已有 V46+V47+V48+V49=4, 再加 3 个到 7
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from glob import glob
from typing import Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(_HERE, "results", "fleet_active.json")
STAGGER = float(os.environ.get("FLEET_STAGGER_SEC", "22"))
WATCH_SEC = float(os.environ.get("FLEET_WATCH_SEC", "180"))
# 观察窗口内 429 次数超过阈值 → 降级
MAX_429_IN_WINDOW = int(os.environ.get("FLEET_MAX_429", "8"))


def _load_meta() -> dict:
    if os.path.exists(META_PATH):
        try:
            return json.load(open(META_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {"procs": []}


def _save_meta(meta: dict):
    os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
    tmp = META_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, META_PATH)


def _alive(pid: int) -> bool:
    try:
        # Windows
        out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], text=True, errors="ignore")
        return str(pid) in out and "python" in out.lower()
    except Exception:
        return False


def _kill(pid: int):
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
        print(f"[scale] killed pid={pid}")
    except Exception as e:
        print(f"[scale] kill fail {pid}: {e}")


def _count_429(since_ts: float) -> int:
    """扫最近 fleet / v46 日志中的 429 次数."""
    n = 0
    patterns = [
        os.path.join(_HERE, "results", "fleet_v*.out.log"),
        os.path.join(_HERE, "results", "v46_tri_progress_*.log"),
    ]
    # also scan terminal-ish progress logs
    for pat in patterns:
        for path in glob(pat):
            try:
                # 只读末尾，避免大文件
                with open(path, "rb") as f:
                    f.seek(0, 2)
                    sz = f.tell()
                    f.seek(max(0, sz - 200_000))
                    text = f.read().decode("utf-8", "ignore")
                n += text.lower().count("429")
                n += text.lower().count("rate limit")
                n += text.count("backoff")
            except Exception:
                pass
    return n


def _launch_job(job: str) -> Dict:
    py = sys.executable
    worker = os.path.join(_HERE, "scan_tri_job.py")
    log_dir = os.path.join(_HERE, "results")
    os.makedirs(log_dir, exist_ok=True)
    out_path = os.path.join(log_dir, f"fleet_{job}_{time.strftime('%Y%m%d_%H%M%S')}.out.log")
    cmd = [py, "-u", worker, "--job", job]
    print(f"[scale] launch {job} -> {out_path}")
    f = open(out_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=_HERE, stdout=f, stderr=subprocess.STDOUT)
    return {"job": job, "pid": proc.pid, "log": out_path}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=7, help="目标并发挖掘进程数 (含已有)")
    ap.add_argument("--add", nargs="+", default=["v50", "v51", "v52"])
    ap.add_argument("--stagger", type=float, default=STAGGER)
    ap.add_argument("--watch", type=float, default=WATCH_SEC)
    ap.add_argument("--v46-pid", type=int, default=0, help="若已知 V46 pid 一并登记")
    args = ap.parse_args()

    meta = _load_meta()
    procs: List[Dict] = list(meta.get("procs") or [])
    # 清理已死
    procs = [p for p in procs if _alive(int(p["pid"]))]
    if args.v46_pid and _alive(args.v46_pid):
        if not any(int(p["pid"]) == args.v46_pid for p in procs):
            procs.insert(0, {"job": "v46", "pid": args.v46_pid, "log": "scan_v46_tri_insider_trx.py"})

    # 也尝试从 tasklist 找 v46
    print(f"[scale] living fleet procs: {len(procs)} -> {[p['job'] for p in procs]}")

    # 扩容
    existing_jobs = {p["job"] for p in procs}
    to_add = [j for j in args.add if j not in existing_jobs]
    while len(procs) < args.target and to_add:
        job = to_add.pop(0)
        if procs:
            print(f"[scale] stagger {args.stagger:.0f}s ...")
            time.sleep(args.stagger)
        info = _launch_job(job)
        procs.append(info)
        meta["procs"] = procs
        meta["target"] = args.target
        meta["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save_meta(meta)
        print(f"[scale] size={len(procs)} after {job}")

    print(f"[scale] at size={len(procs)}, watch {args.watch:.0f}s for 429 ...")
    t0 = time.time()
    base_429 = _count_429(t0)
    time.sleep(min(30, args.watch))  # 先等提交启动
    # 降级阶梯: 7→6→5→4
    ladder = []
    cur = len(procs)
    while cur >= 4:
        ladder.append(cur)
        cur -= 1

    deadline = time.time() + args.watch
    while time.time() < deadline:
        time.sleep(25)
        # refresh alive
        procs = [p for p in procs if _alive(int(p["pid"]))]
        delta_429 = _count_429(t0) - base_429
        print(f"[scale] t+{time.time()-t0:.0f}s size={len(procs)} delta_429≈{delta_429}")
        if delta_429 >= MAX_429_IN_WINDOW and len(procs) > 4:
            # 杀掉最新加入的
            victim = procs.pop()
            print(f"[scale] 429 storm -> step down, kill {victim['job']} pid={victim['pid']}")
            _kill(int(victim["pid"]))
            meta["procs"] = procs
            meta["step_down"] = meta.get("step_down") or []
            meta["step_down"].append({"job": victim["job"], "at": time.strftime("%H:%M:%S"), "delta_429": delta_429})
            _save_meta(meta)
            base_429 = _count_429(t0)  # reset baseline after kill
            # 给桶恢复时间
            time.sleep(40)
        elif delta_429 < MAX_429_IN_WINDOW // 2 and len(procs) >= 4:
            # 稳定信号：继续观察至 watch 结束
            pass

    procs = [p for p in procs if _alive(int(p["pid"]))]
    meta["procs"] = procs
    meta["final_size"] = len(procs)
    meta["stable"] = True
    _save_meta(meta)
    print(f"[scale] DONE final_size={len(procs)} jobs={[p['job'] for p in procs]}")
    print(f"[scale] meta -> {META_PATH}")


if __name__ == "__main__":
    main()
