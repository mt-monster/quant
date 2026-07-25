#!/usr/bin/env python3
"""舰队守护: 永远维持 TARGET=8 路回测进程。

- 每 POLL 秒检查存活挖掘进程数
- 不足则从数据集队列错峰补位 (stagger≥22s)
- 已跑完的数据集进 done, 不重复; 队列耗尽则从 high_pm 续补
- 共享 submit_gate; 禁齐射

用法:
  python -u fleet_keeper.py
  python -u fleet_keeper.py --target 8 --once   # 只补一轮
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from glob import glob
from typing import Dict, List, Set, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(_HERE, "results", "fleet_keeper_state.json")
ACTIVE = os.path.join(_HERE, "results", "fleet_active.json")
HIGHPM = os.path.join(_HERE, "results", "_usa_top3000_highpm.json")

TARGET_DEFAULT = 8
STAGGER = float(os.environ.get("FLEET_STAGGER_SEC", "22"))
POLL = float(os.environ.get("FLEET_POLL_SEC", "90"))

# 优先队列 (未跑/值得再挖)
SEED_QUEUE = [
    "pv_tech_indicators",
    "web_traffic_engage",
    "order_book_imbalance",
    "ml_factor_proj",
    "quant_factor_lib",
    "techindi_model",
    "equity_kpi_forecast",
    "workforce_flow_skills",
    "filing_sentiment",
    "earningscall_sentiment",
    "options_composite",
    "price_signal_dl",
    "dl_riskfree_returns",
    "news_sentiment_transfer",
    "sentiment22",
    "sentiment21",
    "analyst_earnings_ibes",
    "shortinterest6",
    "shortinterest7",
    "fundamental65",
    "expected_move",
    "multi_horizon_alpha",
    "chart_cnn_alpha",
]

TRIED_ALWAYS = {
    "insider_matrix",
    "insider_feats",
    "insider_trx_matrix",
    "search_interest",
    "acquisition_model",
    "forward_beta_risk",
    "board_network",
    "behavioral_signals",
    "hiring_trends",
    "stock_search_trends",
    "event_stock_model",
    "news_sentiment_nlp",
    "stock_cluster_dl",
    "other545",
    "sustainable_profit",
    "cre_exposure_model",
    "earnings_risk",
    "social_sent_score",
    "event_relation",
}

MINER_PAT = re.compile(
    r"scan_tri_job\.py|scan_v52b_hiring_margin\.py|scan_v46_tri_insider_trx\.py",
    re.I,
)


def _load_state() -> dict:
    if os.path.exists(META):
        try:
            return json.load(open(META, encoding="utf-8"))
        except Exception:
            pass
    return {"done_datasets": [], "launched": [], "queue": list(SEED_QUEUE)}


def _save_state(st: dict):
    os.makedirs(os.path.dirname(META), exist_ok=True)
    tmp = META + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, META)


def list_miners() -> List[Dict]:
    """返回 [{pid, cmd, tag}] 正在跑的挖掘进程."""
    out = []
    try:
        ps = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
            ],
            text=True,
            errors="ignore",
            cwd=_HERE,
        )
        data = json.loads(ps) if ps.strip() else []
        if isinstance(data, dict):
            data = [data]
    except Exception:
        data = []
    for row in data or []:
        cmd = row.get("CommandLine") or ""
        pid = row.get("ProcessId")
        if not cmd or not MINER_PAT.search(cmd):
            continue
        tag = "unknown"
        m = re.search(r"--job\s+(\S+)", cmd)
        if m:
            tag = m.group(1)
        m = re.search(r"--dataset\s+(\S+)", cmd)
        if m:
            tag = f"ds:{m.group(1)}"
        elif "v52b" in cmd:
            tag = "v52b"
        elif "scan_v46" in cmd:
            tag = "v46"
        out.append({"pid": int(pid), "cmd": cmd, "tag": tag})
    return out


def done_datasets_from_disk() -> Set[str]:
    done = set(TRIED_ALWAYS)
    for path in glob(os.path.join(_HERE, "results", "*_tri_*_checkpoint.json")):
        base = os.path.basename(path)
        # v47_tri_search_interest_checkpoint.json / ds_xxx_tri_yyy_checkpoint.json
        m = re.search(r"_tri_([a-z0-9_]+)_checkpoint", base)
        if m:
            done.add(m.group(1))
    return done


def build_queue(st: dict) -> List[str]:
    done = set(st.get("done_datasets") or []) | done_datasets_from_disk()
    q = []
    for ds in list(st.get("queue") or []) + list(SEED_QUEUE):
        if ds not in done and ds not in q and not ds.startswith("other"):
            q.append(ds)
    # high_pm 续补
    if os.path.exists(HIGHPM):
        try:
            hp = json.load(open(HIGHPM, encoding="utf-8")).get("high_pm") or []
            for x in hp:
                ds = x if isinstance(x, str) else (x.get("id") or x.get("name"))
                if not ds or ds in done or ds in q or str(ds).startswith("other"):
                    continue
                q.append(ds)
        except Exception:
            pass
    st["queue"] = q
    st["done_datasets"] = sorted(done)
    return q


def launch_dataset(dataset: str) -> Tuple[int, str]:
    py = sys.executable
    worker = os.path.join(_HERE, "scan_tri_job.py")
    log_dir = os.path.join(_HERE, "results")
    os.makedirs(log_dir, exist_ok=True)
    jid = "ds_" + re.sub(r"[^a-z0-9_]+", "_", dataset.lower())[:28]
    log = os.path.join(log_dir, f"fleet_{jid}_{time.strftime('%Y%m%d_%H%M%S')}.out.log")
    cmd = [py, "-u", worker, "--dataset", dataset, "--job-id", jid]
    print(f"[keeper] launch {dataset} -> {log}")
    f = open(log, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=_HERE, stdout=f, stderr=subprocess.STDOUT)
    return proc.pid, log


def fill_to_target(target: int, stagger: float, st: dict) -> dict:
    miners = list_miners()
    n = len(miners)
    print(f"[keeper] alive={n} target={target} tags={[m['tag'] for m in miners]}")
    if n >= target:
        return st
    need = target - n
    q = build_queue(st)
    # 跳过已在跑的 dataset
    running_ds = set()
    for m in miners:
        if m["tag"].startswith("ds:"):
            running_ds.add(m["tag"][3:])
    launched = list(st.get("launched") or [])
    for i in range(need):
        ds = None
        while q:
            cand = q.pop(0)
            if cand in running_ds or cand in (st.get("done_datasets") or []):
                continue
            ds = cand
            break
        if not ds:
            print("[keeper] queue empty — cannot fill")
            break
        if i > 0 or n > 0:
            print(f"[keeper] stagger {stagger:.0f}s ...")
            time.sleep(stagger)
        pid, log = launch_dataset(ds)
        launched.append({"dataset": ds, "pid": pid, "log": log, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
        running_ds.add(ds)
        print(f"[keeper] started {ds} pid={pid} size~{n + i + 1}")
    st["queue"] = q
    st["launched"] = launched[-80:]
    st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    miners2 = list_miners()
    with open(ACTIVE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "target": target,
                "final_size": len(miners2),
                "procs": [{"job": m["tag"], "pid": m["pid"]} for m in miners2],
                "updated": st["updated"],
                "keeper": True,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    _save_state(st)
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=TARGET_DEFAULT)
    ap.add_argument("--stagger", type=float, default=STAGGER)
    ap.add_argument("--poll", type=float, default=POLL)
    ap.add_argument("--once", action="store_true", help="只补一轮后退出")
    args = ap.parse_args()

    print(f"[keeper] start target={args.target} stagger={args.stagger}s poll={args.poll}s")
    st = _load_state()
    build_queue(st)
    _save_state(st)

    while True:
        st = fill_to_target(args.target, args.stagger, st)
        if args.once:
            break
        # 标记已结束的 launched dataset 为 done (若对应 ckpt 存在且进程已死)
        alive_pids = {m["pid"] for m in list_miners()}
        for item in list(st.get("launched") or []):
            pid = item.get("pid")
            ds = item.get("dataset")
            if pid and pid not in alive_pids and ds:
                # 若有 checkpoint 视为本轮完成
                if glob(os.path.join(_HERE, "results", f"*tri_{ds}_checkpoint.json")):
                    done = set(st.get("done_datasets") or [])
                    done.add(ds)
                    st["done_datasets"] = sorted(done)
        _save_state(st)
        print(f"[keeper] sleep {args.poll:.0f}s ...")
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
