#!/usr/bin/env python3
"""V33 HKG analyst10 v3 — Multi-simulation 架构 (参考顾问代码).

v1 问题: 单alpha提交 + PC等待阻塞, 5线程并行效率仅20%
v2 问题: Phase分离解决了PC阻塞, 但平台侧回测串行化, 效率仍19%
v3 改进: Multi-simulation — 一次POST提交N个alpha, 平台batch调度

如果 v3 无提升, 回退到 v2 (Phase分离版) 继续跑任务.
"""
import sys, os, json, time, logging, re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))
from progress_logger import ProgressLogger
PROGRESS_LOG_PATH = os.getenv("PROGRESS_LOG_PATH", os.path.join(_HERE, "results", f"v33_hkg_anl10_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v33")
from wd_lib_wrapper import WqApiSimple

API_BASE = "https://api.worldquantbrain.com"
BATCH_SIZE = 10  # 每个 multi-sim 包含多少个 alpha

PRE_SHARPE = 1.58; PRE_FITNESS = 1.00; HARD_MARGIN_BP = 5.0
HARD_TVR_MIN = 0.05; HARD_TVR_MAX = 0.20; HARD_RETURNS = 0.05
MAX_PROD_CORR = 0.70

def _to_float(v):
    if v is None: return None
    try: return float(v)
    except: return None

settings_base = {
    "instrumentType": "EQUITY", "region": "HKG", "universe": "TOP800",
    "delay": 1, "decay": 4, "neutralization": "SUBINDUSTRY", "truncation": 0.08,
    "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
    "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y",
}

SIGNAL_PAIRS = [
    ("anl10_smartest_ebi_fy1_consensus", "anl10_smartest_ebi_fy1_smart_ests_v0", "ebi_smart_vs_cons"),
    ("anl10_smartest_net_fy1_consensus", "anl10_smartest_net_fy1_smart_ests_v0", "net_smart_vs_cons"),
    ("anl10_smartest_sal_fy1_consensus", "anl10_smartest_sal_fy1_smart_ests_v0", "sal_smart_vs_cons"),
    ("anl10_smartest_pre_fy1_consensus", "anl10_smartest_pre_fy1_smart_ests_v0", "pre_smart_vs_cons"),
    ("anl10_analyst_innovation_sal_innovate_decrease_fy1", "anl10_analyst_innovation_sal_innovate_increase_fy1", "sal_innov_net"),
    ("anl10_analyst_innovation_pre_innovate_decrease_fy1", "anl10_analyst_innovation_pre_innovate_increase_fy1", "pre_innov_net"),
    ("anl10_smartest_ebi_fy2_smart_ests_v0", "anl10_smartest_ebi_fy1_smart_ests_v0", "ebi_fy1_vs_fy2"),
    ("anl10_smartest_sal_fy2_smart_ests_v0", "anl10_smartest_sal_fy1_smart_ests_v0", "sal_fy1_vs_fy2"),
    ("anl10_analyst_innovation_sal_revise_ratio_to_close_fy1", "anl10_analyst_innovation_sal_revise_value_fy1", "sal_rev_val_vs_ratio"),
    ("anl10_smartest_ebi_fy1_pred_surps_v1", "anl10_smartest_ebi_fy1_pred_surps_v0", "ebi_surp_v0_vs_v1"),
    ("anl10_smartest_sal_fy1_pred_surps_v1", "anl10_smartest_sal_fy1_pred_surps_v0", "sal_surp_v0_vs_v1"),
]

VARIANTS = []
for fA, fB, sig_name in SIGNAL_PAIRS:
    A = f"ts_backfill({fA}, 66)"
    B = f"ts_backfill({fB}, 66)"
    SPREAD = f"subtract(ts_mean({B}, 22), ts_mean({A}, 22), filter=true)"
    fund_plain = f"rank(ts_zscore({SPREAD}, 189))"
    fund_gz = f"rank(group_zscore(ts_zscore({SPREAD}, 189), industry))"
    for ret_z in [21, 42]:
        ret_expr = f"scale(-rank(ts_zscore(returns, {ret_z})))"
        for w in [0.30, 0.35, 0.40, 0.45, 0.50]:
            for decay in [3, 4, 5, 6, 7]:
                VARIANTS.append((f"{sig_name}_plain_r{ret_z}_w{w}_d{decay}",
                    f"scale({fund_plain}) + {ret_expr} * {w}", {"decay": decay}))
                VARIANTS.append((f"{sig_name}_gzi_r{ret_z}_w{w}_d{decay}",
                    f"scale({fund_gz}) + {ret_expr} * {w}", {"decay": decay}))

logger.info("V33 HKG v3 (multi-sim) | %d variants, batch=%d | log: %s", len(VARIANTS), BATCH_SIZE, PROGRESS_LOG_PATH)


# =====================================================================
# Multi-simulation 核心函数 (参考顾问 machine_lib.py)
# =====================================================================
def submit_multi_sim(session, sim_data_list, api, max_retries=10):
    """提交 multi-simulation, 返回 progress URL."""
    for attempt in range(max_retries):
        try:
            r = session.post(f"{API_BASE}/simulations", json=sim_data_list, timeout=120)
            if r.ok:
                loc = r.headers.get("Location", "")
                if not loc:
                    try:
                        loc = r.json().get("location", "")
                    except: pass
                if loc:
                    return loc
                logger.error("multi-sim: no Location header. status=%s body=%s", r.status_code, r.text[:200])
                return None
            if r.status_code == 429:
                wait = min(20 + attempt * 8, 45)
                logger.warning("multi-sim 429, waiting %ss (#%d)", wait, attempt)
                time.sleep(wait); continue
            if r.status_code == 401:
                logger.warning("multi-sim 401, re-auth...")
                api._reauth()
                session.cookies.clear()
                session.cookies.update(api.session.cookies)
                continue
            if r.status_code == 400:
                logger.error("multi-sim 400: %s", r.text[:300])
                return "BAD_REQUEST"
            logger.warning("multi-sim HTTP %s, retry...", r.status_code)
            time.sleep(15)
        except Exception as e:
            logger.warning("multi-sim network error: %s", e)
            time.sleep(15)
    return None

def poll_multi_sim(session, prog_url, max_wait=600):
    """轮询 multi-sim 进度, 返回 children 列表."""
    started = time.monotonic()
    while time.monotonic() - started < max_wait:
        try:
            pr = session.get(prog_url, timeout=60)
            retry_after = pr.headers.get("Retry-After", "0")
            try:
                ra_val = float(retry_after)
            except:
                ra_val = 0
            if ra_val == 0:
                try:
                    data = pr.json()
                except:
                    time.sleep(5); continue
                status = data.get("status", "")
                children = data.get("children", [])
                if status == "COMPLETE" or (children and ra_val == 0):
                    return children
                if status == "ERROR":
                    logger.error("multi-sim ERROR: %s", str(data)[:200])
                    return []
                # 有 children 但状态不是 COMPLETE, 继续等
                if children:
                    return children
                time.sleep(5)
            else:
                time.sleep(ra_val)
        except Exception as e:
            logger.warning("multi-sim poll error: %s", e)
            time.sleep(10)
    logger.warning("multi-sim timeout after %ss", max_wait)
    return None

def get_child_alpha(session, child_id, api, max_retries=5):
    """获取子回测的 alpha id (child_id 可能是 URL 或 ID)."""
    if child_id.startswith("http"):
        child_url = child_id
    else:
        child_url = f"{API_BASE}/simulations/{child_id}"
    for _ in range(max_retries):
        try:
            r = session.get(child_url, timeout=60)
            if r.ok:
                data = r.json()
                alpha_id = data.get("alpha")
                if alpha_id:
                    return alpha_id
                retry_after = r.headers.get("Retry-After", "0")
                try:
                    ra_val = float(retry_after)
                except:
                    ra_val = 0
                if ra_val > 0:
                    time.sleep(ra_val)
                    continue
            if r.status_code == 401:
                api._reauth()
                session.cookies.clear()
                session.cookies.update(api.session.cookies)
                continue
            time.sleep(3)
        except:
            time.sleep(5)
    return None


# =====================================================================
# Cheap gates 评估 (与 v1/v2 相同)
# =====================================================================
def evaluate_alpha(api, label, pid, pl, phase=1):
    """获取 alpha 详情 + cheap checks, 评估 gates."""
    det = api.get_alpha_details(pid); is_ = det.get("is") or {}
    s = _to_float(is_.get("sharpe")) or 0.0; f = _to_float(is_.get("fitness")) or 0.0
    tvr = _to_float(is_.get("turnover")); marg = _to_float(is_.get("margin"))
    ret = _to_float(is_.get("returns"))
    ch = None
    for _ in range(5):
        try:
            r = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if r.status_code == 200 and r.text.strip(): ch = r.json(); break
            time.sleep(3)
        except: time.sleep(5)
    if ch is None: ch = {}
    checks = (ch.get("is") or {}).get("checks") or []
    ladder = next((c for c in checks if c.get("name") in ("IS_LADDER_SHARPE","LOW_2Y_SHARPE")), {})
    sub = next((c for c in checks if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"), {})
    sc = next((c for c in checks if c.get("name") == "SELF_CORRELATION"), {})
    pc = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), {})
    lv = ladder.get("value","?"); lr = ladder.get("result","?")
    sv = sub.get("value","?"); sr = sub.get("result","?")
    scv = sc.get("value","?"); scr = sc.get("result","?")
    pcv = pc.get("value","?"); pcr = pc.get("result","?")
    tvr_s = f"{tvr*100:.1f}%" if tvr else "?"; marg_s = f"{marg*10000:.1f}bp" if marg else "?"
    logger.info("[%s] S=%.3f F=%.3f TVR=%s M=%s | LAD=%s(%s) Sub=%s(%s) SC=%s(%s) PC=%s(%s)",
                label, s, f, tvr_s, marg_s, lv, lr, sv, sr, scv, scr, pcv, pcr)
    fails = []
    if s < PRE_SHARPE: fails.append(f"S={s:.3f}")
    if f < PRE_FITNESS: fails.append(f"F={f:.3f}")
    if tvr is not None and (tvr < HARD_TVR_MIN or tvr > HARD_TVR_MAX): fails.append(f"TVR={tvr:.4f}")
    if marg is not None and marg*10000 < HARD_MARGIN_BP: fails.append(f"M={marg*10000:.1f}bp")
    if ret is not None and ret < HARD_RETURNS: fails.append(f"Ret={ret:.4f}")
    if ch:
        fn = [c.get("name") for c in checks if c.get("result") == "FAIL"]
        if fn: fails.append(f"FAIL: {','.join(fn)}")
    # 如果PC已出, 直接判断
    if pcr in ("PASS","FAIL","WARNING"):
        pc_val = _to_float(pcv)
        if pc_val is not None and pc_val < MAX_PROD_CORR and not fails:
            logger.info("[%s] >>> VALID CANDIDATE (PC=%.4f, already computed)!", label, pc_val)
            if pl: pl.step(extra={"label": label, "pid": pid, "status": "VALID_CANDIDATE", "sharpe": s, "fitness": f, "tvr": tvr, "margin": marg, "ladder": lv, "ladder_result": lr, "prod_corr": pc_val, "fails": [], "phase": phase})
            return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":True,"fails":[],"ladder":lv,"ladder_result":lr,"prod_corr":pc_val}
        if pc_val is not None and pc_val >= MAX_PROD_CORR:
            fails.append(f"PC={pc_val:.4f}")
    status = "FAIL" if fails else "PENDING_PC"
    if pl: pl.step(extra={"label": label, "pid": pid, "status": status, "sharpe": s, "fitness": f, "tvr": tvr, "margin": marg, "ladder": lv, "ladder_result": lr, "sub": sv, "sub_result": sr, "self_corr": scv, "self_corr_result": scr, "prod_corr": pcv, "prod_corr_result": pcr, "fails": fails, "phase": phase})
    if fails:
        return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":False,"fails":fails,"ladder":lv,"ladder_result":lr}
    logger.info("[%s] >>> Cheap gates passed! Deferring PC to Phase 2.", label)
    return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":"PENDING_PC","fails":[],"ladder":lv,"ladder_result":lr}

def wait_for_pc(api, pid, max_wait_s=3600, label=""):
    waited = 0
    while waited < max_wait_s:
        try:
            ch = api.session.get(f"{API_BASE}/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                checks = (ch.json().get("is") or {}).get("checks") or []
                pc = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), None)
                if pc and pc.get("result") in ("PASS","FAIL","WARNING"):
                    return _to_float(pc.get("value"))
            time.sleep(30); waited += 30
        except:
            time.sleep(30); waited += 30
    return None


