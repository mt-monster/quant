#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线分析 v53 checkpoint: 多样性评估 + 阶段总结 (纯本地, 不调 API)."""
import json, os, re, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_HERE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(_HERE, "results", "v53b_glb_intraday_checkpoint.json")

ck = json.load(open(CKPT, encoding="utf-8"))
rs = [r for r in ck.get("results", []) if r.get("sharpe") is not None]
print(f"total evaluated: {len(rs)}  found: {len(ck.get('found', []))}")

ops_all, fields_all, skels, styles = set(), set(), Counter(), Counter()
for r in rs:
    e = r.get("expr") or ""
    ops_all |= set(re.findall(r"([a-z_]+)\(", e))
    fields_all |= set(re.findall(r"(?:ts_backfill\()([a-z0-9_]+)", e))
    sk = re.sub(r"[a-z0-9_]+(?=[,)])", "X", e); sk = re.sub(r"\d+", "N", sk)
    skels[sk] += 1
    styles[r.get("style") or "?"] += 1

print("\n== 多样性 ==")
print(f"操作符({len(ops_all)}): {sorted(ops_all)}")
print(f"字段({len(fields_all)}): {sorted(fields_all)}")
print(f"骨架数: {len(skels)}")
print(f"风格分布: {dict(styles)}")

# 最优结果排名
rs.sort(key=lambda x: -(x.get("sharpe") or 0))
print("\n== TOP12 (按 Sharpe) ==")
for r in rs[:12]:
    print(f"  {r['label']:38s} S={r['sharpe']:.2f} F={r['fitness']:.2f} "
          f"TVR={r['tvr']:.3f} M={r['margin_bp']:.1f}bp fails={r.get('fails', [])[:3]}")

# margin>=10bp 且 S>1.58 的"仅平台check卡住"名单
print("\n== IS全过但平台check卡 ==")
for r in rs:
    fl = r.get("fails") or []
    if r["sharpe"] > 1.58 and r["fitness"] > 1.0 and r["margin_bp"] > 10 and 0.05 < r["tvr"] < 0.30:
        print(f"  {r['label']:38s} S={r['sharpe']:.2f} F={r['fitness']:.2f} M={r['margin_bp']:.1f}bp {fl}")

# 失败原因归因
fail_reasons = Counter()
for r in rs:
    for f in (r.get("fails") or []):
        fail_reasons[f.split("=")[0]] += 1
print(f"\n== 失败原因分布 == {dict(fail_reasons)}")

# 维度切片: universe / neut / decay 的平均 sharpe
def slice_stat(keyf):
    agg = defaultdict(list)
    for r in rs:
        agg[keyf(r)].append(r["sharpe"])
    return {k: round(sum(v) / len(v), 3) for k, v in sorted(agg.items())}

print("\n== 切片均值 Sharpe ==")
print("universe:", slice_stat(lambda r: (r.get("settings") or {}).get("universe", "?")))
print("neut:    ", slice_stat(lambda r: (r.get("settings") or {}).get("neutralization", "?")))
print("decay:   ", slice_stat(lambda r: (r.get("settings") or {}).get("decay", "?")))
