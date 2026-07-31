# -*- coding: utf-8 -*-
"""分析 sentiment21 字段结构: 组前缀 x 极性 x 统计量"""
import json, os, re
from collections import Counter

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "glb_fields_sentiment21.json")
items = json.load(open(P, encoding="utf-8"))
print("total:", len(items))

pat = re.compile(r"^snt21_(\w+?)(pos|neg|neut|dts)_(\w+?)_(\d+)$")
groups, stats = Counter(), Counter()
rows = []
for x in items:
    m = pat.match(x["id"])
    if not m:
        rows.append(("NOMATCH", x["id"], x.get("coverage"), x.get("description")))
        continue
    g, pol, st, num = m.groups()
    groups[g] += 1
    stats[f"{pol}_{st}"] += 1

print("\ngroups:", dict(groups))
print("\npol_stat:", dict(stats))
print("\nNOMATCH samples:")
for r in rows[:30]:
    print(" ", r[1], "cov=", r[2], "|", (r[3] or "")[:70])

# 高使用度字段 top20 (人群验证过的可挖字段)
print("\n=== top alphaCount ===")
for x in sorted(items, key=lambda v: -(v.get("alphaCount") or 0))[:20]:
    print(f"  {x['id']:32s} cov={x.get('coverage')} users={x.get('userCount')} alphas={x.get('alphaCount')} | {(x.get('description') or '')[:60]}")
