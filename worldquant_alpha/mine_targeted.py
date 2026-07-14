"""Targeted Alpha mining for analyst44 - high-potential patterns only."""
import sys, os, time, json
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from dotenv import load_dotenv
load_dotenv()
from wd_lib_wrapper import WqApiSimple

api = WqApiSimple()

SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "SUBINDUSTRY", "truncation": 0.08,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P0Y",
}

# Best coverage MATRIX fields from analyst44
FIELDS = {
    "eps_ratio_cur": "anl44_eps_ratio_best_eeps_cur_yr",
    "eps_ratio_nxt": "anl44_eps_ratio_best_eeps_nxt_yr",
    "bps_cur": "anl44_bps_best_eeps_cur_yr",
    "bps_nxt": "anl44_bps_best_eeps_nxt_yr",
    "eps_gaap_cur": "anl44_eps_gaap_best_eeps_cur_yr",
    "eps_gaap_nxt": "anl44_eps_gaap_best_eeps_nxt_yr",
    "dps_cur": "anl44_dps_best_eeps_cur_yr",
    "dps_nxt": "anl44_dps_best_eeps_nxt_yr",
    "cfps_cur": "anl44_cfps_best_eeps_cur_yr",
    "cfps_nxt": "anl44_cfps_best_eeps_nxt_yr",
    "epsr_cur": "anl44_epsr_best_eeps_cur_yr",
    "epsr_nxt": "anl44_epsr_best_eeps_nxt_yr",
}

def fb(f, days=63):
    return f"ts_backfill({f}, {days})"

def w(f, days=63):
    return f"winsorize(ts_backfill({f}, {days}), std=4)"

# Build targeted expressions based on economic logic
def build_targeted():
    exprs = []
    
    # === GROUP 1: Single-field momentum (revision momentum) ===
    # Analysts revising estimates upward -> positive returns
    for name, f in FIELDS.items():
        if "cur_yr" in name:
            # Short-term revision (5 days)
            exprs.append(f"rank(ts_delta({fb(f)}, 5))")
            # Medium-term revision (22 days)
            exprs.append(f"rank(ts_delta({fb(f)}, 22))")
            # Long-term revision (66 days)
            exprs.append(f"rank(ts_delta({fb(f)}, 66))")
            # Z-score of revision
            exprs.append(f"rank(ts_zscore({fb(f)}, 22))")
            # Rank over time
            exprs.append(f"rank(ts_rank({fb(f)}, 22))")
    
    # === GROUP 2: Term structure (cur vs nxt year) ===
    for prefix in ["eps_ratio", "bps", "eps_gaap", "dps", "cfps", "epsr"]:
        cur = FIELDS[f"{prefix}_cur"]
        nxt = FIELDS[f"{prefix}_nxt"]
        a, b = fb(cur), fb(nxt)
        
        # Simple spread
        exprs.append(f"rank(subtract({a}, {b}))")
        # Normalized spread (percentage)
        exprs.append(f"rank(divide(subtract({a}, {b}), abs({b}) + 0.01))")
        # Reversed spread (nxt - cur)
        exprs.append(f"rank(subtract({b}, {a}))")
        # Spread with signed_power
        exprs.append(f"signed_power(rank(subtract({a}, {b})), 2.0)")
        # Spread with zscore
        exprs.append(f"zscore(subtract({a}, {b}))")
        # Spread momentum
        exprs.append(f"rank(ts_delta(subtract({a}, {b}), 22))")
    
    # === GROUP 3: Cross-field ratios ===
    # EPS/BPS = P/E inverse
    exprs.append(f"rank(divide({fb(FIELDS['eps_ratio_cur'])}, abs({fb(FIELDS['bps_cur'])}) + 0.01))")
    # GAAP/EPS ratio = earnings quality
    exprs.append(f"rank(divide({fb(FIELDS['eps_gaap_cur'])}, abs({fb(FIELDS['eps_ratio_cur'])}) + 0.01))")
    # CFPS/EPS = cash flow quality
    exprs.append(f"rank(divide({fb(FIELDS['cfps_cur'])}, abs({fb(FIELDS['eps_ratio_cur'])}) + 0.01))")
    # DPS/EPS = payout ratio
    exprs.append(f"rank(divide({fb(FIELDS['dps_cur'])}, abs({fb(FIELDS['eps_ratio_cur'])}) + 0.01))")
    
    # === GROUP 4: Multi-timeframe revision ===
    for prefix in ["eps_ratio", "bps"]:
        f = FIELDS[f"{prefix}_cur"]
        a = fb(f)
        # Short vs long revision
        exprs.append(f"rank(subtract(ts_delta({a}, 5), ts_delta({a}, 22)))")
        exprs.append(f"rank(subtract(ts_delta({a}, 5), ts_delta({a}, 66)))")
        # Acceleration (change in revision)
        exprs.append(f"rank(ts_delta(ts_delta({a}, 5), 5))")
        exprs.append(f"rank(ts_delta(ts_delta({a}, 22), 22))")
    
    # === GROUP 5: Correlation and regression ===
    a = fb(FIELDS['eps_ratio_cur'])
    b = fb(FIELDS['bps_cur'])
    exprs.append(f"rank(ts_corr({a}, {b}, 22))")
    exprs.append(f"rank(ts_corr({a}, {b}, 60))")
    exprs.append(f"rank(ts_regression({a}, {b}, 22, 0, 2))")
    
    # === GROUP 6: Winsorized versions of best patterns ===
    for prefix in ["eps_ratio", "bps"]:
        cur = FIELDS[f"{prefix}_cur"]
        nxt = FIELDS[f"{prefix}_nxt"]
        a, b = w(cur), w(nxt)
        exprs.append(f"rank(subtract({a}, {b}))")
        exprs.append(f"rank(divide(subtract({a}, {b}), abs({b}) + 0.01))")
        exprs.append(f"rank(ts_delta(subtract({a}, {b}), 22))")
    
    return exprs

