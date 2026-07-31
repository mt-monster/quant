# -*- coding: utf-8 -*-
"""列出 intraday_pv_feats 高覆盖字段, 按语义族分组, 标记已用/未用"""
import json, os, re

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "glb_fields_intraday_pv_feats.json")
with open(P, "r", encoding="utf-8") as f:
    data = json.load(f)

if isinstance(data, dict):
    print("TOP KEYS:", list(data.keys())[:10])
    for k in list(data.keys())[:2]:
        v = data[k]
        print(f"  {k} -> {type(v).__name__}", (v[:1] if isinstance(v, list) else v))
    # 猜常见结构
    items = data.get("results") or data.get("fields") or data.get("data") or []
else:
    items = data

USED = {
    "mean_last_trade_price_return_30m_pre_close_2", "mean_vwap_return_30m_pre_close_2",
    "mean_bid_ask_size_ratio_60m_pre_close_2", "mean_bid_ask_size_ratio_30m_pre_close_2",
    "mean_ask_price_return_60m_pre_close_2", "mean_bid_price_return_60m_pre_close_2",
    "last_trade_price_60m_pre_close_2", "last_trade_price_60m_post_open",
    "mean_price_modulo_100_ratio_30m_pre_close_2", "mean_price_modulo_10_ratio_30m_pre_close_2",
    "max_last_trade_price_60m_pre_close_2", "min_last_trade_price_60m_pre_close_2",
}

rows = []
for it in items:
    if not isinstance(it, dict):
        continue
    fid = it.get("id") or it.get("field") or ""
    cov = it.get("coverage")
    rows.append((fid, cov))

print(f"total fields: {len(rows)}")

# 按语义关键词分族
fams = {}
for fid, cov in rows:
    key = re.sub(r"_?\d+m_(pre_close|post_open)(_\d)?$", "", fid)
    key = re.sub(r"^(mean|max|min|std|sum|last|first)_", "", key)
    fams.setdefault(key, []).append((fid, cov))

print("\n=== 语义族 (按字段数排序) ===")
for k in sorted(fams, key=lambda x: -len(fams[x])):
    used = any(f in USED for f, _ in fams[k])
    covs = [c for _, c in fams[k] if isinstance(c, (int, float))]
    cmax = max(covs) if covs else None
    tag = "USED" if used else "    "
    print(f"[{tag}] {k:55s} n={len(fams[k]):3d} maxcov={cmax}")

# 未用且高覆盖族的字段示例
print("\n=== 未用族字段示例 (maxcov>=0.9) ===")
for k in sorted(fams, key=lambda x: -len(fams[x])):
    used = any(f in USED for f, _ in fams[k])
    if used:
        continue
    covs = [(f, c) for f, c in fams[k] if isinstance(c, (int, float)) and c >= 0.9]
    if not covs:
        continue
    for f, c in sorted(covs, key=lambda x: -x[1])[:4]:
        print(f"  {f:70s} cov={c:.2f}")
