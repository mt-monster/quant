#!/usr/bin/env python3
"""双账号提交工具：--account main 用 mthyzx@126 / --account tri 用 mthyzx@gmail(ML88164)"""
import sys, json, time, os, glob, requests, argparse
from requests.auth import HTTPBasicAuth

BASE = "https://api.worldquantbrain.com"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

ACCOUNTS = {
    "main": {"email": "mthyzx@126.com", "pwd": "asdqwe123!", "label": "主账号 mthyzx"},
    "tri": {"email": "mthyzx@gmail.com", "pwd": "asdqwe123!", "label": "tri_track ML88164"},
}

def make_session(acct):
    cfg = ACCOUNTS[acct]
    s = requests.Session()
    s.auth = HTTPBasicAuth(cfg["email"], cfg["pwd"])
    r = s.post(f"{BASE}/authentication", timeout=60)
    uid = r.json().get("user", {}).get("id", "?")
    print(f"[{cfg['label']}] auth OK, user={uid}")
    return s

def get_tri_pids(top_n=10):
    ckpt = r"D:\BaiduNetdiskDownload\WQ第二三四节课代码\worldquant\tri_track_undug_checkpoint.json"
    d = json.load(open(ckpt, encoding="utf-8"))
    pids = [(r["pid"], float(r.get("sharpe") or 0), r.get("track","?"))
            for r in d.get("results", []) if r.get("pid")]
    return sorted(pids, key=lambda x: -x[1])[:top_n]

def get_main_pids(top_n=10):
    RES = os.path.join(ROOT, "results")
    pids = set()
    for f in sorted(glob.glob(os.path.join(RES, "*_checkpoint.json"))):
        d = json.load(open(f, encoding="utf-8"))
        items = d if isinstance(d, list) else d.get("results", [])
        for r in items:
            pid = r.get("pid")
            if pid and str(r.get("status","")) in ("PASS_CHEAP","CHECK_PENDING"):
                pids.add((pid, float(r.get("sharpe") or 0), f.replace("results/","").replace("_checkpoint.json","")))
    return sorted(pids, key=lambda x: -x[1])[:top_n]

def submit(session, pids, cooldown=15):
    results = {}
    for i, (pid, sharpe, task) in enumerate(pids):
        if i > 0:
            time.sleep(cooldown)
        print(f"[{i+1}/{len(pids)}] {pid} (S={sharpe:.2f}, {task}):", end=" ", flush=True)
        try:
            r = session.post(f"{BASE}/alphas/{pid}/submit", timeout=60)
            code = r.status_code
            if code == 429:
                print("RATE_LIMIT"); results[pid] = "RATELIMIT"; time.sleep(30); continue
            if code >= 400:
                print(f"HTTP{code} ({r.text[:80]})"); results[pid] = f"HTTP{code}"; continue
            print(f"HTTP{code}", end=" ")
            for j in range(12):
                time.sleep(5)
                r2 = session.get(f"{BASE}/alphas/{pid}", timeout=15)
                if r2.status_code == 200:
                    d = r2.json()
                    st = d.get("status","?"); ds = d.get("dateSubmitted")
                    if ds or st in ("ACTIVE","FAIL"):
                        print(f"-> {st}"); results[pid] = f"{st}({str(ds)[:16] if ds else ''})"; break
                if j % 3 == 0: print(".", end="", flush=True)
            else: print("TIMEOUT"); results[pid] = "TIMEOUT"
        except Exception as e:
            print(f"ERROR:{e}"); results[pid] = "ERROR"
    return results

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", choices=["main","tri"], default="tri")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--cooldown", type=int, default=15)
    args = ap.parse_args()

    session = make_session(args.account)
    pids = get_tri_pids(args.top) if args.account == "tri" else get_main_pids(args.top)
    if not pids: print("No PIDs found"); sys.exit(1)
    print(f"Submitting {len(pids)} PIDs via {ACCOUNTS[args.account]['label']}")

    results = submit(session, pids, args.cooldown)

    for pid, r in results.items(): print(f"  {pid}: {r}")

    # update verified cache
    vf_path = os.path.join(ROOT, "results", "_platform_verified.json")
    verified = json.load(open(vf_path)) if os.path.exists(vf_path) else {}
    for pid, r in results.items():
        if "ACTIVE" in str(r): verified[pid] = {"status": "ACTIVE", "dateSubmitted": r}
        elif "FAIL" in str(r): verified[pid] = {"status": "GATE_FAIL", "note": r}
        elif "POLL" in str(r) or "TIMEOUT" in str(r): verified[pid] = {"status": "UNSUBMITTED", "note": r}
    json.dump(verified, open(vf_path, "w"), indent=2, ensure_ascii=False)
    print(f"Updated {vf_path}")
