#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v60 待跑表达式本地约束校验 (纯本地, 不调 API, 不 import scan 模块避免副作用).

检查项:
  1. 操作符数量 < 6
  2. 禁用算子: trade_when / add() / multiply()
  3. 单表达式数据集字段数 1-2
  4. 字段真实存在于 global_seasonal_model 且 coverage > 0.90
  5. 变体 label 与 checkpoint 已评估 label 的冲突(会被去重跳过)统计
"""
import ast, json, os, re, sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(_HERE, "scan_v63_glb_cnn.py")
FIELDS_JSON = os.path.join(_HERE, "results", "glb_fields_chart_cnn_alpha.json")
CKPT = os.path.join(_HERE, "results", "v63_glb_cnn_checkpoint.json")

# 非数据集字段的标识符白名单 (group 参数等)
GROUPS = {"industry", "subindustry", "sector", "market", "country", "exchange"}
BANNED = {"trade_when", "add", "multiply"}

# ---- 1. 从源码 ast 提取 STYLES 字面量 ----
tree = ast.parse(open(SCAN, encoding="utf-8").read())
styles = None
for node in ast.walk(tree):
    if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "STYLES":
        styles = ast.literal_eval(node.value)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if getattr(t, "id", "") == "STYLES":
                styles = ast.literal_eval(node.value)
assert styles, "STYLES not found"

# ---- 2. 字段覆盖率表 ----
d = json.load(open(FIELDS_JSON, encoding="utf-8"))
fl = d.get("fields") if isinstance(d, dict) else d
cov = {f.get("id"): (f.get("coverage") or 0) for f in fl}

# ---- 3. 逐条检查 ----
errors, warns = [], []
all_ops, all_fields = Counter(), Counter()
n_expr = 0
for style, exprs in styles.items():
    for tag, expr in exprs:
        n_expr += 1
        ops = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", expr)
        idents = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", expr)
        fields = sorted({i for i in idents if i not in ops and i not in GROUPS
                         and not i.isdigit()})
        all_ops.update(ops)
        all_fields.update(fields)
        # 1) 操作符数量
        if len(ops) >= 6:
            errors.append(f"{tag}: 操作符 {len(ops)} 个 >= 6: {ops}")
        # 2) 禁用算子
        bad = [o for o in ops if o in BANNED]
        if bad:
            errors.append(f"{tag}: 使用禁用算子 {bad}")
        # 3) 字段数
        if not (1 <= len(fields) <= 2):
            errors.append(f"{tag}: 字段数 {len(fields)} 不在 1-2: {fields}")
        # 4) 字段存在性/覆盖率
        for f in fields:
            if f not in cov:
                errors.append(f"{tag}: 字段不存在于数据集: {f}")
            elif cov[f] <= 0.90:
                warns.append(f"{tag}: 字段 {f} coverage={cov[f]:.3f} <= 0.90")

print(f"表达式总数: {n_expr}  ({len(styles)} styles)")
print(f"操作符探索({len(all_ops)}): {dict(all_ops)}")
print(f"字段探索({len(all_fields)}):")
for f, c in all_fields.most_common():
    print(f"  {f}  x{c}  cov={cov.get(f, 'MISSING')}")

# ---- 4. label 冲突(checkpoint 去重) ----
UNIVERSES = ["MINVOL1M"]; DECAYS = [0, 3]
NEUTS = ["COUNTRY"]; TRUNCS = [0.02]
labels = set()
STYLE_DECAYS = {"bb": [3, 6], "q5t": [3, 6], "sgl": [3, 6], "cty": [3, 6], "fw": [0, 3], "fr": [0, 3], "f8": [0, 3], "ft": [0, 3], "cf": [0, 3]}  # 与 scan_v60 STYLE_OVERRIDES 保持一致
for style, exprs in styles.items():
    for tag, expr in exprs:
        for uni in UNIVERSES:
            for decay in STYLE_DECAYS.get(style, DECAYS):
                for neut in NEUTS:
                    for trunc in TRUNCS:
                        labels.add(f"{tag}_{uni[:4]}_d{decay}_{neut[:4]}_t{int(trunc*100)}")
done = set()
if os.path.exists(CKPT):
    ck = json.load(open(CKPT, encoding="utf-8"))
    done = {r.get("label") for r in ck.get("results", [])}
overlap = labels & done
print(f"\n变体总数: {len(labels)}  checkpoint 已评估: {len(done)}  label 冲突(将被跳过): {len(overlap)}")
if overlap:
    for l in sorted(overlap)[:10]:
        print(f"  overlap: {l}")

print("\n== 错误 ==" if errors else "\n== 无错误 ==")
for e in errors:
    print("  [ERR]", e)
print("== 警告 ==" if warns else "== 无警告 ==")
for w in warns:
    print("  [WARN]", w)
print("\nLINT_RESULT:", "FAIL" if errors else "PASS")
