#!/usr/bin/env python3
"""提交 7 个候选 alpha（j2rrpVzO + 6 EMPTY），轮询状态，落盘验证结果到 _platform_verified.json。
限速：每个提交间隔 20s。"""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin
import glob

BASE = "https://api.worldquantbrain.com"
api = WqApiSimple()
s = api.session

# ===== target PIDs to submit =====
TARGETS = [
    # (pid, description_signal_name, task)
    ("j2rrpVzO", "hiring_trends_ILLIQUID", "v52_tri_hiring_trends"),    # IS CHECK PASS, S=2.19
    ("xAdjvnxN", "hiring_margin_TOP3000", "v52b_hiring_margin"),         # EMPTY /check
    ("qM6jwAlK", "hiring_margin_TOP3000", "v52b_hiring_margin"),         # EMPTY /check
    ("YPgvjZrJ", "hiring_trends_ILLIQUID", "v52_tri_hiring_trends"),     # EMPTY /check
    ("e7xQoWZM", "web_lift_TOP3000", "rescue_r3_web_lift"),              # EMPTY /check
    ("e7xrvnzJ", "sub_micro_TOP3000", "v39b_sub_micro"),                 # EMPTY /check
    ("RR11Gzbd", "hiring_trends_TOP3000", "v52_tri_hiring_trends"),      # EMPTY /check
]

results = {}

for i, (pid, sig_name, task) in enumerate(TARGETS):
    if i > 0:
        print(f"  [cooldown 20s before next submit]")
        time.sleep(20)

    print(f"\n[{i+1}/7] {pid} ({task})", end=" ")

    # Load checkpoint data for expression
    expr = ""
    ckpt_sharpe = None
    for cp in glob.glob("results/*_checkpoint.json"):
        try:
            d = json.load(open(cp, encoding="utf-8"))
        except:
            continue
        items = d if isinstance(d, list) else d.get("results", [])
        for r in items:
            if r.get("pid") == pid:
                expr = r.get("expr", "")[:150]
                ckpt_sharpe = r.get("sharpe")
                break
        if expr:
            break

    # Step 1: Check current status
    try:
        det = api.get_alpha_details(pid)
        cur_st = det.get("status", "")
        cur_sub = det.get("dateSubmitted")
        print(f"[status={cur_st}]", end=" ")
    except Exception as e:
        print(f"→ ERROR (details): {e}")
        results[pid] = {"status": "ERROR", "error": str(e)}
        continue

    # Already active?
    if cur_sub and cur_st == "ACTIVE":
        print("→ ALREADY ACTIVE, skip")
        results[pid] = {"status": "ACTIVE", "dateSubmitted": cur_sub, "note": "already active"}
        continue

    # Step 2: Set description
    desc = (
        f"PPA alpha on USA EQUITY. "
        f"Signal uses industry-neutralized, z-scored feature with decay-based weight. "
        f"IS sharpe={ckpt_sharpe or '?'}. "
        f"Submitted for PPA (Power Pool Alpha) program evaluation."
    )
    try:
        r_desc = s.patch(
            urljoin(BASE, f"alphas/{pid}"),
            json={"name": f"ppa_{sig_name}"[:80], "regular": {"description": desc}, "color": "GREEN"},
            timeout=30,
        )
        if r_desc.status_code >= 400:
            print(f"→ description PATCH {r_desc.status_code}")
    except Exception as e:
        print(f"→ WARN desc: {e}")

    # Step 3: Submit
    try:
        r_sub = s.post(urljoin(BASE, f"alphas/{pid}/submit"), timeout=60)
        print(f"[submit {r_sub.status_code}]", end=" ")
    except Exception as e:
        print(f"→ SUBMIT ERROR: {e}")
        results[pid] = {"status": "SUBMIT_ERROR", "error": str(e)}
        continue

    # Step 4: Poll status
    final_status = "UNKNOWN"
    for poll_i in range(24):  # max 2 min polling
        time.sleep(5)
        try:
            d = api.get_alpha_details(pid)
            st = d.get("status", "?")
            ds = d.get("dateSubmitted")
            if poll_i == 0:
                print(f"→ polling...", end=" ")
            if ds or (st and st not in ("UNSUBMITTED", "SUBMITTING", "")):
                final_status = st
                print(f"[{st}]", end=" ")
                results[pid] = {
                    "status": st,
                    "dateSubmitted": ds,
                    "prodCorr": d.get("prodCorr"),
                    "selfCorr": d.get("selfCorr"),
                    "sharpe": ckpt_sharpe,
                }
                break
        except:
            continue
    else:
        print("→ TIMEOUT (still pending)")
        results[pid] = {"status": "POLL_TIMEOUT", "note": "still pending after 2 min"}

    print(f"→ DONE ({results[pid].get('status','?')})")

# Save results
out = "results/_platform_verified.json"
json.dump(results, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

print(f"\n{'='*60}")
print("提交结果汇总:")
for pid, r in results.items():
    st = r.get("status", "?")
    ds = r.get("dateSubmitted", "")
    pc = r.get("prodCorr")
    sc = r.get("selfCorr")
    extra = f" prod_corr={pc}" if pc is not None else ""
    extra += f" self_corr={sc}" if sc is not None else ""
    extra += f" submitted={ds}" if ds else ""
    print(f"  {pid}: {st}{extra}")
print(f"\n结果已写入: {out}")
