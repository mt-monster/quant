import json, sys
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple

api = WqApiSimple()
pid = "YPgAa3WR"
c = api.get_alpha_check(pid)
print("check 响应顶层键:", list(c.keys()) if isinstance(c, dict) else type(c))
is_ = c.get("is", c) if isinstance(c, dict) else {}
if isinstance(is_, dict):
    print("IS 顶层键:", list(is_.keys()))
    checks = is_.get("checks", [])
    print(f"\n总检查数: {len(checks)}")
    for ch in checks:
        print(f"  {str(ch.get('name')):34} result={str(ch.get('result')):7} value={ch.get('value')} limit={ch.get('limit')}")
