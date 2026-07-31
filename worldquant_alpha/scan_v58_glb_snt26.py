#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V58: GLB/D1 sentiment26 (网络域名流量/关注度排名) 挖掘.

前序: dl_riskfree_returns v57a+b 两轮 76 变体结案 — 8 个深度候选全部倒在 PC 0.80-0.84
同带 (冷门字段 alphas 14-16 与热门 307-915 无差), 拥挤在 CNN 模型信号层面, 换字段无解.
选型依据: GLB 17 字段 cov=1.0 全 VECTOR; 与价格正交(网络流量域) — PC 去拥挤优先;
USA tri 实测 bestS=-1.44 (top10pctranking 系反向, 骨架 gz+ts_zscore(189)).

字段结构: snt26_top{10/25/50/75}pctranking(avg)_* (排名分位统计) + relpopularity/totaldomains
(流量热度); VECTOR -> vec_avg 展开. 语义: ranking 数值大=排名差 -> 反向取负;
relpopularity/domains 高=关注度高 -> 正号试探 (tri 未覆盖, 双向探针).

用户硬约束:
- REGULAR, delay=1, maxTrade=OFF; 探索不同 universe (MINVOL1M / TOPDIV3000)
- IS: Sharpe>1.58, Fitness>1, 2Y-Sharpe>1.6, Margin>10bp, 5%<TVR<30%
- risk-neut(MARKET): Sharpe>1, Fitness>0.7, Margin>10bp
- 操作符数 <6; 单数据集 1-2 字段; 禁 trade_when/add()/multiply() (用 +,* 运算符也避免; 组合仅用减号 spread 形式)
- PROD_CORR 必须已出且 <0.7 才算候选 (<0.4 目标彼此独立); 绝不提交 (手动提交)
- multi-sim 7 车道流水线; 提交经 submit_gate 全局串行错峰 ≥32s; 每 10 批做多样性评估
- 找到即: robust+过拟合测试 -> PATCH 属性 (GREEN/tags) -> 写 manual_submit_ready.json
"""
from __future__ import annotations

import json
import logging
import os
import queue as _queue
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))

# 多车道连发时提交间隔必须 ≥ 令牌补充速率(≈1/30s), 否则耗桶 429 (实测 18s 不收敛)
os.environ.setdefault("BRAIN_SUBMIT_INTERVAL", "32")

LOG_PATH = os.path.join(_HERE, "results", "v58_glb_snt26.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("v58")

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, envelope_summary, run_multi_batch, chunked
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
N_LANES = int(os.environ.get("V53_LANES", "7"))  # 用户指示: 8 个 lane 先只开 7 个
COOLDOWN = float(os.environ.get("V53_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
CKPT = os.path.join(_HERE, "results", "v58_glb_snt26_checkpoint.json")
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
DIVERSITY = os.path.join(_HERE, "results", "v58_diversity_report.jsonl")
DATASET = "sentiment26"

# ---------------- 闸门 ----------------
GATE_S, GATE_F, GATE_M_BP = 1.58, 1.00, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
GATE_RET = 0.0   # 用户 IS 门槛无 Ret 项; F>1 已隐含 Ret≥4%
GATE_2Y_S = 1.6
RN_S, RN_F, RN_M_BP = 1.0, 0.7, 10.0
MAX_PC = 0.70          # 候选红线 (报告用; <0.4 才计入互独立目标)
TARGET_PC = 0.40
PC_WAIT_SEC = 3600
TARGET_FOUND = 10       # 全局目标（本数据集能出几个算几个）


def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def S(uni: str, decay: int, neut: str, trunc: float) -> Dict[str, Any]:
    return {
        "instrumentType": "EQUITY", "region": "GLB", "universe": uni, "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc,
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
        "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
    }


# ---------------- 模板族 v58a: 首轮—USA tri 骨架移植 + v57 验证的平滑骨架 ----------------
# USA tri 实测: -rank(group_zscore(ts_zscore(ts_backfill(vec_avg(f),66),189),industry)) S=-1.44
#   但 TVR 21-40% 贴线/超标; v57 教训: 长窗 zscore 在 GLB 换手爆炸,
#   唯一 M 达标骨架 rank(ts_mean(ts_backfill(f,22),5)) (TVR 11-14%).
# VECTOR 字段 -> vec_avg 展开 (4-5 ops 合规).
# 语义: ranking 数值大=排名差=关注度低 -> 负号(tri 验证方向);
#   relpopularity/totaldomains 高=热度高 -> 双向探针(tri 未覆盖).
STYLES: Dict[str, List[Tuple[str, str]]] = {
    # A) tri 验证骨架 (5 ops): 反向 ranking 系
    "gz": [
        ("gzN_t10r", "-rank(group_zscore(ts_zscore(ts_backfill(vec_avg(snt26_top10pctranking_29), 66), 189), industry))"),
        ("gzN_t10ra", "-rank(group_zscore(ts_zscore(ts_backfill(vec_avg(snt26_top10pctrankingavg_38), 66), 189), industry))"),
        ("gzN_t25ra", "-rank(group_zscore(ts_zscore(ts_backfill(vec_avg(snt26_top25pctrankingavg_34), 66), 189), industry))"),
        ("gzN_avgr", "-rank(group_zscore(ts_zscore(ts_backfill(vec_avg(snt26_avgranking_40), 66), 189), industry))"),
    ],
    # B) v57 验证 M 达标平滑骨架 (4 ops): ranking 系反向
    "sm": [
        ("smN_t10r", "-rank(ts_mean(ts_backfill(vec_avg(snt26_top10pctranking_29), 22), 5))"),
        ("smN_t10ra", "-rank(ts_mean(ts_backfill(vec_avg(snt26_top10pctrankingavg_38), 22), 5))"),
        ("smN_t25r", "-rank(ts_mean(ts_backfill(vec_avg(snt26_top25pctranking_41), 22), 5))"),
        ("smN_t25ra", "-rank(ts_mean(ts_backfill(vec_avg(snt26_top25pctrankingavg_34), 22), 5))"),
        ("smN_topr", "-rank(ts_mean(ts_backfill(vec_avg(snt26_topranking_33), 22), 5))"),
        ("smN_avgr", "-rank(ts_mean(ts_backfill(vec_avg(snt26_avgranking_40), 22), 5))"),
        ("smN_t50ra", "-rank(ts_mean(ts_backfill(vec_avg(snt26_top50pctrankingavg_37), 22), 5))"),
        ("smN_t75ra", "-rank(ts_mean(ts_backfill(vec_avg(snt26_top75pctrankingavg_28), 22), 5))"),
    ],
    # C) 热度/形态字段双向探针 (tri 未覆盖, 正反各试)
    "pop": [
        ("popP_rp1", "rank(ts_mean(ts_backfill(vec_avg(snt26_relpopularity1_35), 22), 5))"),
        ("popN_rp1", "-rank(ts_mean(ts_backfill(vec_avg(snt26_relpopularity1_35), 22), 5))"),
        ("popP_rp08", "rank(ts_mean(ts_backfill(vec_avg(snt26_relpopularity08_43), 22), 5))"),
        ("popP_tdom", "rank(ts_mean(ts_backfill(vec_avg(snt26_totaldomains_31), 22), 5))"),
        ("popN_tdom", "-rank(ts_mean(ts_backfill(vec_avg(snt26_totaldomains_31), 22), 5))"),
        ("popP_cdom", "rank(ts_mean(ts_backfill(vec_avg(snt26_totalcountrydomains_36), 22), 5))"),
        ("popP_skew", "rank(ts_mean(ts_backfill(vec_avg(snt26_skewness_39), 22), 5))"),
        ("popN_kurt", "-rank(ts_mean(ts_backfill(vec_avg(snt26_kurtosis_32), 22), 5))"),
    ],
    # D) v58b: 关注度变化量信号 — v58a level 信号天花板 S=0.88 证伪,
    #   改挖 ts_delta 动量/反转 (经典 web-traffic 结构, tri 未覆盖, 双向探针).
    #   ranking 数值下降=关注度飙升: 正号=追势, 负号=contrarian.
    "chg": [
        ("chN_d5_avgr", "-rank(ts_delta(vec_avg(snt26_avgranking_40), 5))"),
        ("chP_d5_avgr", "rank(ts_delta(vec_avg(snt26_avgranking_40), 5))"),
        ("chN_d22_avgr", "-rank(ts_mean(ts_delta(vec_avg(snt26_avgranking_40), 22), 5))"),
        ("chP_d22_avgr", "rank(ts_mean(ts_delta(vec_avg(snt26_avgranking_40), 22), 5))"),
        ("chN_d22_t10ra", "-rank(ts_mean(ts_delta(vec_avg(snt26_top10pctrankingavg_38), 22), 5))"),
        ("chP_d22_t10ra", "rank(ts_mean(ts_delta(vec_avg(snt26_top10pctrankingavg_38), 22), 5))"),
        ("chN_d22_rp1", "-rank(ts_mean(ts_delta(vec_avg(snt26_relpopularity1_35), 22), 5))"),
        ("chP_d22_rp1", "rank(ts_mean(ts_delta(vec_avg(snt26_relpopularity1_35), 22), 5))"),
        ("chN_d22_tdom", "-rank(ts_mean(ts_delta(vec_avg(snt26_totaldomains_31), 22), 5))"),
        ("chP_d22_tdom", "rank(ts_mean(ts_delta(vec_avg(snt26_totaldomains_31), 22), 5))"),
        ("zN_rp1_66", "-rank(ts_zscore(vec_avg(snt26_relpopularity1_35), 66))"),
        ("zN_avgr_66", "-rank(ts_zscore(vec_avg(snt26_avgranking_40), 66))"),
    ],
    # E) v58b: gz 骨架大 decay 补强 — tri USA 最优 d8 (TVR 21.5%), v58a 只跑了 d0/d3
    #   (d3 S=0.88 TVR=37%); decay 8/16 压 TVR 试探 (见 STYLE_OVERRIDES).
    "gzd": [
        ("gzdN_t10ra", "-rank(group_zscore(ts_zscore(ts_backfill(vec_avg(snt26_top10pctrankingavg_38), 66), 189), industry))"),
        ("gzdN_t10r", "-rank(group_zscore(ts_zscore(ts_backfill(vec_avg(snt26_top10pctranking_29), 66), 189), industry))"),
        ("gzdN_t25ra", "-rank(group_zscore(ts_zscore(ts_backfill(vec_avg(snt26_top25pctrankingavg_34), 66), 189), industry))"),
    ],
}

UNIVERSES = ["MINVOL1M"]
DECAYS = [0, 3]
# v57 教训: INDU neut 被 PF:LOW_GLB_EMEA_SHARPE 系统性卡死, GLB 首轮只跑 COUN
NEUTS = ["COUNTRY"]
TRUNCS = [0.02]
MAX_VARIANTS = int(os.environ.get("V53_MAX_VARIANTS", "560"))

# 每风格覆盖 (universe/decay/neut), 未列出的风格沿用全局默认
STYLE_OVERRIDES: Dict[str, Dict[str, list]] = {
    # v58b: gz 骨架只补大 decay (小 decay 已在 v58a 评估)
    "gzd": {"decays": [8, 16]},
}


def build_variants() -> List[Dict[str, Any]]:
    out, seen = [], set()
    for style, exprs in STYLES.items():
        ov = STYLE_OVERRIDES.get(style, {})
        for ei, (tag, expr) in enumerate(exprs):
            for uni in ov.get("universes", UNIVERSES):
                for decay in ov.get("decays", DECAYS):
                    for neut in ov.get("neuts", NEUTS):
                        for trunc in ov.get("truncs", TRUNCS):
                            key = (expr, uni, decay, neut, trunc)
                            if key in seen:
                                continue
                            seen.add(key)
                            out.append({
                                "label": f"{tag}_{uni[:4]}_d{decay}_{neut[:4]}_t{int(trunc*100)}",
                                "style": style,
                                "expr": expr,
                                "settings": S(uni, decay, neut, trunc),
                            })
    # 探索优先级: 先 MINVOL1M+COUNTRY (GLB 去国别噪声预期最优)
    def prio(v):
        s = v["settings"]
        sc = 0
        if s["universe"] == "MINVOL1M": sc += 4
        if s["neutralization"] == "COUNTRY": sc += 3
        if s["decay"] == 0: sc += 1
        return -sc
    out.sort(key=prio)
    # 轮转各 style, 避免连续 8 条同风格挤占批次
    by_style: Dict[str, List] = {}
    for v in out:
        by_style.setdefault(v["style"], []).append(v)
    mixed, idx = [], 0
    while any(by_style.values()):
        for st in list(STYLES.keys()):
            lst = by_style.get(st) or []
            if lst:
                mixed.append(lst.pop(0))
        idx += 1
    mixed = mixed[:MAX_VARIANTS]
    logger.info("built %d variants (%d styles, cap=%d)", len(mixed), len(STYLES), MAX_VARIANTS)
    return mixed


# ---------------- 评估 ----------------

def fetch_checks(api, pid, retries=5):
    for _ in range(retries):
        try:
            r = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if r.status_code == 200 and r.text.strip():
                checks = (r.json().get("is") or {}).get("checks") or []
                return {c.get("name", ""): c for c in checks}
            time.sleep(4)
        except Exception:
            time.sleep(8)
    return {}


def eval_one(api, label, pid, expr, settings, style):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m, ret = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0, _f(is_.get("returns")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_S: fails.append(f"S={s:.3f}")
    if f <= GATE_F: fails.append(f"F={f:.3f}")
    if tvr <= GATE_TVR_LO or tvr >= GATE_TVR_HI: fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_M_BP: fails.append(f"M={m_bp:.1f}bp")
    if ret <= GATE_RET: fails.append(f"Ret={ret:.4f}")
    status = "PASS_CHEAP" if not fails else "FAIL"
    if s > 1.45 and m_bp > 8:  # 近关也拉平台 check
        checks = fetch_checks(api, pid)
        pfails = [n for n, c in checks.items() if c.get("result") == "FAIL" and n != "PROD_CORRELATION"]
        if pfails:
            fails.extend([f"PF:{x}" for x in pfails])
            status = "FAIL"
        c2y = checks.get("LOW_2Y_SHARPE")
        if c2y is not None:
            v = _f(c2y.get("value"))
            if c2y.get("result") == "FAIL" or (v is not None and v <= GATE_2Y_S):
                fails.append(f"2Y={v}")
                status = "FAIL"
    return {
        "label": label, "pid": pid, "expr": expr, "settings": settings, "style": style,
        "sharpe": s, "fitness": f, "tvr": tvr, "margin_bp": m_bp, "returns": ret,
        "status": status, "fails": fails,
    }


def test_risk_neut(api, expr, base_s):
    try:
        res = api.run_backtest(expr, settings={**base_s, "neutralization": "MARKET"})
        if res and res.get("platform_id"):
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            m_bp = (_f(is_.get("margin")) or 0) * 10000
            ok = s > RN_S and f > RN_F and m_bp > RN_M_BP
            return ok, {"s": s, "f": f, "m_bp": m_bp}
    except Exception as e:
        logger.warning("risk-neut: %s", e)
    return False, {}


def robust_overfit_test(api, expr, base_s):
    """严格过拟合探针: 换 universe / decay 扰动 / 反号破坏性."""
    report = {"ok": True, "tests": []}
    alt_uni = "TOPDIV3000" if base_s["universe"] == "MINVOL1M" else "MINVOL1M"
    probes = [
        ("alt_universe", expr, {**base_s, "universe": alt_uni}, lambda s, f: s > 1.0 and f > 0.5),
        ("decay+2", expr, {**base_s, "decay": min(int(base_s.get("decay", 4)) + 2, 12)}, lambda s, f: s > 1.2),
        ("decay-1", expr, {**base_s, "decay": max(int(base_s.get("decay", 4)) - 1, 0)}, lambda s, f: s > 1.2),
        ("sign_flip", expr[1:] if expr.startswith("-") else f"-{expr}", base_s, lambda s, f: s < -0.8),
    ]
    for name, e, st, judge in probes:
        try:
            res = api.run_backtest(e, settings=st)
            if not res or not res.get("platform_id"):
                report["tests"].append({"name": name, "error": "no_pid"})
                report["ok"] = False
                continue
            det = api.get_alpha_details(res["platform_id"])
            is_ = det.get("is") or {}
            s, f = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
            ok = judge(s, f)
            report["tests"].append({"name": name, "sharpe": s, "fitness": f, "ok": ok})
            if not ok:
                report["ok"] = False
        except Exception as ex:
            report["tests"].append({"name": name, "error": str(ex)[:60]})
            report["ok"] = False
    return report


def wait_pc(api, pid, max_wait=PC_WAIT_SEC):
    waited = 0
    while waited < max_wait:
        checks = fetch_checks(api, pid, retries=1)
        pc = checks.get("PROD_CORRELATION")
        if pc and pc.get("result") in ("PASS", "FAIL", "WARNING"):
            return _f(pc.get("value"))
        time.sleep(30)
        waited += 30
    return None


def set_props(api, pid, name, tags, desc):
    try:
        r = api.session.patch(
            f"{API_BASE}/alphas/{pid}",
            json={"color": "GREEN", "name": name[:80], "tags": tags,
                  "regular": {"description": desc[:200]}},
            timeout=60,
        )
        logger.info("set_props %s -> %s (NO SUBMIT)", pid, r.status_code)
        return r.ok
    except Exception as e:
        logger.warning("set_props: %s", e)
        return False


def append_ready(info):
    ready = json.load(open(READY, encoding="utf-8")) if os.path.exists(READY) else {"goal": 10, "alphas": []}
    info["n"] = len(ready.get("alphas", [])) + 1
    ready.setdefault("alphas", []).append(info)
    with open(READY, "w", encoding="utf-8") as f:
        json.dump(ready, f, ensure_ascii=False, indent=2)
    logger.info("manual_submit_ready: %d 条", len(ready["alphas"]))


# ---------------- 多样性评估 (每 10 批) ----------------
import re as _re

def diversity_report(results: List[Dict], batch_no: int):
    ops_all, fields_all, skels, styles = set(), set(), {}, {}
    total_ops_used = set()
    for r in results:
        expr = r.get("expr") or ""
        ops = set(_re.findall(r"([a-z_]+)\(", expr))
        total_ops_used |= ops
        fields = set(_re.findall(r"(?:ts_backfill\()([a-z0-9_]+)", expr))
        fields_all |= fields
        skel = _re.sub(r"[a-z0-9_]+(?=[,)])", "X", expr)
        skel = _re.sub(r"\d+", "N", skel)
        skels[skel] = skels.get(skel, 0) + 1
        st = r.get("style") or "?"
        styles[st] = styles.get(st, 0) + 1
    pass_styles = {r.get("style") for r in results if r.get("status") == "PASS_CHEAP"}
    rep = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "batch_no": batch_no,
        "n_backtests": len(results),
        "op_exploration": sorted(total_ops_used),
        "n_ops": len(total_ops_used),
        "n_fields_explored": len(fields_all),
        "fields": sorted(fields_all),
        "n_skeletons": len(skels),
        "style_counts": styles,
        "styles_with_pass": sorted(x for x in pass_styles if x),
        "note": "op<6/expr; 禁trade_when/add()/multiply(); 单数据集<=2字段",
    }
    with open(DIVERSITY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rep, ensure_ascii=False) + "\n")
    logger.info("[DIVERSITY] batch=%d ops=%d fields=%d skeletons=%d styles=%s",
                batch_no, rep["n_ops"], rep["n_fields_explored"], rep["n_skeletons"], styles)
    return rep


# ---------------- 主流程: 多车道流水线 ----------------
# 设计依据 (probe_concurrency_final_report_20260725_0255.md):
#   - 令牌桶只限 POST /simulations 的瞬时集中度 (C=7, refill≈1/30s), 不限同时在跑数
#   - submit_gate 文件锁将全部提交串行化 ≥32s → 瞬时提交并发恒=1 (安全区≤6)
#   - 各车道自提交→轮询→评估→再取下一批

_LOCK = threading.RLock()


def _save_ckpt(state):
    with _LOCK:
        with open(CKPT, "w", encoding="utf-8") as f:
            json.dump({"results": state["results"], "found": state["found"]}, f, ensure_ascii=False, indent=2)


def _lane_worker(lane_id: int, q: "_queue.Queue", state: Dict[str, Any], total_jobs: int, start_ts: float):
    time.sleep(lane_id * 5)  # 起步错峰, 避免多认证/提交同时拉起
    try:
        api = WqApiSimple()
    except Exception as e:
        logger.error("[lane%d] auth fail: %s", lane_id, e)
        return
    session = api.session
    while True:
        with _LOCK:
            if len(state["found"]) >= TARGET_FOUND:
                break
        try:
            batch = q.get_nowait()
        except _queue.Empty:
            break
        logger.info("[lane%d] batch start: %s", lane_id, [b["label"] for b in batch][:3])
        raw = run_multi_batch(api, batch, session=session, max_wait=2400, fallback_single=True)
        by = {b["label"]: b for b in batch}
        for item in raw:
            b = by.get(item["label"])
            if item.get("error") in ("poll_timeout", "submit_failed"):
                logger.warning("[lane%d] %s %s -> 留待重试", lane_id, item["label"], item.get("error"))
                continue
            if not item.get("ok") or not item.get("pid") or not b:
                with _LOCK:
                    state["results"].append({"label": item["label"], "status": "error", "style": (b or {}).get("style")})
                continue
            r = eval_one(api, item["label"], item["pid"], b["expr"], b["settings"], b["style"])
            with _LOCK:
                state["results"].append(r)
            logger.info("  [lane%d] %s S=%.2f F=%.2f TVR=%.3f M=%.1fbp %s %s",
                        lane_id, r["label"], r["sharpe"], r["fitness"], r["tvr"], r["margin_bp"],
                        r["status"], r["fails"][:2])
            if r["status"] != "PASS_CHEAP":
                continue
            # ---- 深检: risk-neut -> robust/overfit -> PC (单条探针也经 gate 匀速) ----
            rn_ok, rn = test_risk_neut(api, r["expr"], r["settings"])
            if not rn_ok:
                logger.info("  [lane%d] risk-neut FAIL %s", lane_id, rn)
                continue
            rob = robust_overfit_test(api, r["expr"], r["settings"])
            if not rob["ok"]:
                logger.info("  [lane%d] robust/overfit FAIL %s", lane_id,
                            [t.get("name") for t in rob["tests"] if not t.get("ok", False)])
                continue
            pc = wait_pc(api, r["pid"])
            if pc is None:
                logger.warning("  [lane%d] PC 未出 -> 不符合候选, 跳过 (不提交)", lane_id)
                continue
            if pc >= MAX_PC:
                logger.warning("  [lane%d] PC=%.4f >= 0.70 淘汰", lane_id, pc)
                continue
            info = {
                "dataset": DATASET, "style": r["style"], "pid": r["pid"], "label": r["label"],
                "expr": r["expr"], "sharpe": r["sharpe"], "fitness": r["fitness"],
                "tvr": r["tvr"], "margin_bp": r["margin_bp"], "prod_corr": pc,
                "risk_neut": rn, "robust": rob, "settings": r["settings"],
                "region": "GLB", "submitted": False,
                "tags": ["v56", DATASET, "GLB_D1", "READY_MANUAL", "NO_SUBMIT"],
            }
            set_props(api, r["pid"], f"v56_{r['label']}", info["tags"],
                      f"GLB D1 unlit pyramid {DATASET}. {r['style']}. NO AUTO SUBMIT.")
            with _LOCK:
                state["found"].append(info)
                append_ready(info)
            logger.info("*** FOUND #%d %s S=%.2f M=%.1fbp PC=%.4f style=%s (NO SUBMIT) ***",
                        len(state["found"]), r["pid"], r["sharpe"], r["margin_bp"], pc, r["style"])
        with _LOCK:
            state["batch_no"] += 1
            bn = state["batch_no"]
            _save_ckpt(state)
            if bn % 10 == 0:
                diversity_report(state["results"], bn)
            el = time.time() - start_ts
            logger.info("progress %d/%d (%.1f%%) elapsed=%.0fs found=%d lanes_active=%d",
                        len(state["results"]), total_jobs,
                        len(state["results"]) / total_jobs * 100 if total_jobs else 0,
                        el, len(state["found"]), threading.active_count() - 1)
    logger.info("[lane%d] exit", lane_id)


def main():
    variants = build_variants()
    logger.info("V58 GLB sentiment26 | %d variants | lanes=%d | %s",
                len(variants), N_LANES, envelope_summary())
    results, found = [], []
    if os.path.exists(CKPT):
        try:
            ck = json.load(open(CKPT, encoding="utf-8"))
            results = list(ck.get("results") or [])
            found = list(ck.get("found") or [])
            done = {r.get("label") for r in results}
            variants = [v for v in variants if v["label"] not in done]
            logger.info("resume: %d done, %d left, %d found", len(results), len(variants), len(found))
        except Exception:
            pass

    start_ts = time.time()
    total_jobs = len(variants) + len(results)
    state = {"results": results, "found": found, "batch_no": 0}
    q: "_queue.Queue" = _queue.Queue()
    for b in chunked(variants, BATCH_SIZE):
        q.put(b)

    lanes = [threading.Thread(target=_lane_worker, args=(i, q, state, total_jobs, start_ts), daemon=True)
             for i in range(N_LANES)]
    for t in lanes:
        t.start()
    for t in lanes:
        t.join()

    diversity_report(state["results"], -1)
    ok = [r for r in state["results"] if r.get("sharpe")]
    ok.sort(key=lambda x: -(x.get("sharpe") or 0))
    logger.info("DONE found=%d; top: %s", len(state["found"]), [
        (x.get("label"), round(x.get("sharpe") or 0, 2), round(x.get("margin_bp") or 0, 1)) for x in ok[:8]
    ])


if __name__ == "__main__":
    main()
