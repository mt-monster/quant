# -*- coding: utf-8 -*-
"""列出 GLB MINVOL1M 未点亮数据集, 按可挖性排序"""
import json, os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "glb_unlit_discovery.json")
d = json.load(open(P, encoding="utf-8"))
ds = d["datasets"]["MINVOL1M"]
print(f"total unlit MINVOL1M: {len(ds)}")

# 可挖性: 覆盖>0.85, 字段数适中, alphaCount 高说明该数据集出 alpha 可行性强
rows = [x for x in ds if x.get("coverage", 0) >= 0.85]
rows.sort(key=lambda x: -(x.get("alphaCount", 0)))
print(f"{'id':22s} {'category':12s} {'fields':>6s} {'cov':>5s} {'users':>6s} {'alphas':>6s} {'vs':>4s} {'pyr':>4s}  name")
for x in rows[:30]:
    print(f"{x['id']:22s} {x.get('category','?'):12s} {x.get('fieldCount',0):6d} {x.get('coverage',0):5.2f} "
          f"{x.get('userCount',0):6d} {x.get('alphaCount',0):6d} {x.get('valueScore',0):4.1f} {x.get('pyramidMultiplier',0):4.2f}  {x.get('name','')}")
