import json, sys, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
pid = "YPgAa3WR"
BASE = "https://api.worldquantbrain.com"
s = api.session

# ---- 优化：补合规 description，消除 POWER_POOL_DESCRIPTION WARNING ----
desc = ("Insider-matrix residual quality factor. Signal ranks the industry-neutralized, "
        "time-zscored (189d window) backfilled Eur top-value-2 (66d backfill), capturing "
        "cross-sectional value persistence with low turnover and robust sub-universe coverage. "
        "Region USA, universe TOP3000, delay 1, SECTOR neutralization, decay 3, pasteurized, "
        "P6Y test period.")
print(">> PATCH description ...")
pr = s.patch(urljoin(BASE, f"alphas/{pid}"), json={"description": desc})
print("   PATCH status:", pr.status_code, (pr.text[:200] if pr.status_code >= 400 else "OK"))

# ---- 提交 ----
print(">> POST submit ...")
r = s.post(urljoin(BASE, f"alphas/{pid}/submit"))
print("   SUBMIT http:", r.status_code, r.text[:600])

if r.status_code in (200, 201):
    for _ in range(15):
        d = api.get_alpha_details(pid)
        st = d.get("status")
        print(f"   poll status: {st}")
        if st and st not in ("COMPLETE", "IN_PROGRESS", "SIMULATING", "RUNNING"):
            break
        time.sleep(3)
    keep = {k: d.get(k) for k in ("alpha", "status", "submitted_at", "submission_status") if k in d}
    print(">> FINAL:", json.dumps(keep, ensure_ascii=False))
else:
    print(">> 提交未成功（见上），未对平台产生提交记录。")
