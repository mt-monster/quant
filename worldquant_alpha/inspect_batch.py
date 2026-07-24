import sys, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
ckpt_path = r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha\results\v39b_sub_micro_checkpoint.json"
with open(ckpt_path, encoding="utf-8") as f:
    ck = json.load(f)
print("top-level type:", type(ck).__name__)
if isinstance(ck, dict):
    print("top-level keys:", list(ck.keys()))
    for k, v in ck.items():
        if isinstance(v, list):
            print(f"  {k}: list len={len(v)}")
        else:
            print(f"  {k}: {type(v).__name__}")
elif isinstance(ck, list):
    print("list len:", len(ck))
    print("element[0] keys:", list(ck[0].keys()) if ck else "empty")
