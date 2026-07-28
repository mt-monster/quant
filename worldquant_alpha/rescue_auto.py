#!/usr/bin/env python3
"""近关扫描 + 自动选救援脚本 (供 fleet_keeper 调用)。

硬规则 (用户 2026-07-27):
  救援槽必须优先跑「候选因子里潜力最大」的回测任务。
  潜力 = 距全部门槛最近 + 已过项最多 + 父本信号强度；不是谁先扫到谁。

开闸规则:
  A 降换手 tvr_cut: S>=1.8 且 TVR>=0.35
  B 抬S/F lift_sf:  TVR∈(5%,30%) 且 M>10 且 (1.30<=S<1.58 或 0.80<=F<1.0)
  C 深挖 deep_s:   F>=1 且 M>10 且 TVR∈带 且 1.50<=S<1.58 (差最后一口气)
  放弃: ABANDONED / 同 dataset+mode 已跑完 found=0
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
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _metrics(row: dict) -> Tuple[float, float, float, float]:
    s = _f(row.get("sharpe")) or 0.0
    fit = _f(row.get("fitness")) or 0.0
    tvr = _f(row.get("tvr")) or 0.0
    m = _f(row.get("margin_bp"))
    if m is None:
        m = _f(row.get("margin")) or 0.0
    # 统一成 bp: 平台 margin 常为小数 (0.0015≈15bp)
    if 0 < abs(m) < 1:
        m *= 10000
    return s, fit, tvr, m


def _extract_field(expr: str) -> Optional[str]:
    if not expr:
        return None
    for pat in (
        r"ts_backfill\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*,",
        r"vec_avg\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",
        r"ts_mean\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*,",
        r"ts_rank\(\s*ts_backfill\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*,",
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
    if "model313" in base:
        return "model313"
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
    """返回 'deep_s' | 'lift_sf' | 'tvr_cut' | None。deep_s 优先于 lift_sf。"""
    s, fit, tvr, m = _metrics(row)
    tvr_ok = GATE_TVR_LO < tvr < GATE_TVR_HI
    # C: 只差 S 一口气 (潜力最大档)
    if tvr_ok and m > GATE_M and fit >= GATE_F and 1.50 <= s < GATE_S:
        return "deep_s"
    # B: 近关抬 S/F
    if tvr_ok and m > GATE_M:
        if (1.30 <= s < GATE_S) or (0.80 <= fit < GATE_F):
            return "lift_sf"
    # A: 高 S 高换手
    if s >= 1.8 and tvr >= 0.35:
        return "tvr_cut"
    if s >= 1.8 and fit < 0.9 and tvr >= 0.35:
        return "tvr_cut"
    return None


def score_candidate(mode: str, row: dict) -> float:
    """潜力分: 救援槽永远取最高分。

    优先级直觉:
      1) 已过项越多越好 (F/TVR/M 过关大幅加分)
      2) 距 S=1.58 越近越好 (差 0.01 >> 差 0.3)
      3) 父本 S/F 绝对值作微调
      4) deep_s > lift_sf > tvr_cut (同条件下)
    """
    s, fit, tvr, m = _metrics(row)
    passed = 0
    if fit >= GATE_F:
        passed += 1
    if GATE_TVR_LO < tvr < GATE_TVR_HI:
        passed += 1
    if m > GATE_M:
        passed += 1
    # S 距门槛 (越小越好 → 用 (GATE_S - s) 的倒数型加分)
    gap_s = max(GATE_S - s, 0.0)
    close_s = max(0.0, 40.0 - gap_s * 80.0)  # gap=0.01→39.2; gap=0.28→17.6; gap>=0.5→0

    mode_bonus = {"deep_s": 100.0, "lift_sf": 40.0, "tvr_cut": 10.0}.get(mode, 0.0)
    # 已过 3 项 (只差 S) 再加码
    almost_ready = 50.0 if passed >= 3 and s < GATE_S else (20.0 if passed >= 2 else 0.0)

    base = (
        mode_bonus
        + almost_ready
        + passed * 25.0
        + close_s
        + s * 3.0
        + fit * 2.0
        + min(m, 30.0) * 0.15
    )
    if mode == "tvr_cut":
        # 高换手: 额外看 S 强度
        base += s * 2.0 + min(tvr, 1.0) * 5.0
    return base


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
    if mode == "deep_s" and ds == "model313":
        script = "scan_rescue_model313_deep.py"
        ckpt = os.path.join(RESULTS, "rescue_model313_deep_checkpoint.json")
        return script, [], ckpt
    if mode == "deep_s":
        # 通用深挖: 复用 lift 骨架但独立 ckpt，避免与已 done 的 lift 冲突
        script = "scan_rescue_lift_generic.py"
        ckpt = os.path.join(RESULTS, f"rescue_auto_{ts_tag}_deep_checkpoint.json")
        field = cand.get("field") or ""
        extra = ["--dataset", ds, "--ckpt", ckpt]
        if field:
            extra += ["--field", field]
        return script, extra, ckpt
    if mode == "lift_sf" and ds == "web_traffic_engage":
        script = "scan_rescue_r3_web_lift.py"
        ckpt = os.path.join(RESULTS, "rescue_r3_web_lift_checkpoint.json")
        return script, [], ckpt
    if mode == "lift_sf":
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
    # 若 lift/deep 后仍 S<1.45 且已充分尝试 → 放弃该 dataset
    if mode in ("lift_sf", "deep_s") and best_s < 1.45 and len(ok) >= 48:
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
        ("model313", "deep_s", os.path.join(RESULTS, "rescue_model313_deep_checkpoint.json")),
    ]
    for ds, mode, ckpt in known:
        st = mark_rescue_finished(st, ds, mode, ckpt)
    # auto ckpts
    for path in glob(os.path.join(RESULTS, "rescue_auto_*_checkpoint.json")):
        base = os.path.basename(path)
        m = re.search(r"rescue_auto_([a-z0-9_]+)_(tvr|lift|deep)_checkpoint", base)
        if not m:
            continue
        ds, kind = m.group(1), m.group(2)
        mode = {"tvr": "tvr_cut", "lift": "lift_sf", "deep": "deep_s"}[kind]
        st = mark_rescue_finished(st, ds, mode, path)
    return st
