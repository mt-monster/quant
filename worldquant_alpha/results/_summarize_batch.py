import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
print("success", d.get("success"), d.get("message"))
for a in d.get("alpha_results", []):
    det = a.get("details") or {}
    if not det or "is" not in det:
        print(a.get("alpha_id"), "NO DETAILS")
        continue
    iso = det["is"]
    checks = {c["name"]: c for c in iso["checks"]}

    def gv(n):
        c = checks.get(n, {})
        return f"{c.get('result')}:{c.get('value')}/{c.get('limit')}"

    print(
        a["alpha_id"],
        f"S={iso['sharpe']} F={iso['fitness']} TVR={iso['turnover']:.3f} Ret={iso['returns']:.3f}",
        "SUB",
        gv("LOW_SUB_UNIVERSE_SHARPE"),
        "ROB",
        gv("LOW_ROBUST_UNIVERSE_SHARPE"),
        "2Y",
        gv("LOW_2Y_SHARPE"),
    )
    print(" ", det["regular"]["code"][:140])
