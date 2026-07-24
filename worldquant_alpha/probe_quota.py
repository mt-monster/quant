import sys, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
s = api.session
BASE = "https://api.worldquantbrain.com"

def show(label, r):
    print(f"\n>> {label} -> {r.status_code}")
    try:
        j = r.json()
    except Exception:
        print("   body:", r.text[:300]); return
    if isinstance(j, dict):
        for k in ("submissionLimit", "submission_limit", "submissionsLimit",
                 "weeklySubmissionLimit", "submissionQuota", "quota",
                 "submissionsUsed", "submissionsThisWeek", "limit", "used"):
            if k in j:
                print(f"   {k} = {j[k]}")
        # 打印全部顶层 key（便于发现隐藏字段）
        print("   keys:", list(j.keys())[:40])
        # 递归找含 submission 的字段
        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    if "submiss" in k.lower() or "quota" in k.lower() or "limit" in k.lower():
                        print(f"   [found] {path}{k} = {v}")
                    walk(v, f"{path}{k}.")
            elif isinstance(o, list) and o and isinstance(o[0], dict):
                walk(o[0], f"{path}[0].")
        walk(j)
    else:
        print("   (non-dict)", str(j)[:200])

for ep in ["users/self", "users/me", "user", "alphas/submissions",
           "submission-limit", "alphas/submission-limit", "accounts/self"]:
    try:
        show(ep, s.get(urljoin(BASE, ep), timeout=20))
    except Exception as e:
        print(f"\n>> {ep} -> EXC {e}")
