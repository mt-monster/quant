import sys, json, time
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple

api = WqApiSimple()
cands = [
    ("gz_t2_b66z189_TOP3000_d3_SEC_t12", "le30awQe", "W189 d3 SEC t12"),
    ("gz_t2_b66z189_TOP3000_d2_SEC_t1",  "j2rgVd0E", "W189 d2 SEC t1"),
    ("gz_t2_b66z189_TOP3000_d2_SEC_t12", "zqRWAJmX", "W189 d2 SEC t12"),
    ("gz_t2_b66z189_TOP3000_d3_IND_t1",  "QP9QNw8G", "W189 d3 IND t1"),
    ("gz_t2_b66z189_TOP3000_d3_IND_t12", "RR1rlGge", "W189 d3 IND t12"),
    ("gz_t2_b66z252_TOP3000_d2_SEC_t1",  "KPELQn7l", "W252 d2 SEC t1"),
    ("gz_t2_b66z252_TOP3000_d2_SEC_t12", "e7xrvnzJ", "W252 d2 SEC t12"),
    ("gz_t2_b66z189_TOP3000_d2_IND_t1",  "N1RO8rLL", "W189 d2 IND t1"),
    ("gz_t2_b66z189_TOP3000_d2_IND_t12", "np8Wr2ml", "W189 d2 IND t12"),
]
# 对照已提交的 #5
print("对照(已提交): gz_t2_b66z189_TOP3000_d3_SEC_t1 = YPgAa3WR (W189 d3 SEC t1) -> 通过 SELF_CORRELATION")
print("="*70)
for label, pid, desc in cands:
    chk = api.get_alpha_check(pid)
    items = chk.get("is", {}).get("checks", []) if isinstance(chk, dict) else chk
    if isinstance(items, list):
        for c in items:
            if c.get("name") == "SELF_CORRELATION":
                print(f"[{desc}] pid={pid}")
                print(f"   SELF_CORRELATION: result={c.get('result')} value={c.get('value')} "
                      f"bound={c.get('bound')} threshold={c.get('threshold')}")
                # 也看 sub_universe
            if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE":
                print(f"   LOW_SUB_UNIVERSE_SHARPE: result={c.get('result')} value={c.get('value')}")
    time.sleep(0.5)
