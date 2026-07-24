import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
items = d.get("results", [])
print("count", d.get("count"), "n", len(items))
oth = [x for x in items if (x.get("category") or {}).get("id") == "other"]
print("other n", len(oth))
for x in sorted(oth, key=lambda z: (z.get("alphaCount") or 0, z.get("userCount") or 0))[:50]:
    print(
        f"{x.get('id')}: ac={x.get('alphaCount')} uc={x.get('userCount')} "
        f"cov={x.get('coverage')} fields={x.get('fieldCount')} "
        f"mult={x.get('pyramidMultiplier')} name={x.get('name')}"
    )
