#!/usr/bin/env python3
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
results = data.get("alpha_results") or []
print(f"batch n={len(results)} success={data.get('success')}")
rows = []
for i, a in enumerate(results):
    d = a.get("details") or a
    aid = d.get("id") or a.get("alpha_id")
    reg = d.get("regular") or {}
    expr = reg.get("code") if isinstance(reg, dict) else str(reg)
    is_ = d.get("is") or {}
    s = is_.get("sharpe")
    f = is_.get("fitness")
    t = is_.get("turnover")
    m = is_.get("margin")
    r = is_.get("returns")
    mbp = (m * 10000) if m is not None else None
    ops = reg.get("operatorCount")
    err = a.get("error")
    gate = (
        s is not None
        and s > 1.58
        and f is not None
        and f > 1.0
        and t is not None
        and 0.05 < t < 0.30
        and mbp is not None
        and mbp > 10
    )
    rows.append((s or -999, i, aid, s, f, t, mbp, r, ops, gate, expr, err))

rows.sort(reverse=True)
for s, i, aid, s2, f, t, mbp, r, ops, gate, expr, err in rows:
    flag = "PASS_CHEAP" if gate else ""
    print(
        f"[{i}] {aid} S={s2} F={f} TVR={t} m={mbp}bp ret={r} ops={ops} {flag}"
    )
    print(f"     {expr}")
    if err:
        print(f"     ERR {err}")