# =====================================================================
# 主流程
# =====================================================================
api = WqApiSimple()
session = api.session  # 共享 session
results = []; candidates = []; pending_pc = []
pl = ProgressLogger(total_steps=len(VARIANTS), log_path=PROGRESS_LOG_PATH, task_name="v33_hkg_anl10", emit_interval_sec=15.0, max_recent=5)
pl.start(meta={"region":"HKG","universe":"TOP800","dataset":"analyst10","variants":len(VARIANTS),"architecture":"multi_sim_v3","batch_size":BATCH_SIZE})

# 构建 sim_data_list
all_items = []
for label, expr, ov in VARIANTS:
    settings = settings_base.copy(); settings.update(ov)
    sim_data = {"type": "REGULAR", "settings": settings, "regular": expr}
    all_items.append((label, sim_data))

# 分 batch
batches = [all_items[i:i+BATCH_SIZE] for i in range(0, len(all_items), BATCH_SIZE)]
logger.info("=" * 60)
logger.info("Phase 1: Multi-simulation (%d batches x %d alpha/batch)", len(batches), BATCH_SIZE)
logger.info("=" * 60)

phase1_start = time.monotonic()
multi_sim_supported = True  # 标记 multi-sim 是否可用

for batch_idx, batch in enumerate(batches):
    labels = [item[0] for item in batch]
    sim_data_list = [item[1] for item in batch]

    if multi_sim_supported:
        # 尝试 multi-sim
        prog_url = submit_multi_sim(session, sim_data_list, api)
        if prog_url == "BAD_REQUEST":
            # multi-sim 不支持, 切换到单 alpha 模式
            logger.error("Multi-sim not supported (400)! Falling back to single-alpha mode.")
            multi_sim_supported = False
            # 用 v2 的方式逐个提交
            for label, sd in batch:
                try:
                    res = api.run_backtest(sd["regular"], settings=sd["settings"])
                    if res and res.get("platform_id"):
                        r = evaluate_alpha(api, label, res["platform_id"], pl, phase=1)
                        if r:
                            results.append(r)
                            if r.get("passed") is True: candidates.append(r)
                            elif r.get("passed") == "PENDING_PC": pending_pc.append(r)
                except Exception as e:
                    pl.step(extra={"label": label, "status": "exception", "error": str(e)[:80], "phase": 1})
            continue
        if not prog_url:
            logger.error("Batch %d: submit failed, skipping", batch_idx)
            for label in labels:
                pl.step(extra={"label": label, "status": "submit_failed", "phase": 1})
            continue

        # 轮询 multi-sim
        children = poll_multi_sim(session, prog_url, max_wait=600)
        if children is None:
            logger.warning("Batch %d: poll timeout, skipping", batch_idx)
            for label in labels:
                pl.step(extra={"label": label, "status": "poll_timeout", "phase": 1})
            continue
        if len(children) == 0:
            logger.warning("Batch %d: no children", batch_idx)
            for label in labels:
                pl.step(extra={"label": label, "status": "no_children", "phase": 1})
            continue

        logger.info("Batch %d/%d: %d children, getting alpha ids...", batch_idx+1, len(batches), len(children))

        # 获取各子回测的 alpha id
        for i, child in enumerate(children):
            label = labels[i] if i < len(labels) else f"batch{batch_idx}_child{i}"
            alpha_id = get_child_alpha(session, child, api)
            if alpha_id:
                r = evaluate_alpha(api, label, alpha_id, pl, phase=1)
                if r:
                    results.append(r)
                    if r.get("passed") is True:
                        candidates.append(r)
                        logger.info(">>> VALID CANDIDATE [%s]! (total: %d)", label, len(candidates))
                    elif r.get("passed") == "PENDING_PC":
                        pending_pc.append(r)
            else:
                pl.step(extra={"label": label, "status": "no_alpha_id", "phase": 1})
    else:
        # Fallback: 单 alpha 提交 (v2 模式)
        for label, sd in batch:
            try:
                res = api.run_backtest(sd["regular"], settings=sd["settings"])
                if res and res.get("platform_id"):
                    r = evaluate_alpha(api, label, res["platform_id"], pl, phase=1)
                    if r:
                        results.append(r)
                        if r.get("passed") is True: candidates.append(r)
                        elif r.get("passed") == "PENDING_PC": pending_pc.append(r)
            except Exception as e:
                pl.step(extra={"label": label, "status": "exception", "error": str(e)[:80], "phase": 1})

    # 每 10 个 batch 报告进度
    if (batch_idx + 1) % 10 == 0:
        elapsed = time.monotonic() - phase1_start
        done = len(results)
        logger.info("Progress: %d/%d batches, %d alphas done, %.1fs/alpha, elapsed=%.0fs",
                    batch_idx+1, len(batches), done, elapsed/max(done,1), elapsed)

