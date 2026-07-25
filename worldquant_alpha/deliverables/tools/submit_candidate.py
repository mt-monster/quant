#!/usr/bin/env python3
"""Submit a WQ alpha candidate. Usage: python submit_candidate.py <AID>"""
import sys, json, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

BASE = "https://api.worldquantbrain.com"
AID = sys.argv[1] if len(sys.argv) > 1 else "zqRkPVbX"

api = WqApiSimple()
s = api.session

# Get details from checkpoint
ckpt_path = r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha\results\v52b_hiring_margin_checkpoint.json"
ck = json.load(open(ckpt_path, encoding="utf-8"))
target = next((r for r in ck["results"] if r.get("pid") == AID), None)
if not target:
    # Try v39b
    ck2 = json.load(open(ckpt_path.replace("v52b", "v39b_sub_micro"), encoding="utf-8"))
    target = next((r for r in ck2["results"] if r.get("pid") == AID), None)
if not target:
    print("AID not found in checkpoints:", AID)
    sys.exit(1)

label = target["label"]
is_s = target.get("sharpe", "?")
is_f = target.get("fitness", "?")
is_tvr = target.get("tvr", "?")
expr = target.get("expr", "")
print(f"Target: {AID} label={label} S={is_s} F={is_f} TVR={is_tvr}")

# Platform status
det = api.get_alpha_details(AID)
print(f"Current status: {det.get('status')} submitted={det.get('dateSubmitted')}")
if det.get("status") and det.get("status") != "UNSUBMITTED":
    print(f">>> Already submitted/active. Done.")
    sys.exit(0)

# Set description
desc = (
    "PPA alpha on USA TOP3000 EQUITY, delay 1, decay 4, SECTOR neutralization. "
    "Signal uses rank of industry-neutralized, z-scored, backfilled aggregate open positions count "
    "with 66-day lookback window and 63-day z-score normalization. "
    "Captures hiring demand momentum through changes in cumulative job posting volumes by firm. "
    "Low turnover via decay=4 to reduce trading cost and improve margin. "
    f"IS metrics: sharpe={is_s}, fitness={is_f}, turnover={is_tvr}. "
    "Submitted for PPA (Power Pool Alpha) program evaluation."
)
print(f"\nSetting description ({len(desc)} chars)...")
r = s.patch(urljoin(BASE, f"alphas/{AID}"),
            json={"name": f"ppa_{label}"[:80], "regular": {"description": desc}, "color": "GREEN"})
print(f"PATCH: {r.status_code}")

# Submit
print("\nPOST /submit ...")
r = s.post(urljoin(BASE, f"alphas/{AID}/submit"))
print(f"submit: {r.status_code}")
if r.text:
    print(r.text[:300])

# Poll
print("\nPolling status (up to 3 min)...")
for i in range(36):
    d = api.get_alpha_details(AID)
    st = d.get("status"); dsub = d.get("dateSubmitted")
    if i % 6 == 0 or dsub:
        print(f"  [{i*5:3d}s] status={st} submitted={dsub}")
    if dsub or (st and st != "UNSUBMITTED"):
        break
    time.sleep(5)

# Result
d = api.get_alpha_details(AID)
print(f"\n=== RESULT ===")
print(f"status: {d.get('status')}")
print(f"dateSubmitted: {d.get('dateSubmitted')}")
if d.get("status") == "ACTIVE":
    print(">>> SUBMIT SUCCESS! Now in PPA pool.")
else:
    print(">>> Still UNSUBMITTED. Reason: likely hard IS gate FAIL (SELF_CORRELATION / PROD_CORRELATION not yet validated on platform).")
    print("    Action: run production simulation (OOS) on WQ BRAIN, then retry.")
