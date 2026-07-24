#!/usr/bin/env python3
import json
path = r"C:\Users\MENGTAO\.cursor\projects\c-Users-MENGTAO-Desktop-E3-quant\agent-tools\60afcd20-e65b-443f-ad72-25614593a29d.txt"
d = json.load(open(path, encoding="utf-8"))
items = d.get("results") or []
for cat in ["model", "analyst", "sentiment", "risk", "option", "macro", "insiders", "shortinterest"]:
    xs = [x for x in items if (x.get("category") or {}).get("id") == cat]
    xs = sorted(xs, key=lambda x: (-float(x.get("pyramidMultiplier") or 0), int(x.get("alphaCount") or 0)))
    print("===", cat, "n=", len(xs), "===")
    for x in xs[:8]:
        print(
            f"  {x['id']:28s} mult={x.get('pyramidMultiplier')} "
            f"ac={x.get('alphaCount'):5d} fc={x.get('fieldCount'):4d} cov={x.get('coverage')}"
        )
