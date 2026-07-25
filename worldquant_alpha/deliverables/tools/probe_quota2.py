import sys, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
s = api.session
BASE = "https://api.worldquantbrain.com"
r = s.get(urljoin(BASE, "users/self"), timeout=20)
j = r.json()

import re
terms = re.compile(r"submiss|quota|limit|week|max|rate", re.I)
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if terms.search(k):
                print(f"[KEY] {path}{k} = {v if not isinstance(v,(dict,list)) else type(v).__name__}")
            walk(v, f"{path}{k}.")
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]):
            walk(v, f"{path}[{i}].")

print(">> 递归搜索 users/self 中含 submiss/quota/limit/week/max/rate 的字段：")
walk(j)

# 单独打印可能相关的子对象（截断）
for sub in ["settings", "auxiliary", "onboarding", "recruitment"]:
    if sub in j:
        print(f"\n>> {sub} (节选):")
        print(json.dumps(j[sub], ensure_ascii=False, indent=1)[:800])
