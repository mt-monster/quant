"""Alpha mining for analyst44 dataset - simplified, sequential approach."""
import sys, os, time, json
sys.stdout.reconfigure(line_buffering=True)  # Force flush
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

# Simplified field wrappers (less complex for faster computation)
def w(f):
    """Simple wrapper - just ts_backfill"""
    return f"ts_backfill({f}, 63)"

def ww(f):
    """Medium wrapper - with winsorize"""
    return f"winsorize(ts_backfill({f}, 63), std=4)"

# Curated MATRIX fields from analyst44 - focusing on best coverage
FIELDS = [
    "anl44_eps_ratio_best_eeps_cur_yr",   # EPS ratio current year
    "anl44_eps_ratio_best_eeps_nxt_yr",   # EPS ratio next year
    "anl44_bps_best_eeps_cur_yr",         # BPS current year
    "anl44_bps_best_eeps_nxt_yr",         # BPS next year
    "anl44_eps_gaap_best_eeps_cur_yr",    # GAAP EPS current year
    "anl44_eps_gaap_best_eeps_nxt_yr",    # GAAP EPS next year
    "anl44_dps_best_eeps_cur_yr",         # DPS current year
    "anl44_dps_best_eeps_nxt_yr",         # DPS next year
    "anl44_cfps_best_eeps_cur_yr",        # CFPS current year
    "anl44_cfps_best_eeps_nxt_yr",        # CFPS next year
    "anl44_epsr_best_eeps_cur_yr",        # EPSR current year
    "anl44_epsr_best_eeps_nxt_yr",        # EPSR next year
]

# Build expressions using different patterns
def build_expressions():
    exprs = []
    # For each pair of fields, try several patterns
    for i, f1 in enumerate(FIELDS):
        for j, f2 in enumerate(FIELDS):
            if j <= i:
                continue
            a, b = w(f1), w(f2)
            
            # P1: Simple spread
            exprs.append(f"rank(subtract({a}, {b}))")
            
            # P2: Spread with winsorize
            a2, b2 = ww(f1), ww(f2)
            exprs.append(f"rank(subtract({a2}, {b2}))")
            
            # P3: Momentum of spread
            exprs.append(f"rank(ts_delta(subtract({a}, {b}), 22))")
            
            # P4: Ratio
            exprs.append(f"rank(divide({a}, abs({b}) + 0.01))")
            
            # P5: Zscore spread
            exprs.append(f"zscore(subtract({a}, {b}))")
            
            # P6: Signed power on spread
            exprs.append(f"signed_power(rank(subtract({a}, {b})), 2.0)")
            
            # P7: ts_rank of spread
            exprs.append(f"rank(ts_rank(subtract({a}, {b}), 22))")
            
            # P8: Single field momentum
            if "cur_yr" in f1 and "nxt_yr" in f2:
                exprs.append(f"rank(ts_delta({a}, 22))")
                exprs.append(f"rank(ts_delta({b}, 22))")
    
    return exprs

def main():
    all_exprs = build_expressions()
    print(f"Total expressions to test: {len(all_exprs)}")
    
    results = []
    for i, expr in enumerate(all_exprs):
        print(f"\n[{i+1}/{len(all_exprs)}] {expr[:100]}...")
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
        
        # Get alpha details
        try:
            details = api.get_alpha_details(alpha_id)
            is_data = details.get("is", {})
            sharpe = is_data.get("sharpe", "N/A")
            fitness = is_data.get("fitness", "N/A")
            turnover = is_data.get("turnover", "N/A")
            print(f"  OK {alpha_id} S={sharpe} F={fitness} T={turnover} ({elapsed:.0f}s)")
            
            results.append({
                "alpha_id": alpha_id,
                "expression": expr,
                "sharpe": sharpe,
                "fitness": fitness,
                "turnover": turnover,
            })
            
            # Save results periodically
            with open("results_analyst44.json", "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"  Detail error: {e}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(results)} alphas found from {len(all_exprs)} expressions")
    for r in sorted(results, key=lambda x: float(x.get("sharpe", 0) or 0), reverse=True)[:10]:
        print(f"  {r['alpha_id']} S={r['sharpe']} F={r['fitness']} | {r['expression'][:60]}...")

if __name__ == "__main__":
    main()