phase1_elapsed = time.monotonic() - phase1_start
logger.info("=" * 60)
logger.info("Phase 1 complete: %d done, %d pending PC, %d candidates, elapsed=%.0fs (%.1fs/alpha)",
            len(results), len(pending_pc), len(candidates), phase1_elapsed, phase1_elapsed/max(len(results),1))
logger.info("Multi-sim mode: %s", "YES" if multi_sim_supported else "NO (fallback to single)")
logger.info("=" * 60)

# ---- Phase 2: 批量PC检查 ----
if pending_pc:
    logger.info("Phase 2: Checking PC for %d pending alphas", len(pending_pc))
    for i, item in enumerate(pending_pc):
        logger.info("[Phase2] %d/%d checking %s", i+1, len(pending_pc), item["label"])
        pc_val = wait_for_pc(api, item["pid"], max_wait_s=3600, label=item["label"])
        if pc_val is None:
            logger.warning("[Phase2] [%s] PC timeout!", item["label"])
            pl.step(extra={"label": item["label"], "pid": item["pid"], "status": "PC_TIMEOUT", "phase": 2})
            item["passed"] = False; item["fails"] = ["PC_TIMEOUT"]
        elif pc_val >= MAX_PROD_CORR:
            logger.warning("[Phase2] [%s] PC=%.4f >= 0.70!", item["label"], pc_val)
            pl.step(extra={"label": item["label"], "pid": item["pid"], "status": "PC_FAIL", "prod_corr": pc_val, "phase": 2})
            item["passed"] = False; item["fails"] = [f"PC={pc_val:.4f}"]; item["prod_corr"] = pc_val
        else:
            logger.info("[Phase2] [%s] >>> VALID CANDIDATE (PC=%.4f)!", item["label"], pc_val)
            pl.step(extra={"label": item["label"], "pid": item["pid"], "status": "VALID_CANDIDATE", "prod_corr": pc_val, "phase": 2})
            item["passed"] = True; item["fails"] = []; item["prod_corr"] = pc_val
            candidates.append(item)
        # 更新 results
        for j, res in enumerate(results):
            if res.get("pid") == item["pid"]:
                results[j] = item; break

