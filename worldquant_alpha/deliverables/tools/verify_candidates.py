#!/usr/bin/env python3
"""批量验证 47 候选 alpha：/check 取 IS 硬闸门 + /details 取状态 → 重新归类。
限速：每批 5 个, 批间 45s, 单次间隔 3s。先查后录，不提交。"""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin
import glob

BASE = "https://api.worldquantbrain.com"
api = WqApiSimple()
s = api.session

# 1) 加载候选
cands = []
for f in sorted(glob.glob("results/*_checkpoint.json")):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except:
        continue
    task = os.path.basename(f).replace("_checkpoint.json", "")
    items = d if isinstance(d, list) else d.get("results", [])
    for r in items:
        st = str(r.get("status", ""))
        if st in ("PASS_CHEAP", "CHECK_PENDING", "PASS"):
            pid = r.get("pid")
            if not pid:
                continue
            cands.append({
                "pid": pid, "task": task, "label": r.get("label", ""),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
                "tvr": r.get("tvr"), "margin": r.get("margin"),
                "ret": r.get("returns"), "expr": r.get("expr", "")[:140],
                "status": st
            })
cands.sort(key=lambda x: -(x["sharpe"] or 0))
print(f"Loaded {len(cands)} candidates.\n")

BATCH = 5
COOLDOWN = 45
INNER_SLEEP = 3

results = {
    "active": [],        # already ACTIVE
    "check_fail": [],    # /check returned FAIL on IS gates
    "check_pass": [],    # /check passed IS, but no prod_corr yet
    "check_pending": [], # /check returned null (platform still verifying)
    "no_checks": [],     # /check returned empty (never ran OOS)
    "error": []           # network/API error
}

for i, c in enumerate(cands):
    if i > 0 and i % BATCH == 0:
        print(f"  [cooldown {COOLDOWN}s after batch {i//BATCH}]")
        time.sleep(COOLDOWN)

    pid = c["pid"]
    print(f"[{i+1}/{len(cands)}] {pid} (S={c['sharpe']:.2f}, {c['status']})", end=" ")

    # Step A: get alpha details (status, dateSubmitted)
    try:
        det = api.get_alpha_details(pid)
        cur_st = det.get("status", "")
        cur_sub = det.get("dateSubmitted")
        prod_corr = det.get("prodCorr")
        self_corr = det.get("selfCorr")
        robust = det.get("robust")
        risk_neut = det.get("riskNeut")
    except Exception as e:
        print(f"→ ERROR (details): {e}")
        results["error"].append({**c, "reason": str(e)})
        time.sleep(INNER_SLEEP)
        continue

    # Already submitted or active?
    if cur_sub and cur_st == "ACTIVE":
        print(f"→ ACTIVE (submitted {cur_sub})")
        results["active"].append({**c, "status": "ACTIVE", "dateSubmitted": cur_sub,
                                   "prodCorr": prod_corr, "selfCorr": self_corr})
        time.sleep(INNER_SLEEP)
        continue
    if cur_st and cur_st not in ("UNSUBMITTED", ""):
        print(f"→ {cur_st} (not ACTIVE but non-UNSUBMITTED: {cur_st})")
        results["active"].append({**c, "status": cur_st, "note": "non-ACTIVE non-UNSUBMITTED"})
        time.sleep(INNER_SLEEP)
        continue

    # Step B: /check for IS gates
    try:
        chk = s.get(urljoin(BASE, f"alphas/{pid}/check"), timeout=60)
        if not chk.ok:
            print(f"→ HTTP {chk.status_code}")
            results["error"].append({**c, "reason": f"check {chk.status_code}"})
            time.sleep(INNER_SLEEP)
            continue
        if not chk.text.strip():
            print(f"→ EMPTY (no check data — needs OOS)")
            results["no_checks"].append({**c, "prodCorr": prod_corr, "selfCorr": self_corr})
            time.sleep(INNER_SLEEP)
            continue
        cj = chk.json()
        checks = (cj.get("is") or {}).get("checks") or []
    except Exception as e:
        print(f"→ ERROR (check): {e}")
        results["error"].append({**c, "reason": str(e)})
        time.sleep(INNER_SLEEP)
        continue

    if not checks:
        print(f"→ NO CHECKS (needs OOS/prod sim)")
        results["no_checks"].append({**c, "prodCorr": prod_corr, "selfCorr": self_corr})
        time.sleep(INNER_SLEEP)
        continue

    fails = [x for x in checks if x.get("result") == "FAIL"]
    passes = [x for x in checks if x.get("result") == "PASS"]

    if fails:
        fail_names = [x.get("name","?") for x in fails]
        print(f"→ FAIL ({len(fails)} gates): {', '.join(fail_names[:3])}")
        results["check_fail"].append({**c, "fail_gates": fail_names,
                                       "prodCorr": prod_corr, "selfCorr": self_corr})
    else:
        has_prod = prod_corr is not None
        print(f"→ IS CHECK PASS ({len(passes)} gates){' + prod_corr='+str(round(prod_corr,4)) if has_prod else ' (no prod_corr yet)'}")
        results["check_pass"].append({**c, "pass_gates": len(passes),
                                       "prodCorr": prod_corr, "selfCorr": self_corr})

    time.sleep(INNER_SLEEP)

# 2) Write results
out_path = "deliverables/reports/candidate_verification_batch_1.json"
os.makedirs(os.path.dirname(out_path), exist_ok=True)
json.dump(results, open(out_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# 3) Summary
print(f"\n{'='*60}")
print(f"验证完成 {len(cands)} 个候选:")
print(f"  ✅ 已 ACTIVE:            {len(results['active'])}")
print(f"  ✅ /check IS PASS:      {len(results['check_pass'])} (需 prod_corr + OOS 才能提交)")
print(f"  ❌ /check IS GATE FAIL: {len(results['check_fail'])}")
print(f"  ⚠️  /check 空(未跑OOS):  {len(results['no_checks'])}")
print(f"  ⏳ /check null(产验中): {len(results['check_pending'])}")
print(f"  ❌ 网络/API 错误:        {len(results['error'])}")
print(f"\n结果已写入: {out_path}")
print(f"\nACTIVE 列表:")
for a in results["active"]:
    print(f"  {a['pid']}  S={a['sharpe']:.2f}  {a.get('status','')}  {a.get('dateSubmitted','')}")
