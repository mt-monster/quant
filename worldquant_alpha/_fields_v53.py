#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字段族盘点: 从 586 字段里找收益来源正交的新家族 (纯本地)."""
import json, os, re, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(_HERE, "results", "glb_fields_intraday_pv_feats.json")
d = json.load(open(P, encoding="utf-8"))
fields = d.get("fields") if isinstance(d, dict) else d
print("total fields:", len(fields))
print("sample keys:", list(fields[0].keys()) if fields else None)

# 已用字段(证伪或已挖)
used = {
    "mean_last_trade_price_return_30m_pre_close_2", "mean_last_trade_price_return_60m_pre_close_2",
    "last_trade_price_last_interval", "max_high_price_60m_pre_close_2", "min_low_price_60m_pre_close_2",
    "mean_slippage_60m_pre_close_2", "mean_trade_volume_30m_pre_close_2", "trade_volume_last_interval",
}

hi = [f for f in fields if (f.get("coverage") or 0) > 0.90]
print("cov>0.90:", len(hi))

# 按语义前缀归族
fam = defaultdict(list)
for f in hi:
    fid = f.get("id") or ""
    # 去掉窗口/时段后缀归并家族
    stem = re.sub(r"_\d+m", "_Xm", fid)
    stem = re.sub(r"_\d+$", "", stem)
    fam[stem].append((fid, round(f.get("coverage") or 0, 3)))

# 打印未探索的家族(排除 used 所在家族)
used_stems = set()
for u in used:
    s = re.sub(r"_\d+m", "_Xm", u); s = re.sub(r"_\d+$", "", s)
    used_stems.add(s)

print("\n== 未探索家族 (cov>0.90, 按家族大小) ==")
items = sorted(fam.items(), key=lambda kv: -len(kv[1]))
for stem, lst in items:
    mark = " *USED*" if stem in used_stems else ""
    print(f"[{len(lst):2d}] {stem}{mark}")
    for fid, cov in lst[:4]:
        print(f"      {fid}  cov={cov}")
