import json, re, csv, os
from datetime import datetime

RES = r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha\results"
CK = os.path.join(RES, "v39b_sub_micro_checkpoint.json")
ck = json.load(open(CK, encoding="utf-8"))
results = ck["results"]
pc = [r for r in results if r.get("status") != "FAIL"]
pc.sort(key=lambda r: -(r.get("sharpe") or 0))

FM = {"t1": "eur_top_value_1", "t2": "eur_top_value_2",
      "a1": "eur_aggregated_value_1", "a2": "eur_aggregated_value_2"}

def parse_label(lbl):
    m = re.search(r"^(?:gz|gzsec|wz|sc|gr)_(t1|t2|a1|a2)_", lbl)
    code = m.group(1) if m else "?"
    w = re.search(r"b(\d+)z(\d+)", lbl)
    bf, zw = (w.group(1), w.group(2)) if w else ("", "")
    return FM.get(code, code), bf, zw

rows = []
for r in pc:
    s = r.get("settings", {})
    field, bf, zw = parse_label(r["label"])
    sub = r.get("sub_univ"); lim = r.get("sub_limit")
    ratio = (sub / lim) if (sub and lim) else None
    over = (sub > lim) if (sub is not None and lim is not None) else None
    rows.append({
        "label": r["label"], "field": field, "bf": bf, "zw": zw,
        "universe": s.get("universe"), "delay": s.get("delay"),
        "decay": s.get("decay"), "neutralization": s.get("neutralization"),
        "truncation": s.get("truncation"), "testPeriod": s.get("testPeriod"),
        "pasteurization": s.get("pasteurization"), "maxTrade": s.get("maxTrade"),
        "nanHandling": s.get("nanHandling"), "unitHandling": s.get("unitHandling"),
        "sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
        "tvr": r.get("tvr"), "margin": r.get("margin"),
        "sub_univ": sub, "sub_limit": lim,
        "sub_ratio": round(ratio, 3) if ratio else "",
        "over_limit": "YES" if over else ("NO" if over is False else ""),
        "status": r.get("status"), "expr": r.get("expr"),
    })

# ---- CSV ----
csv_path = os.path.join(RES, "v39b_pass_cheap_candidates.csv")
cols = ["label", "field", "bf", "zw", "universe", "delay", "decay",
        "neutralization", "truncation", "testPeriod", "pasteurization",
        "maxTrade", "nanHandling", "unitHandling", "sharpe", "fitness",
        "tvr", "margin", "sub_univ", "sub_limit", "sub_ratio",
        "over_limit", "status", "expr"]
with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow(r)

# ---- MD ----
md_path = os.path.join(RES, "v39b_pass_cheap_candidates.md")
now = datetime.now().strftime("%Y-%m-%d %H:%M")
L = []
L.append("# V39b PASS_CHEAP 候选提交清单\n")
L.append(f"> 生成时间：{now}  |  来源：`v39b_sub_micro_checkpoint.json`")
L.append(f"> 数据说明：scan_v39b 是「不提交」评估扫描；以下 {len(rows)} 个变体通过全部硬闸门，但 sub_universe 略超限制 → 被标 `PASS_CHEAP`。`sub_univ`/`sub_limit` 取自 WQ 模拟 API 返回的 `is` 字段（即 WQ 后台真实值），需人工确认后提交。\n")
L.append("## 汇总（按 Sharpe 降序）\n")
L.append("| # | label | field | W | neut | decay | trunc | S | F | tvr | sub_univ/lim | 超标 |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for i, r in enumerate(rows, 1):
    L.append(f"| {i} | {r['label']} | {r['field']} | {r['zw']} | {r['neutralization']} | {r['decay']} | {r['truncation']} | {r['sharpe']} | {r['fitness']} | {r['tvr']} | {r['sub_univ']}/{r['sub_limit']} | {r['over_limit']} |")
L.append("\n## 各候选完整表达式与 sub_universe 明细\n")
for i, r in enumerate(rows, 1):
    L.append(f"### {i}. {r['label']}  ({r['status']})")
    L.append(f"- **表达式**：`{r['expr']}`")
    L.append(f"- **指标**：Sharpe={r['sharpe']}, Fitness={r['fitness']}, TVR={r['tvr']}, Margin={r['margin']}")
    flag = "**超标**" if r['over_limit'] == "YES" else "合规"
    L.append(f"- **sub_universe 明细（WQ 真实值）**：sub_univ={r['sub_univ']}, sub_limit={r['sub_limit']}, 比值={r['sub_ratio']} → {flag}")
    L.append(f"- **settings**：universe={r['universe']}, delay={r['delay']}, decay={r['decay']}, neutralization={r['neutralization']}, truncation={r['truncation']}, testPeriod={r['testPeriod']}, pasteurization={r['pasteurization']}, maxTrade={r['maxTrade']}, nanHandling={r['nanHandling']}, unitHandling={r['unitHandling']}")
    L.append("")
open(md_path, "w", encoding="utf-8").write("\n".join(L))

# ---- 打印 sub_universe 明细 ----
print("===== sub_universe 真实明细（WQ 模拟 API 返回 is 字段） =====")
for r in rows:
    flag = "超标" if r["over_limit"] == "YES" else "合规"
    print(f"  {r['label']:42} sub_univ={r['sub_univ']}  limit={r['sub_limit']}  ratio={r['sub_ratio']}  -> {flag}")
print(f"\n候选总数：{len(rows)}")
print(f"CSV : {csv_path}")
print(f"MD  : {md_path}")
