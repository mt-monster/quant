# -*- coding: utf-8 -*-
"""analyst10 字段结构速览: MATRIX 字段按 alphaCount 排序 + 关键词族分组."""
import json, os, re, collections

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "glb_fields_analyst10.json")
d = json.load(open(P, encoding="utf-8"))
m = [x for x in d if x["type"] == "MATRIX"]

print("=== MATRIX top30 by alphaCount ===")
for x in sorted(m, key=lambda x: -(x["alphaCount"] or 0))[:30]:
    print(f"{x['id']:44s} cov={x['coverage']} a={x['alphaCount']:5d} | {(x['description'] or '')[:70]}")

# 按指标族分组 (eps/net/rev/cps/bps/dps...)
fam = collections.Counter()
for x in m:
    mm = re.match(r"anl10_([a-z]+?)(ff|fy1|fy2|smun|past)", x["id"])
    fam[mm.group(1) if mm else "?"] += 1
print("\n=== metric families (MATRIX) ===")
for k, v in fam.most_common():
    print(f"  {k}: {v}")

# 低覆盖警报
low = [x for x in m if (x["coverage"] or 0) < 0.95]
print(f"\n=== MATRIX cov<0.95: {len(low)} ===")
for x in low[:15]:
    print(f"  {x['id']} cov={x['coverage']}")
