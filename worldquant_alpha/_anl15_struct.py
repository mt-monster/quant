# -*- coding: utf-8 -*-
"""analyst15 字段结构速览: 公司级 vs sector级, 按前缀族分组, 高覆盖高alphaCount优先."""
import json, os, re, collections, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "glb_fields_analyst15.json")
d = json.load(open(P, encoding="utf-8"))
m = [x for x in d if x["type"] == "MATRIX"]
print(f"total={len(d)} matrix={len(m)}")

# sector 级 (anl15_s_) vs 公司级
sec = [x for x in m if x["id"].startswith("anl15_s_")]
co = [x for x in m if not x["id"].startswith("anl15_s_")]
print(f"sector-level={len(sec)} company-level={len(co)}")

print("\n=== company-level top40 by alphaCount ===")
for x in sorted(co, key=lambda x: -(x["alphaCount"] or 0))[:40]:
    print(f"{x['id']:40s} cov={x['coverage']} a={x['alphaCount']:5d} u={x['userCount']:4d} | {(x['description'] or '')[:75]}")

# 前缀族分组
fam = collections.Counter()
for x in co:
    mm = re.match(r"anl15_([a-z0-9]+)_", x["id"])
    fam[mm.group(1) if mm else x["id"]] += 1
print("\n=== company-level prefix families ===")
for k, v in fam.most_common(30):
    print(f"  {k}: {v}")

# 高覆盖公司级字段 (cov>=0.95)
hi = [x for x in co if (x["coverage"] or 0) >= 0.95]
print(f"\n=== company-level cov>=0.95: {len(hi)} ===")
for x in sorted(hi, key=lambda x: -(x["alphaCount"] or 0))[:40]:
    print(f"  {x['id']:40s} cov={x['coverage']} a={x['alphaCount']:5d} | {(x['description'] or '')[:70]}")
