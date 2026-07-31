# -*- coding: utf-8 -*-
"""分析 v53 checkpoint: 找接近全过门槛的变体及其失败原因分布"""
import json, os

CKPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "v53b_glb_intraday_checkpoint.json")
with open(CKPT, "r", encoding="utf-8") as f:
    ck = json.load(f)

print("TYPE:", type(ck).__name__)
if isinstance(ck, dict):
    print("TOP KEYS:", list(ck.keys())[:15])
    for k in list(ck.keys())[:3]:
        v = ck[k]
        print(f"  {k} -> {type(v).__name__}", (list(v.keys())[:8] if isinstance(v, dict) else (v[:2] if isinstance(v, list) else v)))

done = ck["results"]
rows = []
for rec in done:
    if not isinstance(rec, dict):
        continue
    s = rec.get("sharpe"); fv = rec.get("fitness"); tvr = rec.get("tvr"); m = rec.get("margin_bp")
    if s is None:
        continue
    rows.append((rec.get("label"), s, fv, tvr, m, rec.get("fails", []), rec.get("style"), rec.get("expr"), rec.get("settings", {})))

# 1) IS 四门槛全过的变体（不管平台检查）
print("=== IS 门槛全过 (S>1.58 F>1 10bp 5-30%TVR) ===")
full = [r for r in rows if r[1] and r[1] > 1.58 and r[2] and r[2] > 1.0
        and r[3] and 0.05 < r[3] < 0.30 and r[4] and r[4] > 10.0]
for r in sorted(full, key=lambda x: -x[1]):
    neut = r[8].get("neutralization", "?")[:4]; uni = r[8].get("universe", "?")[:4]
    print(f"{r[0]:42s} S={r[1]:.2f} F={r[2]:.2f} TVR={r[3]:.3f} M={r[4]:.1f}bp {uni}/{neut} fails={r[5]}")

# 2) S>2 但 TVR 或其他略差的
print("\n=== S>2.0 全部变体 ===")
for r in sorted([r for r in rows if r[1] and r[1] > 2.0], key=lambda x: -x[1]):
    print(f"{r[0]:42s} S={r[1]:.2f} F={r[2]} TVR={r[3]} M={r[4]} fails={r[5]}")

# 3) revDz / eod_reversal 族概览
print("\n=== rev* 族 S>1.8 ===")
for r in sorted([r for r in rows if r[0].startswith("rev") and r[1] and r[1] > 1.8], key=lambda x: -x[1]):
    print(f"{r[0]:42s} S={r[1]:.2f} F={r[2]} TVR={r[3]} M={r[4]} fails={r[5]}")

# 4) revDz 骨架表达式样本
print("\n=== revDz 表达式样本 ===")
for r in rows:
    if r[0].startswith("revDz"):
        print(r[0], "->", r[7])
        break
print("\n=== revTR 表达式样本 ===")
for r in rows:
    if r[0].startswith("revTR"):
        print(r[0], "->", r[7])
        break

print(f"\ntotal={len(rows)}")
