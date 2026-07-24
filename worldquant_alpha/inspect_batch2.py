import sys, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
ckpt_path = r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha\results\v39b_sub_micro_checkpoint.json"
with open(ckpt_path, encoding="utf-8") as f:
    ck = json.load(f)

# 看一条 result 的结构
r0 = ck["results"][0]
print("result[0] keys:", list(r0.keys()))
print("result[0] sample:", {k: (str(v)[:60] if not isinstance(v,(int,float,bool)) else v) for k,v in r0.items()})

# 统计 status 取值分布
from collections import Counter
cnt = Counter(r.get("status") for r in ck["results"])
print("\nstatus 分布:", dict(cnt))

# 找 PASS_CHEAP 标记
for r in ck["results"]:
    if "PASS_CHEAP" in str(r.get("status","")) or "PASS_CHEAP" in str(r.get("label","")):
        print("\nPASS_CHEAP 候选:", r.get("label"), "| pid:", r.get("pid"), "| status:", r.get("status"),
              "| S:", r.get("sharpe"), "| sub_univ:", r.get("sub_univ"))
