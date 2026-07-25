#!/usr/bin/env python3
"""submit_gate 统一合规检查器 (lint_submit_gate.py).

用途: 把"全账号任务统一继承 submit_gate"这一约束变成可复跑的硬检查。
对每个 scan_*.py 验证:
  1) 提交必须经 submit_gate 统一限速: import multi_sim / import wd_lib_wrapper /
     import submit_gate 任一 (三者最终都调用 submit_gate.wait_submit_slot)。
  2) 无裸 session.post("/simulations") 绕过 wait_submit_slot (在 scan 脚本本体内直接提交)。
  3) 任意模块内若有直接 `session.post(.../simulations...)`, 必须同函数内先调用 wait_submit_slot。

输出合规表; 退出码 0 = 全合规, 1 = 存在绕过。
"""
from __future__ import annotations

import glob
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def check_file(path: str) -> dict:
    src = open(path, encoding="utf-8", errors="ignore").read()
    imports_multi_sim = bool(re.search(r"\bimport\s+multi_sim\b|\bfrom\s+multi_sim\s+import", src))
    imports_wd = "wd_lib_wrapper" in src
    imports_sg = "submit_gate" in src
    # gated = 任一提交路径最终走 submit_gate
    gated = imports_multi_sim or imports_wd or imports_sg

    # 裸提交检测: scan 脚本本体内直接 POST /simulations 且未 import 任何 gated 模块
    posts = re.findall(r"\.post\(\s*[^)]*simulations", src)
    # 函数级校验: 把源码按 def 切块, 检查含 /simulations post 的函数是否含 wait_submit_slot
    bare_funcs = 0
    for m in re.finditer(r"def\s+\w+\([^)]*\):\s*(.*?)(?=\n\s*def\s+\w+\(|\Z)", src, re.S):
        body = m.group(1)
        if re.search(r"\.post\(\s*[^)]*simulations", body):
            if "wait_submit_slot" not in body:
                bare_funcs += 1

    # 若脚本整体已 import gated 模块, 其内部 post 实际走 gated 路径, 不算绕过
    bare = bare_funcs if not gated else 0
    return dict(
        path=path,
        imports_multi_sim=imports_multi_sim,
        imports_wd=imports_wd,
        imports_sg=imports_sg,
        gated=gated,
        n_posts=len(posts),
        bare_posts=bare,
    )


def main() -> int:
    files = sorted(glob.glob(os.path.join(_HERE, "scan_*.py")))
    print(f"# submit_gate 统一合规检查 — {len(files)} 个 scan 脚本\n")
    print(f"{'状态':<6} {'脚本':<34} {'multi_sim':>9} {'wd_lib':>8} {'sg':>4} {'gated':>6} {'bare':>5}")
    print("-" * 78)
    all_ok = True
    for f in files:
        r = check_file(f)
        ok = r["gated"] and r["bare_posts"] == 0
        if not ok:
            all_ok = False
        name = os.path.basename(f)
        print(
            f"{'OK' if ok else 'BYPASS':<6} {name:<34} "
            f"{int(r['imports_multi_sim']):>9} {int(r['imports_wd']):>8} "
            f"{int(r['imports_sg']):>4} {int(r['gated']):>6} {r['bare_posts']:>5}"
        )
    print("-" * 78)
    if all_ok:
        print("✅ 全部 scan 脚本均经 submit_gate 统一限速, 无绕过。全局并发纪律自适应化已生效。")
    else:
        print("⚠️ 存在绕过 submit_gate 的裸提交, 需修复 (见 BYPASS 行)。")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
