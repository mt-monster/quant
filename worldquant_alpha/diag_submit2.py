import sys, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
BASE = "https://api.worldquantbrain.com"
s = api.session
AID = "YPgAa3WR"

print(">> GET /alphas/%s/submit (提交资格/表单)" % AID)
r = s.get(urljoin(BASE, f"alphas/{AID}/submit"), timeout=30)
print("status:", r.status_code)
try:
    body = r.json()
    print(json.dumps(body, indent=2, ensure_ascii=False)[:2000])
except Exception:
    print(r.text[:2000])

print("=" * 60)
print(">> 检查 alpha 是否有 submissionStatus 字段 / 其它提交线索")
d = api.get_alpha_details(AID)
for k in ["submissionStatus", "submittedAt", "stage", "grade"]:
    print(f"   {k}: {d.get(k)}")
print("   stage/grade:", d.get("stage"), d.get("grade"))
