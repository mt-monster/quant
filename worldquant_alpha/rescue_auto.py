#!/usr/bin/env python3
"""近关扫描 + 自动选救援脚本 (供 fleet_keeper 调用)。

开闸规则:
  A 降换手: S>=1.8 且 TVR>=0.35 (或 F<0.9 且 TVR>=0.35)
  B 抬S/F:  TVR∈(5%,30%) 且 M>10 且 (1.30<=S<1.58 或 0.80<=F<1.0)
  放弃: ABANDONED / 同 dataset+mode 已跑完 found=0 且未刷新更优父本
"""
from __future__ import annotations

import json
import os
import re
from glob import glob
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(_HERE, "results")

# 硬放弃 (PC/结构失败)
ABANDONED = {
    "hiring_trends",  # PC~0.9
    "dl_riskfree_returns",  # R1 平滑后 S 塌
}

GATE_S, GATE_F, GATE_M = 1.58, 1.0, 10.0


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _extract_field(expr: str) -> Optional[str]:
    if not expr:
        return None
    for pat in (
        r"ts_backfill\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*,",
        r"vec_avg\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",
        r"ts_mean\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*,",
    ):
        m = re.search(pat, expr)
        if m:
            return m.group(1)
    return None


def _dataset_from_path(path: str, row: dict) -> str:
    ds = row.get("dataset")
    if ds:
        return str(ds)
    base = os.path.basename(path)
    m = re.search(r"_tri_([a-z0-9_]+)_checkpoint", base)
    if m:
        return m.group(1)
    if "rescue_r3" in base or "rescue_tvr_r2_web" in base:
        return "web_traffic_engage"
    if "rescue_tvr" in base:
        return "dl_riskfree_returns"
    return "unknown"


def iter_result_rows() -> List[Tuple[str, dict, str]]:
    """[(dataset, row, source_file)]"""
    out = []
    patterns = [
        os.path.join(RESULTS, "*_checkpoint.json"),
        os.path.join(RESULTS, "rescue_*.json"),
    ]
    seen_paths = set()
    for pat in patterns:
        for path in glob(pat):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                d = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            if isinstance(d, list):
                rows = d
            elif isinstance(d, dict):
                rows = d.get("results") or []
            else:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if row.get("sharpe") is None:
                    continue
                ds = _dataset_from_path(path, row)
                out.append((ds, row, os.path.basename(path)))
    return out


def classify(row: dict) -> Optional[str]:
    """返回 'tvr_cut' | 'lift_sf' | None"""
    s = _f(row.get("sharpe"))
    if s is None:
        return None
    fit = _f(row.get("fitness")) or 0.0
    tvr = _f(row.get("tvr")) or 0.0
    m = row.get("margin_bp")
    if m is None:
        m = _f(row.get("margin")) or 0.0
        if 0 < m < 1:
            m *= 10000
    else:
        m = _f(m) or 0.0

    # B: 近关抬 S/F
    if 0.05 < tvr < 0.30 and m > GATE_M:
        if (1.30 <= s < GATE_S) or (0.80 <= fit < GATE_F):
            return "lift_sf"
    # A: 高 S 高换手
    if s >= 1.8 and tvr >= 0.35:
        return "tvr_cut"
    if s >= 1.8 and fit < 0.9 and tvr >= 0.35:
        return "tvr_cut"
    return None


def score_candidate(mode: str, row: dict) -> float:
    s = _f(row.get("sharpe")) or 0
    fit = _f(row.get("fitness")) or 0
    tvr = _f(row.get("tvr")) or 0
    m = _f(row.get("margin_bp")) or 0
    if mode == "lift_sf":
        # 越近门槛越高分
        return s * 10 + fit * 8 + min(m, 20) * 0.2 - abs(tvr - 0.12) * 5
    # tvr_cut: 高 S 优先，TVR 越高越值得救
    return s * 10 + min(tvr, 1.0) * 3 + fit


def _rescue_done_key(dataset: str, mode: str) -> str:
    return f"{dataset}::{mode}"


def load_rescue_done(st: dict) -> set:
    return set(st.get("rescue_done") or [])


def scan_near_misses(st: dict) -> List[Dict[str, Any]]:
    """按分数排序的近关列表。"""
    done = load_rescue_done(st)
    abandoned = set(ABANDONED) | set(st.get("rescue_abandoned") or [])
    best: Dict[str, Dict[str, Any]] = {}

    for ds, row, src in iter_result_rows():
        if ds in abandoned or ds == "unknown":
            continue
        mode = classify(row)
        if not mode:
            continue
        key = _rescue_done_key(ds, mode)
        if key in done:
            # 同 dataset+mode 已自动跑完则不再开 (避免 R2 后又用探索期 S=2.x 重开 tvr)
            continue
        field = row.get("field") or _extract_field(row.get("expr") or "")
        sc = score_candidate(mode, row)
        cand = {
            "dataset": ds,
            "mode": mode,
            "score": sc,
            "sharpe": _f(row.get("sharpe")),
            "fitness": _f(row.get("fitness")),
            "tvr": _f(row.get("tvr")),
            "margin_bp": _f(row.get("margin_bp")) or _f(row.get("margin")),
            "field": field,
            "label": row.get("label"),
            "expr": row.get("expr"),
            "source": src,
        }
        k = f"{ds}:{mode}"
        if k not in best or sc > best[k]["score"]:
            best[k] = cand

    cands = sorted(best.values(), key=lambda x: -x["score"])
    return cands


