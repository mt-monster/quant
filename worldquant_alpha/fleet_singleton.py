#!/usr/bin/env python3
"""本 BRAIN 账号只允许一套 fleet (走 submit_gate) 常驻。

- fleet_keeper 启动时抢单实例锁；已有存活 keeper 则新进程退出
- 可列出/清理 worldquant_alpha 下游离的 scan_tri_job / scan_rescue_*
- 不碰其他账号进程 (百度 gmail / MCP 等)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(_HERE, "results")
LOCK = os.path.join(RESULTS, ".fleet_keeper_singleton.lock")
CLAIM = os.path.join(RESULTS, ".brain_account_fleet.json")

# 本仓库脚本名 (百度侧是 continuous_undug 等, 不会误伤)
OUR_PAT = re.compile(r"scan_tri_job\.py|scan_rescue_.*\.py|fleet_keeper\.py", re.I)
KEEPER_PAT = re.compile(r"fleet_keeper\.py", re.I)
WORKER_PAT = re.compile(r"scan_tri_job\.py|scan_rescue_.*\.py", re.I)


def _load_username() -> str:
    env = os.path.join(_HERE, ".env")
    if not os.path.exists(env):
        return ""
    for line in open(env, encoding="utf-8", errors="ignore"):
        if line.strip().startswith("WQ_USERNAME"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def mask_user(u: str) -> str:
    if not u:
        return ""
    if "@" in u:
        local, dom = u.split("@", 1)
        return (local[:2] + "***@" + dom) if local else "***@" + dom
    return u[:2] + "***" if len(u) > 2 else "***"


def list_python_procs() -> List[Dict]:
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
        if not cmd or not pid:
            continue
        out.append({"pid": int(pid), "cmd": cmd})
    return out


def list_our_fleet_procs() -> List[Dict]:
    return [p for p in list_python_procs() if OUR_PAT.search(p["cmd"].replace("/", "\\"))]


def pid_alive(pid: int) -> bool:
    try:
        subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-Process -Id {int(pid)} -ErrorAction Stop | Out-Null; '1'",
            ],
            text=True,
            errors="ignore",
        )
        return True
    except Exception:
        return False


def acquire_keeper_singleton(force: bool = False) -> bool:
    """成功返回 True；已有其他存活 keeper 则 False。"""
    os.makedirs(RESULTS, exist_ok=True)
    my_pid = os.getpid()
    if os.path.exists(LOCK) and not force:
        try:
            old = json.load(open(LOCK, encoding="utf-8"))
            opid = int(old.get("pid") or 0)
            if opid and opid != my_pid and pid_alive(opid):
                # 确认仍是 fleet_keeper
                for p in list_python_procs():
                    if p["pid"] == opid and KEEPER_PAT.search(p["cmd"]):
                        print(f"[singleton] another fleet_keeper alive pid={opid}; exit")
                        return False
        except Exception:
            pass

    # 杀掉其他 fleet_keeper (同仓库)
    for p in list_our_fleet_procs():
        if KEEPER_PAT.search(p["cmd"]) and p["pid"] != my_pid:
            print(f"[singleton] kill duplicate keeper pid={p['pid']}")
            try:
                subprocess.check_call(
                    ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {p['pid']} -Force"],
                )
            except Exception as e:
                print(f"[singleton] kill failed: {e}")

    claim = {
        "pid": my_pid,
        "account": mask_user(_load_username()),
        "account_domain": (_load_username().split("@")[-1] if "@" in _load_username() else ""),
        "role": "fleet_keeper_submit_gate_owner",
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cwd": _HERE,
        "policy": "one_fleet_per_account_via_submit_gate",
    }
    with open(LOCK, "w", encoding="utf-8") as f:
        json.dump(claim, f, ensure_ascii=False, indent=2)
    with open(CLAIM, "w", encoding="utf-8") as f:
        json.dump(claim, f, ensure_ascii=False, indent=2)
    print(f"[singleton] acquired keeper lock pid={my_pid} account={claim['account']}")
    return True


def reap_orphan_workers(keep_pids: Optional[set] = None) -> List[int]:
    """杀掉本仓库下、非 keep_pids 的 scan_tri_job/scan_rescue (游离提交者)。"""
    keep_pids = set(keep_pids or [])
    keep_pids.add(os.getpid())
    killed = []
    for p in list_our_fleet_procs():
        if not WORKER_PAT.search(p["cmd"]):
            continue
        if p["pid"] in keep_pids:
            continue
        print(f"[singleton] reap orphan submitter pid={p['pid']}")
        try:
            subprocess.check_call(
                ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {p['pid']} -Force"],
            )
            killed.append(p["pid"])
        except Exception as e:
            print(f"[singleton] reap failed pid={p['pid']}: {e}")
    return killed


def refresh_claim(worker_pids: List[int]) -> None:
    u = _load_username()
    data = {
        "pid": os.getpid(),
        "account": mask_user(u),
        "account_domain": u.split("@")[-1] if "@" in u else "",
        "role": "fleet_keeper_submit_gate_owner",
        "workers": worker_pids,
        "n_workers": len(worker_pids),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "policy": "one_fleet_per_account_via_submit_gate",
        "note": "百度/MCP 若不同邮箱则互不抢本账号令牌；本账号仅此套走 submit_gate",
    }
    with open(CLAIM, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 诊断
    u = _load_username()
    print("account", mask_user(u))
    procs = list_our_fleet_procs()
    print("our_fleet_procs", len(procs))
    for p in procs:
        print(" ", p["pid"], p["cmd"][:120])
