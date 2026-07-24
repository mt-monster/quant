#!/usr/bin/env python3
"""V33 HKG analyst10 v2 — Phase分离架构 (参考顾问代码效率做法).

v1 问题: run_variant 把回测+check+PC等待绑在一起, PC等待(~180s)阻塞线程,
         5线程并行效率仅20%, 1100变体需要14.5h.

v2 改进:
  Phase 1: 批量回测 (5并发, 只做POST+轮询+cheap gates, 不等PC)
  Phase 2: 批量PC检查 (对cheap gates PASS的alpha串行检查PC)

预期效率: 5x提速 (14.5h -> ~3.7h)
  Phase 1: 1100/5 * 46s = 10120s (~2.8h)
  Phase 2: ~110 alpha * 30s = 3300s (~0.9h) [假设10%通过cheap gates]

不自动提交! PC<0.70 才报告候选.
"""
import sys, os, json, time, logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))
from progress_logger import ProgressLogger
PROGRESS_LOG_PATH = os.getenv("PROGRESS_LOG_PATH", os.path.join(_HERE, "results", f"v33_hkg_anl10_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("v33")
from wd_lib_wrapper import WqApiSimple

PRE_SHARPE = 1.58; PRE_FITNESS = 1.00; HARD_MARGIN_BP = 5.0
HARD_TVR_MIN = 0.05; HARD_TVR_MAX = 0.20; HARD_RETURNS = 0.05
MAX_PROD_CORR = 0.70

CHECKPOINT_PATH = os.path.join(_HERE, "results", "v33_hkg_anl10_checkpoint.json")
EST_SEC_PER_STEP = 40.0  # 续跑时用于折算已完成部分、估算 ETA 的每步耗时

def load_checkpoint(path):
    """载入断点续跑检查点；返回已完成 variant 的结果列表。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("results", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_checkpoint(path, results):
    """原子写入检查点：每个 variant 完成后调用，确保中断后可恢复。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

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

# 2-field combinations from inspiration templates
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

logger.info("V33 HKG analyst10 v2 (Phase-separated) | %d variants | log: %s", len(VARIANTS), PROGRESS_LOG_PATH)


# =====================================================================
# Phase 1: 回测 + cheap gates (不等PC, 立即释放线程)
# =====================================================================
def run_backtest_only(api, label, expr, ov, pl):
    """只做回测 + cheap gates 检查. 不等PC. 线程立即释放."""
    settings = settings_base.copy(); settings.update(ov)
    try:
        res = api.run_backtest(expr, settings=settings)
    except Exception as e:
        if pl: pl.step(extra={"label": label, "status": "exception", "error": str(e)[:80], "phase": 1})
        return None
    if not res or not res.get("platform_id"):
        if pl: pl.step(extra={"label": label, "status": "no_alpha_id", "phase": 1})
        return None
    pid = res["platform_id"]
    # 获取 alpha 详情
    det = api.get_alpha_details(pid); is_ = det.get("is") or {}
    s = _to_float(is_.get("sharpe")) or 0.0; f = _to_float(is_.get("fitness")) or 0.0
    tvr = _to_float(is_.get("turnover")); marg = _to_float(is_.get("margin"))
    ret = _to_float(is_.get("returns"))
    # 获取 cheap checks (Ladder, Sub, SC — 不含PC, PC需要额外等待)
    ch = None
    for _ in range(5):
        try:
            r = api.session.get(f"https://api.worldquantbrain.com/alphas/{pid}/check", timeout=60)
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
    # 评估 cheap gates
    fails = []
    if s < PRE_SHARPE: fails.append(f"S={s:.3f}")
    if f < PRE_FITNESS: fails.append(f"F={f:.3f}")
    if tvr is not None and (tvr < HARD_TVR_MIN or tvr > HARD_TVR_MAX): fails.append(f"TVR={tvr:.4f}")
    if marg is not None and marg*10000 < HARD_MARGIN_BP: fails.append(f"M={marg*10000:.1f}bp")
    if ret is not None and ret < HARD_RETURNS: fails.append(f"Ret={ret:.4f}")
    if ch:
        fn = [c.get("name") for c in checks if c.get("result") == "FAIL"]
        if fn: fails.append(f"FAIL: {','.join(fn)}")
    # 如果PC已经可用(平台已计算完), 直接判断
    if pcr in ("PASS","FAIL","WARNING"):
        pc_val = _to_float(pcv)
        if pc_val is not None and pc_val >= MAX_PROD_CORR:
            fails.append(f"PC={pc_val:.4f}")
        elif pc_val is not None and pc_val < MAX_PROD_CORR:
            # PC已出且PASS — 直接是候选!
            logger.info("[%s] >>> VALID CANDIDATE (PC=%.4f, already computed)!", label, pc_val)
            if pl: pl.step(extra={"label": label, "pid": pid, "status": "VALID_CANDIDATE", "sharpe": s, "fitness": f, "tvr": tvr, "margin": marg, "ladder": lv, "ladder_result": lr, "prod_corr": pc_val, "fails": [], "phase": 1})
            return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":True,"fails":[],"ladder":lv,"ladder_result":lr,"prod_corr":pc_val}
    status = "FAIL" if fails else "PENDING_PC"
    if pl: pl.step(extra={"label": label, "pid": pid, "status": status, "sharpe": s, "fitness": f, "tvr": tvr, "margin": marg, "ladder": lv, "ladder_result": lr, "sub": sv, "sub_result": sr, "self_corr": scv, "self_corr_result": scr, "prod_corr": pcv, "prod_corr_result": pcr, "fails": fails, "phase": 1})
    if fails:
        return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":False,"fails":fails,"ladder":lv,"ladder_result":lr}
    # Cheap gates PASS, PC未出 — 进入Phase 2
    logger.info("[%s] >>> Cheap gates passed! Deferring PC check to Phase 2.", label)
    return {"label":label,"pid":pid,"sharpe":s,"fitness":f,"tvr":tvr,"margin":marg,"passed":"PENDING_PC","fails":[],"ladder":lv,"ladder_result":lr}


# =====================================================================
# Phase 2: 批量PC检查 (对cheap gates PASS的alpha检查PC)
# =====================================================================
def wait_for_pc(api, pid, max_wait_s=3600, label=""):
    waited = 0
    while waited < max_wait_s:
        try:
            ch = api.session.get(f"https://api.worldquantbrain.com/alphas/{pid}/check", timeout=60)
            if ch.ok and ch.text.strip():
                checks = (ch.json().get("is") or {}).get("checks") or []
                pc = next((c for c in checks if c.get("name") == "PROD_CORRELATION"), None)
                if pc and pc.get("result") in ("PASS","FAIL","WARNING"):
                    return _to_float(pc.get("value"))
            time.sleep(30); waited += 30
        except:
            time.sleep(30); waited += 30
    return None

def check_pc_for_pending(api, item, pl):
    """Phase 2: 对单个PENDING_PC的alpha检查PC."""
    label = item["label"]; pid = item["pid"]
    logger.info("[Phase2] [%s] Checking PC...", label)
    pc_val = wait_for_pc(api, pid, max_wait_s=3600, label=label)
    if pc_val is None:
        logger.warning("[Phase2] [%s] PC timeout!", label)
        if pl: pl.step(extra={"label": label, "pid": pid, "status": "PC_TIMEOUT", "phase": 2})
        return {**item, "passed": False, "fails": ["PC_TIMEOUT"]}
    if pc_val >= MAX_PROD_CORR:
        logger.warning("[Phase2] [%s] PC=%.4f >= 0.70!", label, pc_val)
        if pl: pl.step(extra={"label": label, "pid": pid, "status": "PC_FAIL", "prod_corr": pc_val, "phase": 2})
        return {**item, "passed": False, "fails": [f"PC={pc_val:.4f}"], "prod_corr": pc_val}
    logger.info("[Phase2] [%s] >>> VALID CANDIDATE (PC=%.4f)!", label, pc_val)
    if pl: pl.step(extra={"label": label, "pid": pid, "status": "VALID_CANDIDATE", "prod_corr": pc_val, "phase": 2})
    return {**item, "passed": True, "fails": [], "prod_corr": pc_val}


# =====================================================================
# 主流程
# =====================================================================
api = WqApiSimple()
# ---- 断点续跑：载入检查点，跳过已完成 variant ----
FRESH = os.getenv("V33_FRESH") is not None
ckpt_results = [] if FRESH else load_checkpoint(CHECKPOINT_PATH)
done_labels = {r["label"] for r in ckpt_results if r.get("label")}
results = list(ckpt_results)
candidates = [r for r in ckpt_results if r.get("passed") is True]
pending_pc = [r for r in ckpt_results if r.get("pid") and r.get("passed") in ("PENDING_PC", "PC_TIMEOUT")]
carried_count = len([r for r in ckpt_results if r.get("pid")])
skipped = len(done_labels)
logger.info("Resume: %s | loaded %d prior results | %d variants done, %d remaining (of %d)",
            "FRESH run (V33_FRESH set)" if FRESH else f"checkpoint={CHECKPOINT_PATH}",
            len(ckpt_results), skipped, len(VARIANTS) - skipped, len(VARIANTS))
pl = ProgressLogger(total_steps=len(VARIANTS), log_path=PROGRESS_LOG_PATH, task_name="v33_hkg_anl10", emit_interval_sec=15.0, max_recent=5)
pl.done = carried_count
pl.start(meta={"region":"HKG","universe":"TOP800","dataset":"analyst10","variants":len(VARIANTS),"architecture":"phase_separated_v2","resume":not FRESH,"carried":len(ckpt_results)})
# 续跑时把 start_ts 往回拨，使 ETA 估算接近真实（按历史每步耗时折算已完成部分）
pl.start_ts = time.time() - carried_count * EST_SEC_PER_STEP
pl.recent = [{"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "step": pl.done,
              "label": r.get("label"), "status": r.get("status"), "sharpe": r.get("sharpe"), "phase": 1}
             for r in ckpt_results[-pl.max_recent:]]

# ---- Phase 1: 批量回测 (5并发, 不等PC) ----
logger.info("=" * 60)
logger.info("Phase 1: Batch backtest (%d variants, 5 workers, no PC wait)", len(VARIANTS))
logger.info("=" * 60)
phase1_start = time.monotonic()
try:
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="v33p1") as ex:
        futs = {}
        for label, expr, ov in VARIANTS:
            if label in done_labels:
                continue  # 续跑：跳过已完成 variant
            futs[ex.submit(run_backtest_only, api, label, expr, ov, pl)] = (label, expr, ov)
        for fut in as_completed(futs):
            label, expr, ov = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                pl.step(extra={"label": label, "status": "future_exception", "error": str(e)[:80], "phase": 1})
                continue
            if r:
                results.append(r)
                save_checkpoint(CHECKPOINT_PATH, results)  # 每完成一个即落盘，支持中断恢复
                if r.get("passed") is True:
                    candidates.append(r)
                    logger.info(">>> VALID CANDIDATE [%s]! (total: %d)", label, len(candidates))
                elif r.get("passed") == "PENDING_PC":
                    pending_pc.append(r)
except Exception as e:
    logger.error("Phase 1 aborted: %s", e)

phase1_elapsed = time.monotonic() - phase1_start
logger.info("=" * 60)
logger.info("Phase 1 complete: %d done, %d pending PC, %d candidates (already known)", len(results), len(pending_pc), len(candidates))
logger.info("Phase 1 elapsed: %.0fs (%.1fs/variant, %.1fx speedup vs v1)", phase1_elapsed, phase1_elapsed/max(len(results),1), 5*phase1_elapsed/max(phase1_elapsed*len(results)/max(len(VARIANTS),1),1))
logger.info("=" * 60)

# ---- Phase 2: 批量PC检查 ----
if pending_pc:
    logger.info("Phase 2: Checking PC for %d pending alphas", len(pending_pc))
    phase2_start = time.monotonic()
    for i, item in enumerate(pending_pc):
        logger.info("[Phase2] %d/%d checking %s", i+1, len(pending_pc), item["label"])
        r = check_pc_for_pending(api, item, pl)
        # 更新 results 中的记录
        for j, res in enumerate(results):
            if res.get("pid") == item["pid"]:
                results[j] = r
                break
        save_checkpoint(CHECKPOINT_PATH, results)  # 续跑：PC 结果也落盘
        if r.get("passed") is True:
            candidates.append(r)
            logger.info(">>> VALID CANDIDATE [%s]! (total: %d)", r["label"], len(candidates))
    phase2_elapsed = time.monotonic() - phase2_start
    logger.info("Phase 2 complete: %d checked, %d new candidates, elapsed: %.0fs", len(pending_pc), len(candidates) - (len(candidates) - len([c for c in candidates if c not in pending_pc])), phase2_elapsed)
else:
    logger.info("Phase 2: No pending PC checks needed")

pl.finish(summary={"total":len(VARIANTS),"completed":len(results),"candidates":len(candidates),"pending_pc":len(pending_pc)})

# ---- 输出结果 ----
results.sort(key=lambda x: -(x.get("sharpe",0) or 0))
logger.info("V33 v2 complete | %d done, %d candidates (NOT submitted)", len(results), len(candidates))
for r in results[:20]:
    tvr = r.get("tvr"); tvr_s = f"{tvr*100:.1f}%" if tvr else "?"
    pc = r.get("prod_corr","?")
    logger.info("  %-40s %s S=%-6.3f F=%-6.3f TVR=%-7s LAD=%-5s(%s) PC=%s %s",
                r["label"], "CANDIDATE" if r.get("passed") is True else "FAIL",
                r.get("sharpe",0), r.get("fitness",0), tvr_s,
                r.get("ladder","?"), r.get("ladder_result","?"), pc,
                "; ".join(r.get("fails",[]))[:40])
out_path = os.path.join(_HERE, "results", f"scan_v33_hkg_anl10_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f: json.dump({"results":results,"candidates":candidates}, f, indent=2)
logger.info("Saved to %s", out_path)
if candidates:
    print("\n" + "="*80)
    print(f"VALID CANDIDATES (PC < 0.70, NOT submitted -- for user to submit):")
    print("="*80)
    for c in candidates:
        print(f"  PID={c['pid']} | S={c['sharpe']:.3f} F={c['fitness']:.3f} TVR={c['tvr']*100:.1f}% LAD={c['ladder']}({c['ladder_result']}) PC={c.get('prod_corr','?')}")
        print(f"    Label: {c['label']}")
