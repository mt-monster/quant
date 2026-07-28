#!/usr/bin/env python3
"""舰队守护: 维持探索进程数 + 近关自动开救援。

默认: 探索 TARGET=7 + 救援专用 1 槽 = 总并发 8。
- 只统计/补位 scan_tri_job (探索); 不抢 scan_rescue_* 槽
- 每轮 poll: 扫描近关 → 救援槽空则自动 launch; **永远优先潜力最大候选**
- 队列耗尽则从 high_pm 续补; 禁齐射

用法:
  python -u fleet_keeper.py              # 探索维持 7 + 自动救援
  python -u fleet_keeper.py --target 7 --once
  python -u fleet_keeper.py --no-auto-rescue
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
sys.path.insert(0, _HERE)
META = os.path.join(_HERE, "results", "fleet_keeper_state.json")
ACTIVE = os.path.join(_HERE, "results", "fleet_active.json")
HIGHPM = os.path.join(_HERE, "results", "_usa_top3000_highpm.json")
RESCUE_QUEUE = os.path.join(_HERE, "results", "rescue_auto_queue.json")

# 探索槽默认 7; 另 1 槽留给近关救援 (scan_rescue_*)
TARGET_DEFAULT = int(os.environ.get("FLEET_EXPLORE_TARGET", "7"))
STAGGER = float(os.environ.get("FLEET_STAGGER_SEC", "22"))
POLL = float(os.environ.get("FLEET_POLL_SEC", "90"))
AUTO_RESCUE_DEFAULT = os.environ.get("FLEET_AUTO_RESCUE", "1") not in ("0", "false", "False", "no")

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

# 仅探索 worker; 救援脚本不计入, 避免 keeper 挤掉救援槽
MINER_PAT = re.compile(r"scan_tri_job\.py", re.I)
RESCUE_PAT = re.compile(r"scan_rescue_.*\.py|scan_v52b_hiring_margin\.py", re.I)


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
        out.append({"pid": int(pid), "cmd": cmd, "tag": tag})
    return out


def list_rescue() -> List[Dict]:
    """近关救援进程 (不计入探索 TARGET)."""
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
        if not cmd or not RESCUE_PAT.search(cmd):
            continue
        out.append({"pid": int(pid), "cmd": cmd, "tag": "rescue"})
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


def launch_rescue(script: str, extra: List[str]) -> Tuple[int, str]:
    py = sys.executable
    worker = os.path.join(_HERE, script)
    log_dir = os.path.join(_HERE, "results")
    os.makedirs(log_dir, exist_ok=True)
    tag = re.sub(r"[^a-z0-9_]+", "_", script.replace(".py", ""))[:24]
    log = os.path.join(log_dir, f"fleet_{tag}_{time.strftime('%Y%m%d_%H%M%S')}.out.log")
    cmd = [py, "-u", worker] + list(extra)
    print(f"[keeper] AUTO-RESCUE launch {script} {extra} -> {log}")
    f = open(log, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=_HERE, stdout=f, stderr=subprocess.STDOUT)
    return proc.pid, log


def ensure_rescue_slot(st: dict, stagger: float) -> dict:
    """救援槽空 → 在候选里选潜力最大者自动开 (不等人下令)。"""
    from rescue_auto import pick_script, scan_near_misses, sync_finished_rescues

    st = sync_finished_rescues(st)
    rescues = list_rescue()
    if rescues:
        print(f"[keeper] rescue already running pids={[r['pid'] for r in rescues]}")
        return st

    cands = scan_near_misses(st)
    with open(RESCUE_QUEUE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "policy": "rescue_slot_max_potential_first",
                "candidates": cands[:12],
                "rescue_done": st.get("rescue_done") or [],
                "rescue_abandoned": st.get("rescue_abandoned") or [],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    if not cands:
        print("[keeper] auto-rescue: no near-miss candidates")
        return st

    # 硬规则: 永远取潜力分最高
    cand = max(cands, key=lambda x: float(x.get("score") or 0))
    print(
        f"[keeper] auto-rescue pick MAX-POTENTIAL "
        f"{cand['dataset']} mode={cand['mode']} score={cand.get('score'):.1f} "
        f"S={cand.get('sharpe')} F={cand.get('fitness')} TVR={cand.get('tvr')} M={cand.get('margin_bp')}"
    )
    if len(cands) > 1:
        alt = cands[1]
        print(
            f"[keeper] auto-rescue runner-up {alt['dataset']} mode={alt['mode']} "
            f"score={alt.get('score'):.1f}"
        )

    script, extra, ckpt = pick_script(cand)
    worker = os.path.join(_HERE, script)
    if not os.path.exists(worker):
        print(f"[keeper] auto-rescue skip: missing {script}")
        return st

    # 错峰, 避免与探索齐射
    if list_miners():
        print(f"[keeper] auto-rescue stagger {stagger:.0f}s ...")
        time.sleep(stagger)

    pid, log = launch_rescue(script, extra)
    hist = list(st.get("rescue_launched") or [])
    hist.append(
        {
            "dataset": cand["dataset"],
            "mode": cand["mode"],
            "script": script,
            "pid": pid,
            "log": log,
            "ckpt": ckpt,
            "score": cand.get("score"),
            "priority": "max_potential",
            "reason": {
                "sharpe": cand.get("sharpe"),
                "fitness": cand.get("fitness"),
                "tvr": cand.get("tvr"),
                "margin_bp": cand.get("margin_bp"),
                "field": cand.get("field"),
                "source": cand.get("source"),
            },
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    st["rescue_launched"] = hist[-40:]
    st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[keeper] AUTO-RESCUE started {cand['dataset']} mode={cand['mode']} "
        f"score={cand.get('score'):.1f} S={cand.get('sharpe')} F={cand.get('fitness')} "
        f"TVR={cand.get('tvr')} pid={pid}"
    )
    _save_state(st)
    return st


def fill_to_target(target: int, stagger: float, st: dict) -> dict:
    miners = list_miners()
    rescues = list_rescue()
    n = len(miners)
    print(
        f"[keeper] explore={n}/{target} rescue={len(rescues)} "
        f"tags={[m['tag'] for m in miners]} "
        f"rescue_pids={[r['pid'] for r in rescues]}"
    )
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
    rescues2 = list_rescue()
    with open(ACTIVE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "explore_target": target,
                "rescue_slots": 1,
                "final_size": len(miners2),
                "rescue_alive": len(rescues2),
                "procs": [{"job": m["tag"], "pid": m["pid"]} for m in miners2],
                "rescue_procs": [{"job": r["tag"], "pid": r["pid"]} for r in rescues2],
                "updated": st["updated"],
                "keeper": True,
                "policy": "7_explore_plus_1_rescue",
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
    ap.add_argument(
        "--no-auto-rescue",
        action="store_true",
        help="关闭近关自动开救援",
    )
    ap.add_argument(
        "--auto-rescue",
        action="store_true",
        help="强制开启自动救援 (默认开)",
    )
    args = ap.parse_args()
    auto_rescue = AUTO_RESCUE_DEFAULT
    if args.no_auto_rescue:
        auto_rescue = False
    if args.auto_rescue:
        auto_rescue = True

    from fleet_singleton import acquire_keeper_singleton, reap_orphan_workers, refresh_claim

    print(
        f"[keeper] start target={args.target} stagger={args.stagger}s poll={args.poll}s "
        f"auto_rescue={auto_rescue}"
    )
    if not acquire_keeper_singleton(force=bool(args.once)):
        print("[keeper] abort: another submit_gate fleet_keeper owns this account")
        sys.exit(2)

    st = _load_state()
    build_queue(st)
    _save_state(st)

    while True:
        # 先补探索, 再填救援 (救援错峰在 ensure 内)
        st = fill_to_target(args.target, args.stagger, st)
        if auto_rescue:
            try:
                st = ensure_rescue_slot(st, args.stagger)
            except Exception as e:
                print(f"[keeper] auto-rescue error: {e}")
        # 本账号只保留本 keeper 名下的 scan_* 提交者
        keep = {m["pid"] for m in list_miners()} | {r["pid"] for r in list_rescue()}
        killed = reap_orphan_workers(keep)
        if killed:
            print(f"[keeper] reaped orphan submitters: {killed}")
        refresh_claim(sorted(keep))

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
