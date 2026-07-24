import sys, json, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
BASE = "https://api.worldquantbrain.com"
s = api.session

expr = "rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))"
settings = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
    "decay": 3, "neutralization": "SECTOR", "truncation": 0.01, "pasteurization": "ON",
    "unitHandling": "VERIFY", "nanHandling": "ON", "language": "FASTEXPR",
    "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
}

print(">> 重新模拟 (fresh) ...")
res = api.run_backtest(expr, settings, max_wait_time=1200)
print("sim:", res)
if not res or not res.get("platform_id"):
    print("!! 模拟失败，终止")
else:
    nid = res["platform_id"]
    d0 = api.get_alpha_details(nid)
    is0 = d0.get("is", {})
    print(f"   fresh alpha_id = {nid}  S={is0.get('sharpe')} F={is0.get('fitness')} subUniv={is0.get('subUniverse')}")
    print(">> 提交 fresh id ...")
    r = s.post(urljoin(BASE, f"alphas/{nid}/submit"))
    print("   SUBMIT http:", r.status_code, r.text[:400])
    if r.status_code in (200, 201):
        for _ in range(30):
            d = api.get_alpha_details(nid)
            st = d.get("status")
            print(f"   poll [{_}]: {st}")
            if st and st != "UNSUBMITTED":
                break
            time.sleep(5)
        print("FINAL:", nid, "| status =", d.get("status"), "| submitted_at =", d.get("submitted_at"))
    else:
        print("!! 提交未成功")
