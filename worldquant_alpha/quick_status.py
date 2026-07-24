import sys, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
a = WqApiSimple()
d = a.get_alpha_details("YPgAa3WR")
for k in ("alpha", "status", "submission_status", "submitted_at", "submitted", "state", "type"):
    if k in d:
        print(f"{k:18} = {d.get(k)}")
# 也看 is 里是否有 submission 相关检查
is_ = d.get("is", {})
if isinstance(is_, dict):
    subs = [c for c in is_.get("checks", []) if "SUBMIT" in str(c.get("name","")) or "GATEWAY" in str(c.get("name",""))]
    for c in subs:
        print("SUB_CHECK:", c.get("name"), c.get("result"), c.get("value"), c.get("limit"))
