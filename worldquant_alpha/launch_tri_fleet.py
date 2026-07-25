#!/usr/bin/env python3
"""错峰启动三轨挖掘舰队 (共享 submit_gate).

默认: V46 已在跑时，再启 V47/V48/V49，进程间 stagger ≥22s，避免齐射。
瞬时提交进程数目标 ≤4 (< 安全区 6)。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
STAGGER_SEC = float(os.environ.get("FLEET_STAGGER_SEC", "22"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jobs", nargs="+", default=["v47", "v48", "v49"])
    p.add_argument("--stagger", type=float, default=STAGGER_SEC)
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()

    py = sys.executable
    worker = os.path.join(_HERE, "scan_tri_job.py")
    log_dir = os.path.join(_HERE, "results")
    os.makedirs(log_dir, exist_ok=True)

    procs = []
    for i, job in enumerate(args.jobs):
        if i > 0:
            print(f"[fleet] stagger wait {args.stagger:.0f}s before {job}...")
            if not args.dry:
                time.sleep(args.stagger)
        out_path = os.path.join(log_dir, f"fleet_{job}_{time.strftime('%Y%m%d_%H%M%S')}.out.log")
        cmd = [py, "-u", worker, "--job", job]
        print(f"[fleet] launch {job}: {' '.join(cmd)} -> {out_path}")
        if args.dry:
            continue
        f = open(out_path, "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(cmd, cwd=_HERE, stdout=f, stderr=subprocess.STDOUT)
        procs.append({"job": job, "pid": proc.pid, "log": out_path})
        print(f"[fleet] {job} pid={proc.pid}")

    meta = os.path.join(log_dir, "fleet_active.json")
    import json
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"started": time.strftime("%Y-%m-%d %H:%M:%S"), "procs": procs, "stagger": args.stagger}, f, indent=2)
    print(f"[fleet] meta -> {meta}")
    print("[fleet] all launched (detached). V46 if running is independent.")


if __name__ == "__main__":
    main()