pl.finish(summary={"total":len(VARIANTS),"completed":len(results),"candidates":len(candidates),"pending_pc":len(pending_pc),"multi_sim":multi_sim_supported})

results.sort(key=lambda x: -(x.get("sharpe",0) or 0))
logger.info("V33 v3 complete | %d done, %d candidates (NOT submitted) | multi_sim=%s", len(results), len(candidates), multi_sim_supported)
for r in results[:20]:
    tvr = r.get("tvr"); tvr_s = f"{tvr*100:.1f}%" if tvr else "?"
    pc = r.get("prod_corr","?")
    logger.info("  %-40s %s S=%-6.3f F=%-6.3f TVR=%-7s LAD=%-5s(%s) PC=%s %s",
                r["label"], "CANDIDATE" if r.get("passed") is True else "FAIL",
                r.get("sharpe",0), r.get("fitness",0), tvr_s,
                r.get("ladder","?"), r.get("ladder_result","?"), pc,
                "; ".join(r.get("fails",[]))[:40])
out_path = os.path.join(_HERE, "results", f"scan_v33_hkg_anl10_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f: json.dump({"results":results,"candidates":candidates,"multi_sim":multi_sim_supported}, f, indent=2)
logger.info("Saved to %s", out_path)
if candidates:
    print("\n" + "="*80)
    print(f"VALID CANDIDATES (PC < 0.70, NOT submitted -- for user to submit):")
    print("="*80)
    for c in candidates:
        print(f"  PID={c['pid']} | S={c['sharpe']:.3f} F={c['fitness']:.3f} TVR={c['tvr']*100:.1f}% LAD={c['ladder']}({c['ladder_result']}) PC={c.get('prod_corr','?')}")
        print(f"    Label: {c['label']}")
