"""表达式语法校验（耐心版，workflow Stage 2.5 Smoke Test）。

WQ 的 429 限流检查排在语法校验之前，故 429 无法区分语法对错。
本脚本对每条新算子表达式做：POST 遇 429 短退避重试，
直到拿到 201（语法合法，已接受排队）或 400（语法/签名错，立即返回）。
201 会创建一个真实模拟（验证孤儿，随槽位排空），400 不占槽。
仅用于确认 build_exprs_for_pair 里 P3/P4/P5/P6/P7 等新手法签名可用。
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.abspath(".env"))
import requests
from wd_lib_wrapper import API_BASE
from mine_usa_ppa_multi import SETTINGS

U = os.environ["WQ_USERNAME"]; P = os.environ["WQ_PASSWORD"]
s = requests.Session(); s.auth = (U, P)
r0 = s.post(f"{API_BASE}/authentication", timeout=60)
print("AUTH", r0.status_code, flush=True)

bf = 66
a = f"ts_backfill(inst20_ra_short_volume, {bf})"
b = f"ts_backfill(inst20_sq_short_volume, {bf})"

tests = {
    "T1_subtract_filter":      f"rank(ts_zscore(subtract({a}, {b}, filter=true), {bf}))",
    "T2_group_zscore_corr":    f"group_zscore(ts_corr({a}, {b}, 126), sector)",
    "T3_corr_delta_first":     f"rank(ts_corr(ts_delta({a}, 5), ts_delta({b}, 5), {bf}))",
    "T4_trade_when":          f"trade_when(ts_delta({b}, 22) > 0, rank(subtract({a}, {b}, filter=true)))",
    "T5_if_else":             f"if_else(ts_delta({b}, 22) > 0, rank(divide({a}, abs({b}) + 0.01)), 0)",
    "T6_days_from_last_change":f"rank(subtract(days_from_last_change({a}), days_from_last_change({b})))",
    "T7_ts_quantile":         f"rank(ts_quantile(subtract({a}, {b}, filter=true), {bf}, 2))",
    "T8_group_rank_subind":    f"group_rank(ts_zscore(divide({a}, {b}), {bf}), subindustry)",
    "T9_ts_regression":       f"group_rank(ts_regression({a}, {b}, {bf}), industry)",
}

def validate(name, expr):
    data = {"type": "REGULAR", "settings": SETTINGS, "regular": expr}
    attempt = 0
    while attempt < 30:
        try:
            r = s.post(f"{API_BASE}/simulations", json=data, timeout=60)
        except Exception as e:
            print(f"{name}: EXC {e}", flush=True); time.sleep(20); attempt += 1; continue
        if r.status_code in (200, 201):
            print(f"{name}: 201 VALID (accepted)", flush=True); return True
        if r.status_code == 400:
            print(f"{name}: 400 INVALID | {r.text[:220]}", flush=True); return False
        if r.status_code == 429:
            wait = min(15 + attempt * 5, 60)
            time.sleep(wait); attempt += 1; continue
        # 其它 4xx/5xx
        print(f"{name}: {r.status_code} | {r.text[:200]}", flush=True); return False
    print(f"{name}: GAVE_UP_after_retries", flush=True); return False

for name, expr in tests.items():
    validate(name, expr)
    time.sleep(1)
print("VALIDATE_DONE", flush=True)
