import sys, json, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
s = api.session
BASE = "https://api.worldquantbrain.com"
AID = "KPELQn7l"   # gz_t2_b66z252_TOP3000_d2_SEC_t1, self_corr=0.8714 (9个里最低)

desc = ("PPA alpha on USA TOP3000 EQUITY. Signal = rank(group_zscore("
        "ts_zscore(ts_backfill(eur_top_value_2, 66), 252), industry)). "
        "Earnings-value reversal composite using unlit pyramid dataset eur_top_value_2, "
        "sector-neutralized, decay 2, delay 1, test period P6Y. "
        "Captures cross-sectional value reversion with low turnover.")
print(">> PATCH description ...")
r0 = s.patch(urljoin(BASE, f"alphas/{AID}"),
             json={"name": "ppa_usa_top3000_eur_value_rev_v39b_w252_d2",
                   "regular": {"description": desc}, "color": "GREEN"})
print("   PATCH:", r0.status_code)

print(">> POST /submit (单次提交实测) ...")
t0 = time.time()
r = s.post(urljoin(BASE, f"alphas/{AID}/submit"))
print("   http:", r.status_code)
print("   headers:", {k: v for k, v in r.headers.items() if k.lower() in
                      ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after")})
print("   body:", r.text[:600])

if r.status_code in (200, 201, 202):
    for i in range(12):
        d = api.get_alpha_details(AID)
        st = d.get("status")
        print(f"   poll[{i}] status={st} submittedAt={d.get('dateSubmitted')}")
        if st and st != "UNSUBMITTED":
            break
        time.sleep(5)
    d = api.get_alpha_details(AID)
    print("FINAL:", AID, "| status=", d.get("status"), "| dateSubmitted=", d.get("dateSubmitted"))
    chk = api.get_alpha_check(AID)
    if chk:
        items = chk.get("is", {}).get("checks", []) if isinstance(chk, dict) else chk
        if isinstance(items, list):
            print("   IS after attempt:", [(c.get("name"), c.get("result")) for c in items])
else:
    print("!! POST 未被接受 -> 提交被平台拒绝（硬闸门或配额）")
