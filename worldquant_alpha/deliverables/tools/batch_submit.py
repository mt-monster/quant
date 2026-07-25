#!/usr/bin/env python3
"""批量检查候选 alpha 闸门 + 通过则提交。"""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin
import glob

BASE = "https://api.worldquantbrain.com"
api = WqApiSimple()
s = api.session

# 1) 加载候选
cands = []
for f in sorted(glob.glob("results/*_checkpoint.json")):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except:
        continue
    task = os.path.basename(f).replace("_checkpoint.json", "")
    for r in d.get("results", []):
        st = str(r.get("status", ""))
        if st in ("PASS_CHEAP", "CHECK_PENDING"):
            cands.append({"pid": r["pid"], "task": task, "label": r.get("label", ""),
                          "sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
                          "expr": r.get("expr", "")[:140], "status": st})
cands.sort(key=lambda x: -(x["sharpe"] or 0))
print(f"Loaded {len(cands)} candidates. Checking gates...\n")

submitted = 0
already_ok = 0
failed_gate = 0
no_checks = 0

for i, c in enumerate(cands):
    pid = c["pid"]
    # Skip if already submitted
    det = api.get_alpha_details(pid)
    cur_st = det.get("status", "")
    cur_sub = det.get("dateSubmitted")
    if cur_st and cur_st != "UNSUBMITTED":
        already_ok += 1
        if i < 5:
            print(f"  [{i+1}/{len(cands)}] {pid} (S={c['sharpe']:.2f}) — already {cur_st} (submitted {cur_sub})")
        continue

    # Check IS gates
    try:
        chk = s.get(urljoin(BASE, f"alphas/{pid}/check"), timeout=60)
        if not chk.ok or not chk.text.strip():
            no_checks += 1
            continue
        cj = chk.json()
        checks = (cj.get("is") or {}).get("checks") or []
        fails = [x for x in checks if x.get("result") == "FAIL"]
        if fails:
            failed_gate += 1
            continue
        if not checks:
            no_checks += 1
            continue
    except Exception as e:
        no_checks += 1
        continue

    # GATES PASS — submit!
    print(f"  [{i+1}/{len(cands)}] {pid} (S={c['sharpe']:.2f}) — ALL GATES PASS. Submitting...")

    desc = (
        f"PPA alpha on USA EQUITY TOP3000. "
        f"IS sharpe={c['sharpe']}, fitness={c['fitness']}. "
        f"Low turnover design with industry neutralization. "
        f"Submitted for PPA program evaluation."
    )
    try:
        s.patch(urljoin(BASE, f"alphas/{pid}"),
                json={"name": f"ppa_{c['label']}"[:80], "regular": {"description": desc}, "color": "GREEN"})
        r = s.post(urljoin(BASE, f"alphas/{pid}/submit"))
        ok = r.status_code in (200, 201, 202)

        # Poll
        for _ in range(36):
            d = api.get_alpha_details(pid)
            st = d.get("status"); dsub = d.get("dateSubmitted")
            if dsub or (st and st != "UNSUBMITTED"):
                break
            time.sleep(5)

        d = api.get_alpha_details(pid)
        if d.get("status") == "ACTIVE":
            submitted += 1
            print(f"    >>> ACTIVE — submitted! ({d.get('dateSubmitted')})")
        else:
            print(f"    >>> {d.get('status')} — gate failure (needs OOS)")
    except Exception as e:
        print(f"    error: {e}")

    time.sleep(1)

# Summary
print(f"\n{'='*50}")
print(f"TOTAL: {len(cands)} candidates")
print(f"  Already submitted/active: {already_ok}")
print(f"  Freshly submitted (just now): {submitted}")
print(f"  Gate check failed: {failed_gate}")
print(f"  No platform checks (needs OOS): {no_checks}")
print(f"\nYPgAa3WR status:")
d = api.get_alpha_details("YPgAa3WR")
print(f"  status={d.get('status')} dateSubmitted={d.get('dateSubmitted')}")
