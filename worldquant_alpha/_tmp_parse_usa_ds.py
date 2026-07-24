#!/usr/bin/env python3
"""Parse USA datasets for unlit pyramid candidates."""
import json

path = r"C:\Users\MENGTAO\.cursor\projects\c-Users-MENGTAO-Desktop-E3-quant\agent-tools\60afcd20-e65b-443f-ad72-25614593a29d.txt"
with open(path, "r", encoding="utf-8") as f:
    raw = f.read()
data = json.loads(raw)
if isinstance(data, dict):
    if "result" in data:
        data = data["result"]
    if isinstance(data, dict):
        items = data.get("results") or data.get("datasets") or data.get("data") or []
        if not items and "count" in data:
            print("keys", list(data.keys()))
    else:
        items = data
else:
    items = data

print("n_items", len(items))
if not items:
    raise SystemExit(1)
print("sample keys", list(items[0].keys()))


def pm(x):
    return float(x.get("pyramidMultiplier") or 0)


def ac(x):
    return int(x.get("alphaCount") or 0)


def cat(x):
    c = x.get("category")
    if isinstance(c, dict):
        return c.get("id") or c.get("name")
    return str(c)


ranked = sorted(items, key=lambda x: (-pm(x), ac(x)))
print("\n=== Top by pyramidMultiplier ===")
for x in ranked[:50]:
    print(
        f"{x.get('id'):32s} cat={cat(x):16s} mult={pm(x):.2f} "
        f"alphaCount={ac(x):7d} fields={x.get('fieldCount')} "
        f"cov={x.get('coverage')}"
    )

# Unlit heuristic: multiplier >= 1.5 OR (multiplier > 1.0 and alphaCount < 500)
print("\n=== Unlit-ish (mult>=1.4, alphaCount<2000, MATRIX-friendly) ===")
cands = [
    x
    for x in items
    if pm(x) >= 1.4 and ac(x) < 5000
]
cands = sorted(cands, key=lambda x: (-pm(x), ac(x)))
for x in cands[:40]:
    print(
        f"{x.get('id'):32s} cat={cat(x):16s} mult={pm(x):.2f} "
        f"alphaCount={ac(x):7d} fields={x.get('fieldCount')} name={x.get('name')}"
    )
