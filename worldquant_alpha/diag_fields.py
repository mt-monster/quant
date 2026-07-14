#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump real alpha details/check JSON to learn exact field names for hard-gate parsing."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wd_lib_wrapper import WqApiSimple

# 取一个近期已完成回测的 alpha（来自 mining_multi.log）
PIDS = ["1YdOdJrJ", "6X9Z9e5L", "zqmgmJKO"]

api = WqApiSimple()
for pid in PIDS:
    print("=" * 70)
    print("PID:", pid)
    det = api.get_alpha_details(pid)
    print("--- details top-level keys ---")
    print(sorted(det.keys()))
    is_ = det.get("is") or {}
    print("--- details.is keys ---")
    print(sorted(is_.keys()))
    print("--- details.is sample ---")
    for k in sorted(is_.keys()):
        v = is_[k]
        if isinstance(v, (dict, list)):
            print(f"  {k}: <{type(v).__name__}> {json.dumps(v)[:200]}")
        else:
            print(f"  {k}: {v}")
    ch = api.get_alpha_check(pid)
    print("--- check top-level keys ---")
    print(sorted(ch.keys()))
    print("--- check.is keys ---")
    print(sorted((ch.get("is") or {}).keys()))
    checks = (ch.get("is") or {}).get("checks") or []
    print(f"--- check.is.checks ({len(checks)}) ---")
    for c in checks:
        print("  ", c.get("name"), "=", c.get("value"), "result=", c.get("result"))
