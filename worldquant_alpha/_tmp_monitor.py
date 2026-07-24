import json, os, csv, time

BASE = r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha"
RES = os.path.join(BASE, "results")

def summarize_v43():
    p = os.path.join(RES, "v43_event_rel_checkpoint.json")
    if not os.path.exists(p):
        return "v43 checkpoint missing"
    d = json.load(open(p, encoding="utf-8"))
    res = d.get("results") or []
    found = d.get("found_alphas") or []
    n = len(res)
    with_pid = [r for r in res if r.get("pid")]
    errors = [r for r in res if r.get("status") == "error"]
    pass_cheap = [r for r in res if r.get("status") == "PASS_CHEAP"]
    sh = [float(r["sharpe"]) for r in res if r.get("sharpe") is not None]
    best = max(sh) if sh else None
    best_label = None
    if sh:
        bi = max(range(len(sh)), key=lambda i: sh[i])
        best_label = res[bi].get("label")
    # candidates that passed cheap AND no platform fail
    cands = []
    for r in pass_cheap:
        fails = r.get("fails") or []
        if not any(f.startswith("PF:") for f in fails):
            cands.append(r.get("label"))
    return {
        "total_variants": 200,
        "results_recorded": n,
        "with_pid": len(with_pid),
        "errors": len(errors),
        "pass_cheap": len(pass_cheap),
        "candidates_no_pf_fail": cands,
        "best_sharpe": round(best, 4) if best is not None else None,
        "best_label": best_label,
        "found_alphas": len(found),
    }

def summarize_tabbit_csv():
    p = r"d:\BaiduNetdiskDownload\WQ第二三四节课代码\worldquant\tabbit_option9_results.csv"
    if not os.path.exists(p):
        return "tabbit csv missing"
    rows = []
    with open(p, encoding="utf-8", errors="replace") as f:
        rd = csv.DictReader(f)
        for row in rd:
            rows.append(row)
    n = len(rows)
    # status counts
    from collections import Counter
    st = Counter(r.get("status", "") for r in rows)
    # alpha ids present
    aids = [r.get("alpha_id") for r in rows if r.get("alpha_id")]
    # last finished_at
    fins = [r.get("finished_at") for r in rows if r.get("finished_at")]
    return {
        "csv_rows": n,
        "status_counts": dict(st),
        "alpha_ids": len(aids),
        "last_finished_at": fins[-1] if fins else None,
        "csv_path": p,
    }

if __name__ == "__main__":
    print("=== V43 ===")
    print(json.dumps(summarize_v43(), ensure_ascii=False, indent=2))
    print("=== TABBIT CSV ===")
    print(json.dumps(summarize_tabbit_csv(), ensure_ascii=False, indent=2))
