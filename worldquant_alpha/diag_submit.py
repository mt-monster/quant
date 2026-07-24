import sys, json, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
BASE = "https://api.worldquantbrain.com"
s = api.session

AID = "YPgAa3WR"
print("=" * 60)
print(f">> 读取 alpha {AID} 当前完整状态")
d = api.get_alpha_details(AID)
if not d:
    print("!! 无法获取详情（可能 token 失效或 id 错误）")
    sys.exit(1)

# 打印关键提交相关字段
keys_of_interest = ["id", "status", "submissionStatus", "submittedAt", "name",
                    "description", "category", "tags", "color", "regular",
                    "dateCreated", "dateSubmitted"]
print("-- 顶层关键字段 --")
for k in keys_of_interest:
    if k in d:
        v = d[k]
        if isinstance(v, str) and len(v) > 120:
            v = v[:120] + "..."
        print(f"   {k}: {v}")
print("-- 其余顶层 keys --")
print("   ", [k for k in d.keys() if k not in keys_of_interest])

print("=" * 60)
print(">> 提交闸门检查 (IS check)")
chk = api.get_alpha_check(AID)
if chk:
    checks = chk.get("checks", chk) if isinstance(chk, dict) else chk
    # 兼容两种结构
    items = checks if isinstance(checks, list) else chk.get("checks", [])
    if isinstance(items, list):
        for c in items:
            name = c.get("name") or c.get("checkName") or c.get("type")
            res = c.get("result") or c.get("status")
            print(f"   {name}: {res}")
    else:
        for kk, vv in chk.items():
            if isinstance(vv, dict):
                print(f"   {kk}: {vv.get('result') or vv.get('status')}")
            else:
                print(f"   {kk}: {vv}")
else:
    print("   无 IS check 数据")

print("=" * 60)
print(">> 尝试读取 submission 相关子资源")
for sub in ["submission", "submissions", "submit"]:
    try:
        r = s.get(urljoin(BASE, f"alphas/{AID}/{sub}"), timeout=30)
        print(f"   GET alphas/{AID}/{sub} -> {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"   GET alphas/{AID}/{sub} -> EXC {e}")
