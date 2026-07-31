#!/usr/bin/env python3
"""三轨 multi-sim 共享 job runner (从 scan_v45/v46 提取).

一个 scan 变体只需提供 ScanConfig: 数据集/门槛/字段表达式 builder/种子来源/
优先级函数, 其余 simulate/评估/checkpoint/深检/ready 落盘全部由 run_tri_scan 承担。

- 槽位: 3 explore / 3 improve / 2 settings-rescue (tri_track)
- 提交节奏: submit_gate 经 multi_sim 生效; 本 runner 绝不提交 alpha
- 文件名约定 (results/ 下, 由 cfg.version 派生):
    {ver}_tri_progress_{ts}.log / scan_{ver}_tri_{ts}.json / cfg.ckpt_name
- 环境变量: {VER}_COOLDOWN / {VER}_MAX_BATCHES
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# 根目录模块 (multi_sim 等) 依赖仓库根在 sys.path; scan_v* 脚本已保证, 此处兜底
_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, after_batch_cooldown, envelope_summary, run_multi_batch
from progress_logger import ProgressLogger
from tri_track import (
    SLOT_EXPLORE,
    SLOT_IMPROVE,
    SLOT_RESCUE,
    build_improve_variants,
    build_rescue_variants,
    count_operators,
    mix_batch,
    refill_queues_from_results,
)
from wd_lib_wrapper import WqApiSimple

logger = logging.getLogger("tri_runner")

BATCH_SIZE = 8
GATE_SHARPE, GATE_FITNESS, GATE_MARGIN_BP = 1.58, 1.0, 10.0
GATE_TVR_MIN, GATE_TVR_MAX, GATE_RETURNS, GATE_2Y = 0.05, 0.30, 0.05, 1.6
GATE_RISK_NEUT_S, GATE_RISK_NEUT_F, GATE_RISK_NEUT_M_BP = 1.0, 0.7, 10.0
MAX_PROD_CORR, MAX_OPS, TARGET_ALPHAS = 0.70, 6, 1

READY_PATH = os.path.join(_ROOT, "results", "manual_submit_ready.json")


@dataclass
class ScanConfig:
    """一个 scan 变体的全部差异点。"""

    version: str                                    # 如 "v45" (派生路径/env 前缀/标签)
    dataset: str
    task_name: str                                  # ProgressLogger task_name
    ckpt_name: str                                  # results/ 下 checkpoint 文件名
    style: str                                      # found info 的 style 字段
    build_explore: Callable[[], List[Dict[str, Any]]]
    build_seeds: Callable[[], List[Dict[str, Any]]] = lambda: []
    explore_priority: Optional[Callable[[Dict[str, Any]], Any]] = None
    known_pid: Optional[str] = None                 # 与已有 ready alpha 的相关约束
    max_pair_corr: float = 0.40
    target_alphas: int = TARGET_ALPHAS
    max_batches_default: int = 40
    progress_meta: Dict[str, Any] = field(default_factory=dict)


def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def base_settings(universe, decay, neut, trunc=0.08):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": universe, "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc, "pasteurization": "ON",
        "unitHandling": "VERIFY", "nanHandling": "ON", "language": "FASTEXPR",
        "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
    }


def variant_key(v: Dict[str, Any]) -> Tuple:
    s = v.get("settings") or {}
    return (v.get("expr"), s.get("universe"), s.get("decay"), s.get("neutralization"), s.get("truncation"))


def make_variant_adder(variants: List[Dict[str, Any]], seen: Set[Tuple], default_trunc: float, max_ops: int = MAX_OPS):
    """explore builder 的通用 add(): ops 门槛 + 去重 + settings 组装。"""

    def add(label, expr, uni, decay, neut, style, fld, trunc=None):
        t = default_trunc if trunc is None else trunc
        ops = count_operators(expr)
        if ops >= max_ops or ops > 900:
            return
        item = {
            "label": label, "expr": expr, "settings": base_settings(uni, decay, neut, t),
            "style": style, "field": fld, "ops": ops, "track": "explore",
        }
        k = variant_key(item)
        if k in seen:
            return
        seen.add(k)
        variants.append(item)

    return add


def load_checkpoint(ckpt_path):
    if not os.path.exists(ckpt_path):
        return None
    try:
        return json.load(open(ckpt_path, encoding="utf-8"))
    except Exception:
        return None


def save_checkpoint(ckpt_path, results_list, found_list, queues_meta=None):
    tmp = ckpt_path + ".tmp"
    payload = {"results": results_list, "found_alphas": found_list}
    if queues_meta:
        payload["queues"] = queues_meta
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ckpt_path)


def append_ready(info):
    try:
        ready = json.load(open(READY_PATH, encoding="utf-8")) if os.path.exists(READY_PATH) else {"goal": 10, "alphas": []}
        info = dict(info)
        info["n"] = len(ready.get("alphas", [])) + 1
        ready.setdefault("alphas", []).append(info)
        with open(READY_PATH, "w", encoding="utf-8") as f:
            json.dump(ready, f, ensure_ascii=False, indent=2)
        logger.info("Appended ready %d/10", len(ready["alphas"]))
    except Exception as e:
        logger.warning("append_ready: %s", e)


def fetch_checks(api, pid, retries=5):
    for _ in range(retries):
        try:
            r = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if r.status_code == 200 and r.text.strip():
                checks = (r.json().get("is") or {}).get("checks") or []
                return {c.get("name", ""): c for c in checks}, [c.get("name") for c in checks if c.get("result") == "FAIL"], True
            time.sleep(4)
        except Exception:
            time.sleep(8)
    return {}, [], False


def wait_for_pc(api, pid, max_wait_s=3600):
    waited = 0
    while waited < max_wait_s:
        try:
            ch = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                checks = (ch.json().get("is") or {}).get("checks") or []
                pc = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), None)
                if pc and pc.get("result") in ("PASS", "FAIL", "WARNING"):
                    return _f(pc.get("value"))
            time.sleep(30)
            waited += 30
        except Exception:
            time.sleep(30)
            waited += 30
    return None


def check_corr_vs_known(api, pid, known_pid, max_pair_corr) -> Tuple[bool, Any]:
    """与已有 ready alpha 的 pair 相关须 < max_pair_corr; 无本地相关器时放行并标记待验。"""
    try:
        if api.local_sc is not None:
            try:
                c = api.local_sc.corr_pair(pid, known_pid)
                return (c is not None and abs(c) < max_pair_corr), c
            except Exception:
                pass
        logger.warning("pair-corr vs %s unavailable locally; mark pending_corr", known_pid)
        return True, "pending"
    except Exception as e:
        logger.warning("corr check: %s", e)
        return True, "pending"


def test_risk_neutralization(api, expr, base_s):
    settings = {**base_s, "neutralization": "MARKET"}
    try:
        res = api.run_backtest(expr, settings=settings)
        if res and res.get("platform_id"):
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            m = _f(is_.get("margin"))
            m_bp = m * 10000 if m else 0
            return s > GATE_RISK_NEUT_S and f > GATE_RISK_NEUT_F and m_bp > GATE_RISK_NEUT_M_BP, {"s": s, "f": f, "m_bp": m_bp}
    except Exception as e:
        logger.warning("risk-neut: %s", e)
    return False, {}


def robust_overfit_test(api, expr, base_s):
    report = {"ok": True, "tests": []}
    probes = [("decay+2", {**base_s, "decay": min(int(base_s.get("decay", 3)) + 2, 10)}), ("uni_TOP2000", {**base_s, "universe": "TOP2000"}), ("sign_flip", base_s)]
    flip = expr[1:] if expr.startswith("-") else f"-{expr}"
    for name, settings in probes:
        try:
            e = flip if name == "sign_flip" else expr
            res = api.run_backtest(e, settings=settings)
            if not res or not res.get("platform_id"):
                report["ok"] = False
                continue
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            ok = abs(s) > 0.8 if name == "sign_flip" else (s > 0.9 and f > 0.5)
            report["tests"].append({"name": name, "sharpe": s, "fitness": f})
            if not ok:
                report["ok"] = False
            time.sleep(2)
        except Exception:
            report["ok"] = False
    return report


def set_alpha_props(api, pid, name, tags):
    try:
        r = api.session.patch(f"{API_BASE}/alphas/{pid}", json={"color": "GREEN", "name": name[:80], "tags": tags, "regular": {"description": name[:200]}}, timeout=60)
        logger.info("set_props %s -> %s (NO SUBMIT)", pid, r.status_code)
        return r.ok
    except Exception as e:
        logger.warning("set_props: %s", e)
        return False


def evaluate_is(api, label, pid, expr, settings, track=None):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m, ret = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0, _f(is_.get("returns")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_SHARPE: fails.append(f"S={s:.3f}")
    if f <= GATE_FITNESS: fails.append(f"F={f:.3f}")
    if tvr <= GATE_TVR_MIN or tvr >= GATE_TVR_MAX: fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_MARGIN_BP: fails.append(f"M={m_bp:.1f}bp")
    if ret <= GATE_RETURNS: fails.append(f"Ret={ret:.4f}")
    checks, plat_fails = {}, []
    sub_v, sub_lim = None, None
    if s > 1.4 or not fails:
        checks, plat_fails, ok = fetch_checks(api, pid)
        sub = checks.get("LOW_SUB_UNIVERSE_SHARPE") or {}
        sub_v, sub_lim = _f(sub.get("value")), _f(sub.get("limit"))
        if not fails:
            if not ok:
                return {"label": label, "pid": pid, "expr": expr, "settings": settings, "track": track, "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "status": "CHECK_PENDING", "fails": ["check_pending"], "sub_univ": sub_v, "sub_limit": sub_lim}
            for name in ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE"):
                c = checks.get(name) or {}
                if c.get("result") == "FAIL": fails.append(f"{name}_FAIL")
                val = _f(c.get("value"))
                if val is not None and val <= GATE_2Y: fails.append(f"{name}={val:.3f}<=1.6")
            if plat_fails: fails.extend([f"PF:{x}" for x in plat_fails])
    return {"label": label, "pid": pid, "expr": expr, "settings": settings, "track": track, "sharpe": s, "fitness": f, "tvr": tvr, "margin": m, "status": "PASS_CHEAP" if not fails else "FAIL", "fails": fails, "checks": checks, "failed_checks": plat_fails, "sub_univ": sub_v, "sub_limit": sub_lim}


def run_batch_multi(api, session, batch):
    by = {b["label"]: b for b in batch}
    raw = run_multi_batch(api, batch, session=session, max_wait=900, fallback_single=True)
    out = []
    for item in raw:
        b = by.get(item["label"])
        if not item.get("ok") or not item.get("pid") or not b:
            out.append({"label": item["label"], "status": "error", "track": (b or {}).get("track"), "fails": [item.get("error") or "no_pid"]})
        else:
            out.append(evaluate_is(api, item["label"], item["pid"], b["expr"], b["settings"], track=b.get("track")))
    return out


def run_tri_scan(cfg: ScanConfig) -> None:
    """共享主循环: 队列装填 → 批量 multi-sim → checkpoint → survivor 深检 (绝不提交)。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    ver = cfg.version.lower()
    env_prefix = cfg.version.upper()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_cooldown = float(os.environ.get(f"{env_prefix}_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
    max_batches = int(os.environ.get(f"{env_prefix}_MAX_BATCHES", str(cfg.max_batches_default)))
    progress_log_path = os.path.join(_ROOT, "results", f"{ver}_tri_progress_{ts}.log")
    ckpt_path = os.path.join(_ROOT, "results", cfg.ckpt_name)
    found_path = os.path.join(_ROOT, "results", f"scan_{ver}_tri_{ts}.json")

    explore_q = cfg.build_explore()
    seeds = cfg.build_seeds() or []
    improve_q = build_improve_variants(seeds, label_prefix="imp0") if seeds else []
    rescue_q = build_rescue_variants(seeds, label_prefix="rsc0") if seeds else []
    if cfg.explore_priority is not None:
        explore_q.sort(key=cfg.explore_priority)

    api = WqApiSimple()
    session = api.session
    ckpt = load_checkpoint(ckpt_path)
    if ckpt:
        ckpt_results = list(ckpt.get("results") or [])
        found_alphas = list(ckpt.get("found_alphas") or [])
        done_keys: Set[Tuple] = set()
        for r in ckpt_results:
            if r.get("expr") and r.get("settings"):
                s = r["settings"]
                done_keys.add((r["expr"], s.get("universe"), s.get("decay"), s.get("neutralization"), s.get("truncation")))
            elif r.get("label"):
                done_keys.add(("label", r["label"]))
    else:
        ckpt_results, found_alphas, done_keys = [], [], set()

    seen: Set[Tuple] = set(done_keys)
    # 过滤队列中已跑过的
    explore_q = [v for v in explore_q if variant_key(v) not in seen]
    improve_q = [v for v in improve_q if variant_key(v) not in seen]
    rescue_q = [v for v in rescue_q if variant_key(v) not in seen]

    logger.info(
        "%s TRI-TRACK %s | explore=%d improve=%d rescue=%d | slots %d/%d/%d | NO SUBMIT",
        env_prefix, cfg.dataset, len(explore_q), len(improve_q), len(rescue_q), SLOT_EXPLORE, SLOT_IMPROVE, SLOT_RESCUE,
    )
    logger.info("submit envelope: %s", envelope_summary())

    total_est = min(max_batches * BATCH_SIZE, len(explore_q) + len(improve_q) + len(rescue_q))
    pl = ProgressLogger(total_steps=max(total_est, 1), log_path=progress_log_path, task_name=cfg.task_name, emit_interval_sec=15.0, max_recent=8)
    pl.start(meta={"dataset": cfg.dataset, "tri_track": True, "no_submit": True, **cfg.progress_meta})
    pl.done = len(ckpt_results)

    survivors = []
    track_stats = {"explore": 0, "improve": 0, "rescue": 0}

    for bi in range(max_batches):
        if len(found_alphas) >= cfg.target_alphas:
            break
        if not (explore_q or improve_q or rescue_q):
            logger.info("queues empty, stop")
            break

        batch, taken = mix_batch(explore_q, improve_q, rescue_q, seen=seen, batch_size=BATCH_SIZE)
        if not batch:
            break
        for t, n in taken.items():
            track_stats[t] = track_stats.get(t, 0) + n

        t0 = time.monotonic()
        logger.info(
            "--- Batch %d/%d | slots E%d I%d R%d | q_left E%d I%d R%d ---",
            bi + 1, max_batches, taken["explore"], taken["improve"], taken["rescue"],
            len(explore_q), len(improve_q), len(rescue_q),
        )
        results = run_batch_multi(api, session, batch)
        wall = time.monotonic() - t0

        for r in sorted(results, key=lambda x: _f(x.get("sharpe")) or -999, reverse=True)[:4]:
            if r.get("sharpe") is not None:
                logger.info(
                    "  [%s] %s S=%.3f F=%.3f TVR=%.3f %s",
                    r.get("track"), r.get("label"), r.get("sharpe") or 0, r.get("fitness") or 0,
                    r.get("tvr") or 0, r.get("status"),
                )

        for r in results:
            pl.step(extra={
                "label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"),
                "sharpe": r.get("sharpe"), "track": r.get("track"), "fails": r.get("fails"),
                "batch_wall_sec": round(wall, 1),
            }, force_emit=True)
            parent = next((b for b in batch if b["label"] == r.get("label")), {})
            ckpt_results.append({
                "label": r.get("label"), "pid": r.get("pid"), "status": r.get("status"),
                "track": r.get("track") or parent.get("track"),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"), "tvr": r.get("tvr"),
                "margin": r.get("margin"), "fails": r.get("fails") or [],
                "expr": r.get("expr") or parent.get("expr"),
                "settings": r.get("settings") or parent.get("settings"),
                "style": parent.get("style"), "field": parent.get("field"),
                "parent_label": parent.get("parent_label"),
            })
            if r.get("status") == "PASS_CHEAP":
                survivors.append(r)
                logger.info("[%s/%s] cheap PASS", r.get("track"), r.get("label"))

        # 动态补充 improve/rescue
        refill_queues_from_results(results, explore_q, improve_q, rescue_q, seen=seen, top_k=5)
        save_checkpoint(
            ckpt_path, ckpt_results, found_alphas,
            queues_meta={"explore": len(explore_q), "improve": len(improve_q), "rescue": len(rescue_q), "track_stats": track_stats},
        )

        if (bi + 1) % 5 == 0:
            ss = [_f(x.get("sharpe")) for x in ckpt_results if _f(x.get("sharpe")) is not None]
            by_track = {}
            for x in ckpt_results:
                t = x.get("track") or "?"
                by_track.setdefault(t, []).append(_f(x.get("sharpe")) or 0)
            best_t = {t: (max(vs) if vs else None) for t, vs in by_track.items()}
            logger.info("DIVERSITY @%d best_S=%s by_track=%s stats=%s", bi + 1, max(ss) if ss else None, best_t, track_stats)

        if bi + 1 < max_batches and (explore_q or improve_q or rescue_q):
            after_batch_cooldown(batch_cooldown)

    for r in survivors:
        if len(found_alphas) >= cfg.target_alphas:
            break
        label, pid, expr, settings = r["label"], r["pid"], r["expr"], r["settings"]
        rn_ok, rn_stats = test_risk_neutralization(api, expr, settings)
        if not rn_ok:
            logger.info("[%s] risk-neut FAIL %s", label, rn_stats)
            continue
        robust = robust_overfit_test(api, expr, settings)
        if not robust.get("ok"):
            logger.info("[%s] robust FAIL", label)
            continue
        pc_val = wait_for_pc(api, pid)
        if pc_val is None or pc_val >= MAX_PROD_CORR:
            logger.warning("[%s] PC=%s 淘汰(不提交)", label, pc_val)
            continue
        pair_c = None
        if cfg.known_pid:
            corr_ok, pair_c = check_corr_vs_known(api, pid, cfg.known_pid, cfg.max_pair_corr)
            if not corr_ok:
                logger.warning("[%s] pair-corr vs %s = %s 淘汰", label, cfg.known_pid, pair_c)
                continue
        info = {
            "dataset": cfg.dataset, "style": cfg.style, "pid": pid, "label": label,
            "expr": expr, "sharpe": r["sharpe"], "fitness": r["fitness"], "tvr": r["tvr"],
            "margin": r["margin"], "prod_corr": pc_val, "risk_neut": rn_stats, "robust": robust,
            "settings": settings, "track": r.get("track"), "submitted": False,
        }
        if cfg.known_pid:
            info["pair_corr_vs"] = {cfg.known_pid: pair_c}
        set_alpha_props(api, pid, f"{ver}_{label}", [ver, cfg.dataset, "USA_D1", "READY_MANUAL", "NO_SUBMIT", f"track_{r.get('track')}"])
        found_alphas.append(info)
        append_ready({**info, "margin_bp": (r["margin"] or 0) * 10000, "tags": [ver, cfg.dataset, "USA_D1", "READY_MANUAL"]})
        logger.info("*** FOUND %s S=%.3f PC=%.4f track=%s (NO SUBMIT) ***", pid, r["sharpe"], pc_val, r.get("track"))
        save_checkpoint(ckpt_path, ckpt_results, found_alphas)

    with open(found_path, "w", encoding="utf-8") as f:
        json.dump(found_alphas, f, ensure_ascii=False, indent=2)
    logger.info("Done found=%d track_stats=%s (never submitted)", len(found_alphas), track_stats)
    pl.finish(summary={"found": len(found_alphas), "track_stats": track_stats, "no_submit": True})
