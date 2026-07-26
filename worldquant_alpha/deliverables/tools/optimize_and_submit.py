#!/usr/bin/env python3
"""对 v52b 最佳候选做参数调优变体，跑通硬闸门后直接提交。

策略：取 zqRkPVbX (S=2.33, decay4 SECTOR) 的表达式，
扫 decay/neutralization/truncation 变体 → run_backtest → 检 IS → 通过则 submit。
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

BASE = "https://api.worldquantbrain.com"
api = WqApiSimple()
s = api.session

# 基础表达式（v52b 最佳候选）
BASE_EXPR = "rank(group_zscore(ts_zscore(ts_backfill(vec_avg(aggregate_open_positions_count), 66), 63), industry))"

# 调优变体：聚焦降自相关 + 抬 margin
VARIANTS = [
    # (tag, decay, neut, trunc, universe)
    ("d3_SUB",    3, "SUBINDUSTRY", 0.01, "TOP3000"),   # 更细中性化 → 降 self_corr
    ("d5_SUB",    5, "SUBINDUSTRY", 0.01, "TOP3000"),   # +decay 降换手
    ("d4_MKT",    4, "MARKET",      0.05, "TOP3000"),   # MARKET 中性 + 大 trunc
    ("d3_IND_t5", 3, "INDUSTRY",    0.05, "TOP3000"),   # INDUSTRY + 大 trunc
    ("d6_SEC_t8", 6, "SECTOR",      0.08, "TOP3000"),   # 高 decay + 大 trunc 抬 margin
    ("d4_SUB_t8", 4, "SUBINDUSTRY", 0.08, "TOP2000"),   # SUB + TOP2000 降 self_corr
]

GATE_S, GATE_F, GATE_M_BP = 1.58, 1.0, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30

def _f(v):
    try: return float(v) if v is not None else None
    except: return None

def make_settings(decay, neut, trunc, uni):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": uni, "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc,
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
        "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
    }

def check_gates(is_):
    s = _f(is_.get("sharpe")) or 0
    f = _f(is_.get("fitness")) or 0
    tvr = _f(is_.get("turnover")) or 0
    m = _f(is_.get("margin")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_S: fails.append(f"S={s:.3f}")
    if f <= GATE_F: fails.append(f"F={f:.3f}")
    if tvr <= GATE_TVR_LO or tvr >= GATE_TVR_HI: fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_M_BP: fails.append(f"M={m_bp:.1f}bp")
    return fails, s, f, tvr, m_bp

print(f"Optimizing v52b top candidate: {BASE_EXPR[:60]}...")
print(f"Running {len(VARIANTS)} variants...\n")

results = []
for tag, decay, neut, trunc, uni in VARIANTS:
    label = f"opt_{tag}"
    settings = make_settings(decay, neut, trunc, uni)
    print(f"[{label}] decay={decay} {neut} trunc={trunc} {uni} ...", end=" ", flush=True)
    
    try:
        res = api.run_backtest(BASE_EXPR, settings=settings)
        if not res or not res.get("platform_id"):
            print("NO PID")
            results.append({"label": label, "status": "no_pid"})
            continue
        pid = res["platform_id"]
        
        # Get IS details
        det = api.get_alpha_details(pid)
        is_ = det.get("is") or {}
        fails, s_v, f_v, tvr, m_bp = check_gates(is_)
        status = "PASS_CHEAP" if not fails else "FAIL"
        print(f"pid={pid} S={s_v:.2f} F={f_v:.2f} TVR={tvr:.4f} M={m_bp:.1f}bp {status} {fails[:2]}")
        
        results.append({
            "label": label, "pid": pid, "sharpe": s_v, "fitness": f_v,
            "tvr": tvr, "margin_bp": m_bp, "status": status, "fails": fails,
            "settings": settings,
        })
        
        # If PASS_CHEAP → try submit (triggers OOS + platform checks)
        if status == "PASS_CHEAP":
            print(f"  >>> PASS_CHEAP! Attempting submit (triggers OOS)...")
            desc = (
                f"PPA alpha on USA EQUITY {uni}, delay 1, decay {decay}, {neut} neutralization. "
                f"Signal = rank of industry-neutralized z-scored backfilled aggregate open positions count. "
                f"Low turnover design via decay={decay}. IS sharpe={s_v:.2f}, fitness={f_v:.2f}. "
                f"Submitted for PPA program evaluation."
            )
            s.patch(urljoin(BASE, f"alphas/{pid}"),
                    json={"name": f"ppa_opt_{tag}"[:80], "regular": {"description": desc}, "color": "GREEN"})
            s.post(urljoin(BASE, f"alphas/{pid}/submit"))
            
            # Poll for status flip (3 min)
            for _ in range(36):
                d = api.get_alpha_details(pid)
                st = d.get("status"); dsub = d.get("dateSubmitted")
                if dsub or (st and st != "UNSUBMITTED"):
                    break
                time.sleep(5)
            
            d = api.get_alpha_details(pid)
            final_st = d.get("status")
            print(f"  >>> Submit result: {final_st} {d.get('dateSubmitted') or ''}")
            if final_st == "ACTIVE":
                print(f"  *** SUBMITTED SUCCESSFULLY! pid={pid} ***")
        
    except Exception as e:
        print(f"ERROR: {e}")
        results.append({"label": label, "status": "error", "error": str(e)})
    
    time.sleep(2)  # cooldown

# Summary
print(f"\n{'='*60}")
print(f"SUMMARY: {len(VARIANTS)} variants")
for r in results:
    if r.get("status") == "PASS_CHEAP":
        print(f"  ✅ {r['label']}: S={r['sharpe']:.2f} F={r['fitness']:.2f} M={r['margin_bp']:.1f}bp")
    elif r.get("sharpe"):
        print(f"  ❌ {r['label']}: S={r['sharpe']:.2f} {r['fails'][:2]}")
    else:
        print(f"  ⚠️ {r['label']}: {r.get('status','?')}")
