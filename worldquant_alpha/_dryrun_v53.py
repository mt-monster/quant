# -*- coding: utf-8 -*-
"""dry-run: 只构建 variants 验证数量与新样式, 不发请求"""
import os
os.environ["V53_DRYRUN"] = "1"
import ast

src = open("scan_v53_glb_intraday.py", encoding="utf-8").read()
ast.parse(src)
print("SYNTAX OK")

# 提取 build_variants 依赖并执行
import importlib.util
spec = importlib.util.spec_from_file_location("v53", "scan_v53_glb_intraday.py")
# 不能整体 import（会跑 main），改手动 exec 顶部到 build_variants
lines = src.splitlines()
end = next(i for i, l in enumerate(lines) if l.startswith("def _lane_worker") or l.startswith("class ") or "认证" in l)
snippet = "\n".join(lines[:end])
ns = {"__file__": os.path.abspath("scan_v53_glb_intraday.py")}
try:
    exec(compile(snippet, "v53_head", "exec"), ns)
    vs = ns["build_variants"]()
    print("total variants:", len(vs))
    for st in ("rev_final", "quote_vwap", "close_vol"):
        sub = [v for v in vs if v["style"] == st]
        print(f"{st} variants:", len(sub))
        for v in sub:
            print(" ", v["label"], v["settings"]["decay"])
except Exception as e:
    print("EXEC ERR:", repr(e))