def main():
    all_exprs = build_targeted()
    # Remove duplicates
    all_exprs = list(dict.fromkeys(all_exprs))
    print(f"Total targeted expressions: {len(all_exprs)}")
    
    results = []
    for i, expr in enumerate(all_exprs):
        print(f"\n[{i+1}/{len(all_exprs)}] {expr[:120]}...")
        t0 = time.time()
        try:
            success, alpha_id = api.submit_simulation(expr, SETTINGS.copy(), max_wait_time=900)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        elapsed = time.time() - t0
        
        if not success or not alpha_id:
            print(f"  FAIL ({elapsed:.0f}s)")
            continue
        
        try:
            details = api.get_alpha_details(alpha_id)
            is_data = details.get("is", {})
            sharpe = float(is_data.get("sharpe", 0) or 0)
            fitness = float(is_data.get("fitness", 0) or 0)
            turnover = is_data.get("turnover", "N/A")
            print(f"  OK {alpha_id} S={sharpe:.3f} F={fitness:.3f} T={turnover} ({elapsed:.0f}s)")
            
            results.append({
                "alpha_id": alpha_id,
                "expression": expr,
                "sharpe": sharpe,
                "fitness": fitness,
                "turnover": turnover,
                "elapsed": elapsed,
            })
            
            with open("results_targeted.json", "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"  Detail error: {e}")
    
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(results)} alphas from {len(all_exprs)} expressions")
    print(f"{'='*60}")
    for r in sorted(results, key=lambda x: abs(x.get("sharpe", 0)), reverse=True)[:15]:
        print(f"  {r['alpha_id']} S={r['sharpe']:.3f} F={r['fitness']:.3f} T={r['turnover']}")
        print(f"    {r['expression'][:100]}...")

if __name__ == "__main__":
    main()
