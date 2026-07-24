import sys, json, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
s = api.session
BASE = "https://api.worldquantbrain.com"
AID = "YPgAa3WR"

# 1) 修正 description（正确的嵌套 regular.description 形式；旧的 flat 'description' 会被 400）
desc = ("PPA alpha on USA TOP3000 EQUITY. Signal = rank(group_zscore("
        "ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry)). "
        "Earnings-value reversal composite using unlit pyramid dataset eur_top_value_2, "
        "sector-neutralized, decay 3, delay 1, test period P6Y. "
        "Designed to capture cross-sectional value reversion with low turnover.")
print(">> PATCH metadata (nested regular.description) ...")
patch = {"name": "ppa_usa_top3000_eur_value_rev_v39b",
         "regular": {"description": desc},
         "color": "GREEN"}
r0 = s.patch(urljoin(BASE, f"alphas/{AID}"), json=patch)
print("   PATCH status:", r0.status_code, r0.text[:200])

# 2) 重新拉取，确认 description 已生效
d = api.get_alpha_details(AID)
print("   new regular.description:", d.get("regular", {}).get("description", "")[:80], "...")
print("   new status:", d.get("status"))

# 3) 提交
print(">> POST /alphas/%s/submit ..." % AID)
r = s.post(urljoin(BASE, f"alphas/{AID}/submit"))
print("   SUBMIT http:", r.status_code, "body:", r.text[:300])

# 4) 轮询（最多 3 分钟）
if r.status_code in (200, 201, 202):
    for i in range(36):
        d = api.get_alpha_details(AID)
        st = d.get("status")
        sst = d.get("submissionStatus")
        ds = d.get("dateSubmitted") or d.get("submittedAt")
        print(f"   poll[{i}] status={st} submissionStatus={sst} submitted={ds}")
        if st and st != "UNSUBMITTED":
            break
        time.sleep(5)
    print("FINAL:", AID, "| status =", d.get("status"),
          "| submissionStatus =", d.get("submissionStatus"),
          "| submittedAt =", d.get("dateSubmitted") or d.get("submittedAt"))
else:
    print("!! 提交未被接受 (http %s)" % r.status_code)
