import sys, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
api = WqApiSimple()
AID = "YPgAa3WR"
d = api.get_alpha_details(AID)
print("status:", d.get("status"))
print("submittedAt:", d.get("dateSubmitted") or d.get("submittedAt"))
print("color:", d.get("color"))
print("name:", d.get("name"))
print("regular.description len:", len(d.get("regular", {}).get("description", "")))
chk = api.get_alpha_check(AID)
if chk:
    items = chk.get("is", {}).get("checks", []) if isinstance(chk, dict) else chk
    if isinstance(items, list):
        fails = [c for c in items if c.get("result") == "FAIL"]
        warns = [c for c in items if c.get("result") == "WARNING"]
        passes = [c for c in items if c.get("result") == "PASS"]
        print(f"IS checks: PASS={len(passes)} WARNING={len(warns)} FAIL={len(fails)} (total {len(items)})")
        for c in items:
            print(f"   {c.get('name')}: {c.get('result')} (value={c.get('value')})")
    else:
        print("checks structure:", json.dumps(chk, ensure_ascii=False)[:500])
else:
    print("no check data")
