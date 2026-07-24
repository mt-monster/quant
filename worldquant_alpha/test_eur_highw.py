#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""顺序验证高 returns 权重变体能否拉起 IS_LADDER（单并发，不抢主进程 slot）"""
import sys, os, json, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))
from wd_lib_wrapper import WqApiSimple

_PA = "cfg2_top1200_residual_return"
_PB = "top2500_equity_residualized_return"
def _sm(f):
    return f"ts_mean(ts_backfill({f}, 66), 22)"
spread = f"subtract({_sm(_PA)}, {_sm(_PB)}, filter=true)"
fund189 = f"rank(ts_zscore({spread}, 189))"
RET42 = "scale(-rank(ts_zscore(returns, 42)))"
RET21 = "scale(-rank(ts_zscore(returns, 21)))"

VARIANTS = [
    ("hw_z42_w0.5_d5",  f"scale({fund189}) + {RET42} * 0.5",  5),
    ("hw_z42_w0.7_d5",  f"scale({fund189}) + {RET42} * 0.7",  5),
    ("hw_z42_w1.0_d5",  f"scale({fund189}) + {RET42} * 1.0",  5),
    ("hw_z42_w0.7_d8",  f"scale({fund189}) + {RET42} * 0.7",  8),
    ("hw_z21_w0.5_d5",  f"scale({fund189}) + {RET21} * 0.5",  5),
    ("hw_z21_w0.7_d5",  f"scale({fund189}) + {RET21} * 0.7",  5),
]

SETTINGS = dict(
    instrumentType="EQUITY", region="EUR", universe="TOPCS1600",
    delay=1, decay=6, neutralization="SUBINDUSTRY", truncation=0.05,
    pasteurization="ON", unitHandling="VERIFY", nanHandling="ON",
    language="FASTEXPR", visualization=False, maxTrade="OFF",
)

api = WqApiSimple()
out = []
for label, expr, decay in VARIANTS:
    st = dict(SETTINGS); st["decay"] = decay
    try:
        res = api.run_backtest(expr, st)
    except Exception as e:
        print(f"[{label}] 失败: {e}"); continue
    pid = (res or {}).get("platform_id")
    if not pid:
        print(f"[{label}] 无 platform_id"); continue
    m = res.get("metrics") or {}
    ch = api.get_alpha_check(pid)
    checks = (ch.get("is") or {}).get("checks") or []
    def g(name):
        c = next((c for c in checks if c.get("name") == name), {})
        return c.get("value"), c.get("limit"), c.get("result")
    lad = g("IS_LADDER_SHARPE"); sub = g("LOW_SUB_UNIVERSE_SHARPE")
    row = dict(label=label, pid=pid,
               S=m.get("sharpe"), F=m.get("fitness"),
               TVR=m.get("turnover"), M_bp=(m.get("margin") or 0)*10000,
               LAD=lad, SUB=sub)
    out.append(row)
    print(f"[{label}] pid={pid} S={m.get('sharpe')} F={m.get('fitness')} "
          f"TVR={m.get('turnover')} M={(m.get('margin') or 0)*10000:.1f}bp "
          f"LAD={lad} SUB={sub}", flush=True)

with open(os.path.join(_HERE, "results", "eur_highw_probe.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("done")
