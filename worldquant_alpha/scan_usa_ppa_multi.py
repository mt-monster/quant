#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""USA PPA Alpha Mining — 手册驱动版
目标: 找到 10 个未提交 alpha (不同数据集/风格/相关<0.4)
约束: region=USA, D1, REGULAR, no trade_when/add/multiply, ops<6, 1-2 fields
回测: multi_create_simulate BATCH=8
每 10 轮: 多样性评估
"""

import json, os, time, sys, threading, itertools, re, random, _queue
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("usa_ppa")

# ===== Config =====
DATASET = "fundamental6"
REGION = "USA"
INSTRUMENT = "EQUITY"
DELAY = 1
MAX_WEIGHT = None  # max_trade OFF (None = no truncation)

# Universe 探索序列
UNIVERSE_SEQ = ["TOP3000", "TOP2000", "TOP1000"]

# 中性化选择
NEUT_CHOICES = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "COUNTRY", "NONE"]

# 衰减序列
DECAY_SEQ = [3, 4, 5, 6, 8, 10, 12, 16, 20]

# 回测窗口
TEST_PERIOD = "P6Y"

# 并发
BATCH_SIZE = 8
N_LANES = int(os.environ.get("USA_LANES", "4"))

# 闸门
GATE_S, GATE_F, GATE_M_BP = 1.58, 1.00, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
GATE_RET = 0.05
GATE_2Y_S = 1.60
GATE_RISK_S, GATE_RISK_F, GATE_RISK_M = 1.00, 0.70, 10.0

# 提交闸
GATE_SC_TH = 0.50      # SELF_CORRELATION 阈值
GATE_PC_TH = 0.70      # PROD_CORRELATION 红线

# 操作符限制: <6
MAX_OPS = 5

# 多样性评估间隔
DIVERSITY_INTERVAL = 10

# 产出目录
ROOT = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(ROOT, "results")
CKPT = os.path.join(RES, f"usa_{DATASET}_checkpoint.json")
LOG = os.path.join(RES, f"usa_{DATASET}.log")
os.makedirs(RES, exist_ok=True)

# 论坛监控
FORUM_CHECK_EVERY = 50  # 每 50 批检查一次论坛

# ===== Imports =====
sys.path.insert(0, ROOT)
from wd_lib_wrapper import WqApiSimple
from multi_sim import run_multi_batch, chunked, API_BASE

# ===== API =====
api = WqApiSimple()

# ===== Signal Templates (USA PPA proven patterns) =====
TEMPLATES = [
    # 1. 反转价差 (最佳: S=2.23+)
    "rank(ts_zscore(subtract(ts_mean(ts_backfill({F1}, 66), 22), ts_mean(ts_backfill({F2}, 66), 22), filter=true), 189))",
    # 2. 纯字段 rank
    "rank(ts_zscore(ts_backfill({F1}, 66), 189))",
    # 3. 减均值残差
    "rank(ts_zscore(subtract(ts_backfill({F1}, 66), ts_mean(ts_backfill({F2}, 66), 22)), 252))",
    # 4. 比例
    "rank(ts_zscore(ts_backfill({F1}, 66), 189)) - rank(ts_zscore(ts_backfill({F2}, 66), 189))",
    # 5. 动量-反转混合
    "rank(ts_zscore(ts_backfill({F1}, 252), 42)) - rank(ts_zscore(ts_backfill({F1}, 22), 42))",
    # 6. 波动率调整
    "rank(ts_zscore(ts_backfill({F1}, 66), 189) / (ts_std(ts_backfill({F1}, 66), 66) + 1e-8))",
    # 7. 双窗口交叉
    "rank(ts_zscore(subtract(ts_mean(ts_backfill({F1}, 66), 10), ts_mean(ts_backfill({F1}, 66), 30)), 189))",
]

# ===== Helper =====
def _f(v):
    try: return float(v)
    except: return None

def count_ops(expr):
    """数操作符个数"""
    return len(re.findall(r'(rank|ts_zscore|ts_backfill|ts_mean|ts_std|subtract|divide|log|abs|sign|sqrt|power)', expr))

def build_variants(fields):
    """从字段列表生成变体"""
    variants = []
    for dec in DECAY_SEQ:
        for neut in ["SUBINDUSTRY", "INDUSTRY", "SECTOR"]:
            for univ in UNIVERSE_SEQ[:2]:  # 先用 TOP3000/TOP2000
                for tidx, tmpl in enumerate(TEMPLATES):
                    if tidx == 0:
                        # 双字段模板
                        for f1, f2 in itertools.combinations(fields, 2):
                            f1_id = f1.get("id",""); f2_id = f2.get("id","")
                            expr = tmpl.format(F1=f1_id, F2=f2_id)
                            if count_ops(expr) > MAX_OPS: continue
                            label = f"t0_{f1_id[:8]}_{f2_id[:8]}_{univ[:4]}_d{dec}_{neut[:3]}"
                            variants.append({
                                "label": label, "expr": expr, "settings": {
                                    "instrumentType": INSTRUMENT, "region": REGION, "delay": DELAY,
                                    "universe": univ, "neutralization": neut, "decay": dec,
                                    "testPeriod": TEST_PERIOD,
                                }, "style": f"spread_{tidx}", "template": tidx,
                            })
                    elif tidx == 1:
                        # 单字段模板
                        for f in fields:
                            f_id = f.get("id","")
                            expr = tmpl.format(F1=f_id, F2="")
                            if count_ops(expr) > MAX_OPS: continue
                            label = f"t1_{f_id[:8]}_{univ[:4]}_d{dec}_{neut[:3]}"
                            variants.append({
                                "label": label, "expr": expr, "settings": {
                                    "instrumentType": INSTRUMENT, "region": REGION, "delay": DELAY,
                                    "universe": univ, "neutralization": neut, "decay": dec,
                                    "testPeriod": TEST_PERIOD,
                                }, "style": f"pure_{tidx}", "template": tidx,
                            })
                    elif tidx in (2,3,4,5,6):
                        # 双字段变体
                        for f1, f2 in itertools.combinations(fields, 2):
                            f1_id = f1.get("id",""); f2_id = f2.get("id","")
                            try:
                                expr = tmpl.format(F1=f1_id, F2=f2_id)
                            except KeyError:
                                expr = tmpl.format(F1=f1_id)
                            if count_ops(expr) > MAX_OPS: continue
                            label = f"t{tidx}_{f1_id[:8]}_{f2_id[:8]}_{univ[:4]}_d{dec}_{neut[:3]}"
                            variants.append({
                                "label": label, "expr": expr, "settings": {
                                    "instrumentType": INSTRUMENT, "region": REGION, "delay": DELAY,
                                    "universe": univ, "neutralization": neut, "decay": dec,
                                    "testPeriod": TEST_PERIOD,
                                }, "style": f"var_{tidx}", "template": tidx,
                            })
    logger.info("Built %d variants from %d fields", len(variants), len(fields))
    return variants

# ===== Eval One =====
def eval_one(pid, label, expr, settings, style):
    """评估单条 alpha 的 IS 指标"""
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s, f_ = _f(is_.get("sharpe")) or 0, _f(is_.get("fitness")) or 0
    tvr, m, ret = _f(is_.get("turnover")) or 0, _f(is_.get("margin")) or 0, _f(is_.get("returns")) or 0
    m_bp = m * 10000
    fails = []
    if s <= GATE_S: fails.append(f"S={s:.3f}")
    if f_ <= GATE_F: fails.append(f"F={f_:.3f}")
    if tvr <= GATE_TVR_LO or tvr >= GATE_TVR_HI: fails.append(f"TVR={tvr:.4f}")
    if m_bp <= GATE_M_BP: fails.append(f"M={m_bp:.1f}bp")
    if ret <= GATE_RET: fails.append(f"Ret={ret:.4f}")
    status = "PASS_CHEAP" if not fails else "FAIL"
    # 近关拉平台 check
    if s > 1.25 and m_bp > 8:
        try:
            chk = api.get_alpha_check(pid)
            is_checks = chk.get("is",{}).get("checks",[])
            for c in is_checks:
                if c.get("result") == "FAIL" and c.get("name") not in ("REGULAR_DESCRIPTION_LENGTH","REGULAR_DESCRIPTION_FORMAT","PROD_CORRELATION","SELF_CORRELATION"):
                    fails.append(f"PF:{c['name']}")
                    status = "FAIL"
            c2y = next((c for c in is_checks if c.get("name") == "LOW_2Y_SHARPE"), None)
            if c2y:
                vy = _f(c2y.get("value"))
                if c2y.get("result") == "FAIL" or (vy is not None and vy <= GATE_2Y_S):
                    fails.append(f"2Y={vy}")
                    if status == "PASS_CHEAP": status = "FAIL"
        except Exception as e:
            logger.debug("  check error: %s", e)
    return {
        "pid": pid, "label": label, "expr": expr, "settings": settings, "style": style,
        "sharpe": s, "fitness": f_, "tvr": tvr, "margin_bp": m_bp, "returns": ret,
        "status": status, "fails": fails,
    }

# ===== Risk-neut test =====
def test_risk_neut(expr, base_settings):
    """MARKET 中性化回测"""
    try:
        s2 = dict(base_settings); s2["neutralization"] = "MARKET"
        bt = api.run_backtest(expr, settings=s2)
        new_pid = bt.get("platform_id") if isinstance(bt, dict) else None
        if not new_pid: return False, {}
        det = api.get_alpha_details(new_pid)
        is_ = det.get("is", {})
        ns = _f(is_.get("sharpe")) or 0
        nf = _f(is_.get("fitness")) or 0
        nm = (_f(is_.get("margin")) or 0) * 10000
        ok = ns > GATE_RISK_S and nf > GATE_RISK_F and nm > GATE_RISK_M
        return ok, {"rn_pid": new_pid, "rn_sharpe": ns, "rn_fitness": nf, "rn_margin_bp": nm, "rn_pass": ok}
    except Exception as e:
        return False, {"rn_error": str(e)}

# ===== Robustness test =====
def test_robust(expr, base_settings):
    """过拟合测试: 不同 testPeriod 的 Sharpe"""
    results = {}
    for tp in ["P4Y", "P5Y", "P6Y"]:
        try:
            s2 = dict(base_settings); s2["testPeriod"] = tp
            bt = api.run_backtest(expr, settings=s2)
            pid = bt.get("platform_id") if isinstance(bt, dict) else None
            if pid:
                det = api.get_alpha_details(pid)
                is_ = det.get("is", {})
                results[tp] = _f(is_.get("sharpe")) or 0
        except: pass
    if not results: return False, {}
    ss = list(results.values())
    avg_s = sum(ss) / len(ss) if ss else 0
    min_s = min(ss) if ss else 0
    # 稳健性: 最短窗口 S>1.25 且 衰减 < 50%
    rob_ok = min_s > 1.25 and (max(ss) - min_s) / max(ss) < 0.50 if ss else False
    return rob_ok, {"rob_periods": results, "rob_avg": avg_s, "rob_min": min_s, "rob_ok": rob_ok}

# ===== PC 等待 =====
def wait_pc(pid, max_wait=600):
    """等待 PROD_CORRELATION / SELF_CORRELATION"""
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            chk = api.get_alpha_check(pid)
            is_checks = chk.get("is",{}).get("checks",[])
            pc = next((c for c in is_checks if c.get("name")=="PROD_CORRELATION"), None)
            sc = next((c for c in is_checks if c.get("name")=="SELF_CORRELATION"), None)
            if pc is not None and sc is not None:
                pc_v = _f(pc.get("value")) or 1; sc_v = _f(sc.get("value")) or 1
                pc_ok = pc_v < GATE_PC_TH
                sc_ok = sc_v < GATE_SC_TH
                return pc_ok, sc_ok, {"prod_corr": pc_v, "self_corr": sc_v, "pc_ok": pc_ok, "sc_ok": sc_ok}
            time.sleep(30)
        except Exception as e:
            time.sleep(15)
    return False, False, {"pc_timeout": True}

# ===== Lane Worker =====
_lock = threading.RLock()

def _save_ckpt(state):
    tmp = CKPT + ".tmp"
    with _lock:
        json.dump({"results": state["results"], "found": state["found"], "total_variants": state["total_variants"],
                   "batch_no": state.get("batch_no",0), "fields": state.get("fields",[])},
                  open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, CKPT)

def _lane_worker(lane_id, q, state, total_jobs, start_ts):
    while True:
        try:
            batch = q.get(timeout=5)
        except _queue.Empty:
            return
        if not batch: return
        logger.info("[lane%d] batch start: %s", lane_id, [v["label"][:30] for v in batch[:3]])
        try:
            results = run_multi_batch(api, batch)
        except Exception as e:
            logger.error("[lane%d] batch error: %s", lane_id, e)
            continue
        for r in (results or []):
            pid = r.get("platform_id")
            if not pid: continue
            item = next((v for v in batch if v["label"] == r.get("label")), None)
            if not item: continue
            ev = eval_one(pid, item["label"], item["expr"], item["settings"], item["style"])
            with _lock:
                state["results"].append(ev)
                done = len(state["results"])
                et = int(time.time() - start_ts)
                active = sum(1 for t in threading.enumerate() if t.name.startswith("lane-"))
                logger.info("progress %d/%d (%.1f%%) elapsed=%ds found=%d lanes_active=%d",
                           done, total_jobs, done/total_jobs*100 if total_jobs else 0,
                           et, len(state["found"]), active)
            # PASS_CHEAP → 深检
            if ev["status"] == "PASS_CHEAP":
                rn_ok, rn_info = test_risk_neut(item["expr"], item["settings"])
                if not rn_ok:
                    logger.info("  [lane%d] risk-neut FAIL %s", lane_id, rn_info)
                    continue
                logger.info("  [lane%d] risk-neut PASS S=%.2f", lane_id, rn_info.get("rn_sharpe",0))
                # Robust
                rob_ok, rob_info = test_robust(item["expr"], item["settings"])
                if not rob_ok:
                    logger.info("  [lane%d] robust FAIL avg=%.2f", lane_id, rob_info.get("rob_avg",0))
                    continue
                logger.info("  [lane%d] robust PASS avg=%.2f", lane_id, rob_info.get("rob_avg",0))
                # PC wait
                pc_ok, sc_ok, pc_info = wait_pc(pid)
                if not pc_ok or not sc_ok:
                    logger.info("  [lane%d] PC/SC FAIL pc=%.3f sc=%.3f", lane_id,
                               pc_info.get("prod_corr",0), pc_info.get("self_corr",0))
                    continue
                logger.info("  [lane%d] ★★★ PC/SC PASS pc=%.3f sc=%.3f", lane_id,
                           pc_info.get("prod_corr",0), pc_info.get("self_corr",0))
                # 设置属性
                try:
                    from urllib.parse import urljoin
                    desc = (f"USA PPA: {item['label']}. Signal uses {DATASET} dataset, "
                            f"template={item['style']}, ops<6, 1-2 fields. "
                            f"Region={REGION}, D{DELAY}, {item['settings'].get('neutralization','')} neutralization. "
                            f"Sharpe={ev['sharpe']:.2f}, Fitness={ev['fitness']:.2f}, "
                            f"Turnover={ev['tvr']:.4f}, Margin={ev['margin_bp']:.1f}bp. "
                            f"Risk-neut S={rn_info.get('rn_sharpe',0):.2f}. "
                            f"Robust avg S={rob_info.get('rob_avg',0):.2f} across P4Y/P5Y/P6Y. "
                            f"Self-correlation={pc_info.get('self_corr',0):.4f}, "
                            f"Prod-correlation={pc_info.get('prod_corr',0):.4f}. "
                            f"DO NOT SUBMIT — manual review pending.")
                    api.session.patch(urljoin(API_BASE, f"alphas/{pid}"),
                                      json={"name": f"usa_{DATASET}_{item['label'][:20]}",
                                            "regular": {"description": desc},
                                            "color": "GREEN"})
                    logger.info("  [lane%d] properties set (NO SUBMIT)", lane_id)
                except Exception as e:
                    logger.warning("  [lane%d] set properties error: %s", lane_id, e)
                with _lock:
                    state["found"].append({
                        "pid": pid, "label": item["label"], "sharpe": ev["sharpe"],
                        "rn_info": rn_info, "rob_info": rob_info, "pc_info": pc_info,
                    })
                    _save_ckpt(state)
                    logger.info("  ★ READY for manual submit: %s S=%.2f", pid, ev["sharpe"])
        _save_ckpt(state)

# ===== Diversity Report =====
def diversity_report(results, batch_no):
    """每 10 轮多样性评估"""
    if not results: return
    ss = [float(r.get("sharpe", 0) or 0) for r in results if r.get("sharpe") is not None]
    styles = [r.get("style", "?") for r in results]
    templates = [r.get("template", "?") for r in results]
    fields_used = set()
    ops_counted = {}
    for r in results:
        expr = r.get("expr", "")
        ops_counted[len(re.findall(r'(rank|ts_zscore|ts_backfill|ts_mean|ts_std|subtract|divide|log|abs|sign|sqrt|power)', expr))] = ops_counted.get(len(re.findall(r'(rank|ts_zscore|ts_backfill|ts_mean|ts_std|subtract|divide|log|abs|sign|sqrt|power)', expr)), 0) + 1
        for m in re.finditer(r'ts_backfill\((\w+)', expr):
            fields_used.add(m.group(1))
    statuses = [r.get("status", "?") for r in results]
    pass_cheap = statuses.count("PASS_CHEAP")
    logger.info("=" * 60)
    logger.info("[DIVERSITY] batch=%d total=%d PASS_CHEAP=%d", batch_no, len(results), pass_cheap)
    logger.info("  S distribution: max=%.2f p95=%.2f p50=%.2f min=%.2f",
                max(ss) if ss else 0,
                sorted(ss, reverse=True)[int(len(ss)*0.05)] if ss else 0,
                sorted(ss)[len(ss)//2] if ss else 0,
                min(ss) if ss else 0)
    logger.info("  Styles: %s", {s: styles.count(s) for s in set(styles)})
    logger.info("  Templates: %s", {t: templates.count(t) for t in set(templates)})
    logger.info("  Fields explored: %d (%s)", len(fields_used), ", ".join(sorted(list(fields_used))[:10]))
    logger.info("  Operators used: %s", ops_counted)
    logger.info("=" * 60)
    return {
        "batch": batch_no, "total": len(results), "pass_cheap": pass_cheap,
        "sharpe_max": max(ss) if ss else 0,
        "styles": {s: styles.count(s) for s in set(styles)},
        "fields_explored": sorted(list(fields_used)),
    }

# ===== Main =====
def main():
    # 1) 获取字段
    logger.info("Fetching fields for %s...", DATASET)
    # Try TOP3000
    fields = []
    for univ in UNIVERSE_SEQ:
        try:
            r = api.session.get(f"{API_BASE}data-sets/{DATASET}?universe={univ}")
            if r.status_code == 200:
                fields = r.json().get("fields", [])
                if fields: break
        except: pass
    if not fields:
        logger.error("Cannot fetch fields for %s", DATASET)
        return
    logger.info("Dataset %s: %d fields", DATASET, len(fields))

    # 2) 生成变体
    variants = build_variants(fields)
    total_variants = len(variants)
    logger.info("Total variants: %d", total_variants)

    # 3) 续跑
    state = {"results": [], "found": [], "total_variants": total_variants,
             "batch_no": 0, "fields": [f.get("id","") for f in fields]}
    if os.path.exists(CKPT):
        try:
            ck = json.load(open(CKPT, encoding="utf-8"))
            state["results"] = list(ck.get("results") or [])
            state["found"] = list(ck.get("found") or [])
            done_labels = {r.get("label") for r in state["results"]}
            variants = [v for v in variants if v["label"] not in done_labels]
            logger.info("Resume: %d done, %d left, %d found",
                       len(state["results"]), len(variants), len(state["found"]))
        except Exception as e:
            logger.warning("Checkpoint load error: %s", e)

    if not variants:
        logger.info("ALL DONE. No remaining variants.")
        return

    # 4) 并发回测
    start_ts = time.time()
    q = _queue.Queue()
    for b in chunked(variants, BATCH_SIZE):
        q.put(b)

    lanes = []
    for i in range(N_LANES):
        t = threading.Thread(target=_lane_worker, args=(i, q, state, total_variants, start_ts),
                            name=f"lane-{i}", daemon=True)
        t.start(); lanes.append(t)
    for t in lanes:
        t.join()

    # 5) 多样性报告
    diversity_report(state["results"], state.get("batch_no", 0))
    _save_ckpt(state)

    logger.info("Batch complete. Found: %d alphas", len(state["found"]))
    for fa in state["found"]:
        logger.info("  READY: %s S=%.2f", fa.get("pid","?"), fa.get("sharpe",0))


if __name__ == "__main__":
    main()
