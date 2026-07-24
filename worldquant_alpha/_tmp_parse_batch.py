import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
print("success", d.get("success"), d.get("message"))
rows = []
for a in d.get("alpha_results", []):
    det = a.get("details") or {}
    if not det:
        print("ERR", str(a.get("error"))[:100])
        continue
    i = det.get("is") or {}
    ch = {c["name"]: c for c in i.get("checks", [])}
    rows.append((
        i.get("sharpe") or -999,
        a.get("alpha_id"),
        i.get("fitness"),
        ch.get("LOW_2Y_SHARPE", {}).get("value"),
        ch.get("LOW_2Y_SHARPE", {}).get("result"),
        i.get("turnover"),
        i.get("returns"),
        det.get("regular", {}).get("code", ""),
        det.get("settings", {}).get("neutralization"),
        det.get("settings", {}).get("decay"),
    ))
rows.sort(reverse=True)
for s, aid, f, y2, y2r, to, r, code, neut, decay in rows:
    print(f"{aid} S={s} F={f} 2Y={y2}({y2r}) TO={to} R={r} neut={neut} d={decay}")
    print(" ", code[:110])
