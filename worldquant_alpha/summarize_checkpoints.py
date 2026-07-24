import sys, json
from collections import Counter
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")

def summ(name, path):
    try:
        with open(path, encoding="utf-8") as f:
            ck = json.load(f)
    except Exception as e:
        print(f"[{name}] 读取失败: {e}"); return
    res = ck.get("results", [])
    fa = ck.get("found_alphas", [])
    cnt = Counter(r.get("status") for r in res)
    print(f"\n===== {name} =====")
    print(f"  总变体: {len(res)} | 状态分布: {dict(cnt)}")
    print(f"  found_alphas: {len(fa)}")
    for a in fa:
        print(f"    - {a.get('label')} | S={a.get('sharpe')} F={a.get('fitness')} "
              f"tvr={a.get('tvr')} pid={a.get('pid')} sub_univ={a.get('sub_univ')}")
    # 候选(非FAIL)但未进 found 的
    cands = [r for r in res if r.get("status") not in ("FAIL",) and r.get("status")]
    print(f"  非FAIL 结果条数: {len(cands)}")

for nm, p in [
    ("V40 cre_exposure", r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha\results\v40_cre_checkpoint.json"),
    ("V41 earn_risk",   r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha\results\v41_earn_risk_checkpoint.json"),
]:
    summ(nm, p)
