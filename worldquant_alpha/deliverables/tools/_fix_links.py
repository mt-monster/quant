# -*- coding: utf-8 -*-
"""将摘要文档的相对链接改为绝对 file:// URL，让 WorkBuddy 可正确解析。"""
import re, urllib.parse, os

BASE = "C:\\Users\\MENGTAO\\Desktop\\E3\\quant\\worldquant_alpha\\deliverables\\reports"
f = "deliverables/reports/factor_mining_summary.md"
text = open(f, encoding="utf-8").read()

def to_abs(m):
    rel = m.group(1)  # full relative path e.g. "details/foo.md"
    base_unix = BASE.replace("\\", "/")
    parts = rel.split("/")
    encoded_parts = [urllib.parse.quote(p) for p in parts]
    encoded_rel = "/".join(encoded_parts)
    return f"(file:///{base_unix}/{encoded_rel})"

# Match the full path inside parens including details/
new_text = re.sub(r"\((details/[\w_]+\.md)\)", to_abs, text)
open(f, "w", encoding="utf-8").write(new_text)

# Verify all links now absolute
matches = re.findall(r"\(file:///.+?\)", new_text)
print(f"总共找到 {len(matches)} 个 file:// 链接:")
for m in matches:
    print(" ", m)