def pick_script(cand: Dict[str, Any]) -> Tuple[str, List[str], str]:
    """返回 (script_basename, argv_extra, ckpt_path)."""
    ds = cand["dataset"]
    mode = cand["mode"]
    ts_tag = re.sub(r"[^a-z0-9_]+", "_", ds.lower())[:28]
    if mode == "lift_sf" and ds == "web_traffic_engage":
        script = "scan_rescue_r3_web_lift.py"
        ckpt = os.path.join(RESULTS, "rescue_r3_web_lift_checkpoint.json")
        return script, [], ckpt
    if mode == "lift_sf":
        # 通用抬 S/F: 复用 r3 脚本前先走 tvr 脚本的轻平滑反面 — 用 auto lift wrapper
        script = "scan_rescue_lift_generic.py"
        ckpt = os.path.join(RESULTS, f"rescue_auto_{ts_tag}_lift_checkpoint.json")
        field = cand.get("field") or ""
        extra = ["--dataset", ds, "--ckpt", ckpt]
        if field:
            extra += ["--field", field]
        return script, extra, ckpt
    # tvr_cut
    script = "scan_rescue_tvr.py"
    ckpt = os.path.join(RESULTS, f"rescue_auto_{ts_tag}_tvr_checkpoint.json")
    return script, ["--dataset", ds, "--ckpt", ckpt], ckpt


def mark_rescue_finished(st: dict, dataset: str, mode: str, ckpt: str) -> dict:
    """救援 ckpt 显示跑完且 found=0 时记入 done，避免空转重复开。"""
    if not os.path.exists(ckpt):
        return st
    try:
        ck = json.load(open(ckpt, encoding="utf-8"))
    except Exception:
        return st
    found = ck.get("found_alphas") or []
    res = ck.get("results") or []
    if found:
        # 已找到则不再自动开同 mode
        key = _rescue_done_key(dataset, mode)
        done = set(st.get("rescue_done") or [])
        done.add(key)
        st["rescue_done"] = sorted(done)
        meta = dict(st.get("rescue_done_meta") or {})
        meta[key] = {"best_s": 9.9, "found": True, "at": __import__("time").strftime("%Y-%m-%d %H:%M:%S")}
        st["rescue_done_meta"] = meta
        return st
    # 无 found: 若结果数够多视为本轮结束
    ok = [r for r in res if isinstance(r, dict) and r.get("sharpe") is not None]
    if len(ok) < 24 and len(res) < 40:
        return st
    best_s = max((_f(r.get("sharpe")) or 0) for r in ok) if ok else 0
    key = _rescue_done_key(dataset, mode)
    done = set(st.get("rescue_done") or [])
    done.add(key)
    st["rescue_done"] = sorted(done)
    meta = dict(st.get("rescue_done_meta") or {})
    meta[key] = {
        "best_s": best_s,
        "found": False,
        "n_ok": len(ok),
        "at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    }
    st["rescue_done_meta"] = meta
    # 若 lift 后仍 S<1.45 且已充分尝试 → 放弃该 mode
    if mode == "lift_sf" and best_s < 1.45 and len(ok) >= 48:
        abd = set(st.get("rescue_abandoned") or [])
        abd.add(dataset)
        st["rescue_abandoned"] = sorted(abd)
    if mode == "tvr_cut" and best_s < 1.0 and len(ok) >= 48:
        abd = set(st.get("rescue_abandoned") or [])
        abd.add(dataset)
        st["rescue_abandoned"] = sorted(abd)
    return st


def sync_finished_rescues(st: dict) -> dict:
    """根据已知 ckpt 更新 done/abandoned。"""
    known = [
        ("web_traffic_engage", "lift_sf", os.path.join(RESULTS, "rescue_r3_web_lift_checkpoint.json")),
        ("web_traffic_engage", "tvr_cut", os.path.join(RESULTS, "rescue_tvr_r2_web_checkpoint.json")),
        ("dl_riskfree_returns", "tvr_cut", os.path.join(RESULTS, "rescue_tvr_checkpoint.json")),
    ]
    for ds, mode, ckpt in known:
        st = mark_rescue_finished(st, ds, mode, ckpt)
    # auto ckpts
    for path in glob(os.path.join(RESULTS, "rescue_auto_*_checkpoint.json")):
        base = os.path.basename(path)
        m = re.search(r"rescue_auto_([a-z0-9_]+)_(tvr|lift)_checkpoint", base)
        if not m:
            continue
        ds, kind = m.group(1), m.group(2)
        mode = "tvr_cut" if kind == "tvr" else "lift_sf"
        st = mark_rescue_finished(st, ds, mode, path)
    return st
