import sys, json, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

api = WqApiSimple()
s = api.session
BASE = "https://api.worldquantbrain.com"

cands = [
    ("gz_t2_b66z189_TOP3000_d3_SEC_t12", "le30awQe"),
    ("gz_t2_b66z189_TOP3000_d2_SEC_t1",  "j2rgVd0E"),
    ("gz_t2_b66z189_TOP3000_d2_SEC_t12", "zqRWAJmX"),
    ("gz_t2_b66z189_TOP3000_d3_IND_t1",  "QP9QNw8G"),
    ("gz_t2_b66z189_TOP3000_d3_IND_t12", "RR1rlGge"),
    ("gz_t2_b66z252_TOP3000_d2_SEC_t1",  "KPELQn7l"),
    ("gz_t2_b66z252_TOP3000_d2_SEC_t12", "e7xrvnzJ"),
    ("gz_t2_b66z189_TOP3000_d2_IND_t1",  "N1RO8rLL"),
    ("gz_t2_b66z189_TOP3000_d2_IND_t12", "np8Wr2ml"),
]

print("="*70)
print(">> 提交配额检查")
for ep in ["alphas/submission-limit", "users/self/submission-limit", "submission-limit"]:
    try:
        r = s.get(urljoin(BASE, ep), timeout=20)
        print(f"   GET {ep} -> {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"   GET {ep} -> EXC {e}")

print("="*70)
print(">> 逐个平台 IS 检查（与已提交的 #5 同家族，重点看是否有硬 FAIL）")
for label, pid in cands:
    d = api.get_alpha_details(pid)
    st = d.get("status")
    chk = api.get_alpha_check(pid)
    fails, warns, passes = [], [], []
    if chk:
        items = chk.get("is", {}).get("checks", []) if isinstance(chk, dict) else chk
        if isinstance(items, list):
            for c in items:
                res = c.get("result")
                nm = c.get("name")
                if res == "FAIL": fails.append(nm)
                elif res == "WARNING": warns.append(nm)
                elif res == "PASS": passes.append(nm)
    ok = (st == "UNSUBMITTED") and (len(fails) == 0)
    print(f"\n[{label}] pid={pid} status={st}")
    print(f"   IS: PASS={len(passes)} WARN={len(warns)} FAIL={len(fails)}")
    if fails:
        print(f"   FAIL gates: {fails}")
    if warns:
        print(f"   WARN gates: {warns}")
    print(f"   >> 可提交(无硬FAIL且UNSUBMITTED): {ok}")
    time.sleep(1)
