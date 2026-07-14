#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USA / delay=1 / 单数据集(PM==1.0 未点亮金字塔) / 双字段组合 / PPA 挖掘
==================================================================================
目标：在【单个】未点亮金字塔(USA/D1/TOP3000, pyramidMultiplier==1.0)数据集内，
      用【两个字段的组合】构造 alpha，直到找到 2 个【可提交】的 alpha 才停止。

严格闸门（用户硬约束）：
  * 必须等到【生产相关性(PROD_CORR)结果出来】；没出来绝不视为可提交。
  * 生产相关性 > 0.7 的 alpha 绝不提交/计入。
  * 只有 IS 通过 + 检查无 FAIL + 生产相关性可用且 < 0.7 的 alpha 才算“可提交”。

选集：institutions6（Institutions and Beneficial Stake Ownership），22 个 MATRIX 字段，
      经济含义分 3 组（净买入压力 / 机构主导度 / 每股价值），双字段组合空间充足。

提交：对每个“可提交”的 alpha 调用 update_alpha_properties 设置
      name(无空格) / description(英文) / tags=["PowerPoolSelected"] / color=GREEN，
      符合 workflow Stage 6 的 PPA 提交约定。
"""
import sys, os, json, time, logging, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import combinations
from threading import Lock

sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv(os.path.abspath(".env"))

try:
    from wd_lib_wrapper import WqApiSimple
except ImportError:
    from worldquant_alpha.wd_lib_wrapper import WqApiSimple
try:
    from wd_lib.api.alphas import update_alpha_properties
except ImportError:
    from worldquant_alpha.wd_lib.api.alphas import update_alpha_properties

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ppa_single")

# ───────────────────────── 配置 ─────────────────────────
DATASET_ID = "institutions6"
DATASET_NAME = "Institutions and Beneficial Stake Ownership"
REGION = "USA"
UNIVERSE = "TOP3000"
DELAY = 1
DECAY = 4
NEUT = "SUBINDUSTRY"          # PPA 用子行业中性化
TRUNCATION = 0.08
TARGET_COUNT = 2               # 找到 2 个可提交才停
MAX_PROD_CORR = 0.7          # 硬上限：>0.7 绝不提交
MAX_WORKERS = 2               # 拥堵时降并发，避免全部排队卡死
PROD_CORR_WAIT = 3600        # 等生产相关性最多 1 小时（应对集群拥堵）
BACKFILL_WIN = 66              # 机构持仓为季频，窗口 66 个交易日

# 字段包裹：季频机构数据 → 前向填充
def w(f):
    return f"ts_backfill({f}, {BACKFILL_WIN})"

SETTINGS = {
    "instrumentType": "EQUITY",
    "region": REGION,
    "universe": UNIVERSE,
    "delay": DELAY,
    "decay": DECAY,
    "neutralization": NEUT,
    "truncation": TRUNCATION,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P5Y",       # 缩短回测窗口以加速（集群拥堵时显著降算力）；生产相关性仍为最终闸门
}

# ───────────────────────── 22 个 MATRIX 字段 ─────────────────────────
FIELDS = [
    "aggregate_equity_value_all_owners",
    "aggregate_equity_value_institutions",
    "aggregate_share_count_all_owners",
    "aggregate_share_count_institutions",
    "count_institutional_buyers_security",
    "count_institutional_holders_security",
    "count_institutional_sellers_security",
    "inst6_num_of_institutional_buyers",
    "inst6_num_of_institutional_holders",
    "inst6_num_of_institutional_sellers",
    "inst6_num_of_institutional_shares_bought",
    "inst6_num_of_institutional_shares_sold",
    "inst6_total_share_held_by_owners",
    "inst6_total_shares_held_by_institutions",
    "inst6_value_held_by_institutions",
    "inst6_value_held_by_owners",
    "inst6_value_of_institutional_shares_bought",
    "inst6_value_of_institutional_shares_sold",
    "market_value_institutional_shares_acquired",
    "market_value_institutional_shares_disposed",
    "quantity_institutional_shares_acquired",
    "quantity_institutional_shares_disposed",
]

# ───────────────────────── 经济互补字段对（按逻辑精选）─────────────────────────
PAIRS = [
    # A 组：净买入压力（买方面 vs 卖方面）
    ("inst6_num_of_institutional_buyers", "inst6_num_of_institutional_sellers"),
    ("count_institutional_buyers_security", "count_institutional_sellers_security"),
    ("inst6_num_of_institutional_shares_bought", "inst6_num_of_institutional_shares_sold"),
    ("quantity_institutional_shares_acquired", "quantity_institutional_shares_disposed"),
    ("market_value_institutional_shares_acquired", "market_value_institutional_shares_disposed"),
    ("inst6_value_of_institutional_shares_bought", "inst6_value_of_institutional_shares_sold"),
    # B 组：机构主导度（机构 vs 全体持有者）
    ("inst6_value_held_by_institutions", "aggregate_equity_value_all_owners"),
    ("inst6_total_shares_held_by_institutions", "aggregate_share_count_all_owners"),
    ("aggregate_equity_value_institutions", "aggregate_equity_value_all_owners"),
    ("aggregate_share_count_institutions", "aggregate_share_count_all_owners"),
    ("inst6_num_of_institutional_holders", "count_institutional_holders_security"),
    # C 组：每股价值 / 平均成本代理（价值 vs 股数）
    ("inst6_value_held_by_institutions", "inst6_total_shares_held_by_institutions"),
    ("inst6_value_held_by_owners", "inst6_total_share_held_by_owners"),
    ("aggregate_equity_value_institutions", "aggregate_share_count_institutions"),
    ("inst6_value_of_institutional_shares_bought", "inst6_num_of_institutional_shares_bought"),
    # D 组：持有者 vs 买卖方（集中度/信念）
    ("inst6_num_of_institutional_holders", "inst6_num_of_institutional_buyers"),
    ("count_institutional_holders_security", "count_institutional_buyers_security"),
    ("inst6_num_of_institutional_holders", "inst6_num_of_institutional_sellers"),
    # E 组：买卖价值 vs 买卖股数（溢价/折价代理）
    ("market_value_institutional_shares_acquired", "quantity_institutional_shares_acquired"),
    ("market_value_institutional_shares_disposed", "quantity_institutional_shares_disposed"),
    ("inst6_value_of_institutional_shares_bought", "inst6_num_of_institutional_shares_bought"),
    ("inst6_value_held_by_owners", "aggregate_equity_value_all_owners"),
]

_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION", "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION", "PRODUCTION_CORR",
)

def build_exprs_for_pair(a_raw, b_raw, extended=False):
    """为一个字段对构造多样的双字段表达式（遵循 workflow ATLAS 范式）。"""
    a, b = w(a_raw), w(b_raw)
    ops = [
        f"rank(subtract({a}, {b}))",
        f"zscore(subtract({a}, {b}))",
        f"rank(divide({a}, abs({b}) + 0.01))",
        f"group_rank(subtract({a}, {b}), industry)",
        f"rank(ts_zscore(subtract({a}, {b}), {BACKFILL_WIN}))",
        f"rank(ts_delta(subtract({a}, {b}), 22))",
        f"rank(ts_corr({a}, {b}, {BACKFILL_WIN}))",
    ]
    if extended:
        ops += [
            f"signed_power(rank(subtract({a}, {b})), 2.0)",
            f"rank(ts_rank(divide({a}, abs({b}) + 0.01), 126))",
            f"rank(ts_regression({a}, {b}, {BACKFILL_WIN}))",
            f"group_zscore(subtract({a}, {b}), subindustry)",
            f"rank(divide({b}, abs({a}) + 0.01))",
            f"rank(ts_std_dev(subtract({a}, {b}), 66))",
        ]
    return ops

def parse_production_correlation(check_payload):
    if not check_payload:
        return None
    checks = (check_payload.get("is") or {}).get("checks") or []
    for c in checks:
        name = (c.get("name") or "").upper()
        if any(k in name for k in _PROD_CORR_NAMES):
            v = c.get("value")
            if v is None:
                return None
            try:
                return abs(float(v))
            except (TypeError, ValueError):
                return None
    for c in checks:
        if "PRODUCTION" in (c.get("name") or "").upper():
            v = c.get("value")
            if v is not None:
                try:
                    return abs(float(v))
                except (TypeError, ValueError):
                    pass
    return None

def wait_for_production_correlation(api, pid, max_wait_s=PROD_CORR_WAIT, poll_s=25):
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        try:
            ch = api.get_alpha_check(pid)
        except Exception:
            time.sleep(poll_s)
            continue
        corr = parse_production_correlation(ch)
        if corr is not None:
            return corr
        logger.info("生产相关性未出，%ss 后重试... (%s)", poll_s, pid)
        time.sleep(poll_s)
    return None

def backtest_one(api, expr, sn, min_sharpe, min_fitness):
    """回测单条表达式，按闸门判断是否为【可提交】alpha。"""
    logger.info("[SIM #%d] %s", sn, expr[:90])
    try:
        res = api.run_backtest(expr, settings=SETTINGS.copy())
    except Exception as e:
        logger.warning("[SIM #%d] 回测异常: %s", sn, e)
        return None
    if not res or not res.get("platform_id"):
        return None
    pid = res["platform_id"]
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    try:
        sharpe = float(is_.get("sharpe") or 0)
        fitness = float(is_.get("fitness") or 0)
    except (TypeError, ValueError):
        sharpe, fitness = 0.0, 0.0
    if sharpe < min_sharpe or fitness < min_fitness:
        logger.info("[SIM #%d] IS 不达标 S=%.3f F=%.3f（门槛 S>=%.2f F>=%.2f）",
                   sn, sharpe, fitness, min_sharpe, min_fitness)
        return None
    # 检查无 FAIL（硬性提交前提）
    try:
        ch = api.get_alpha_check(pid)
        checks = (ch.get("is") or {}).get("checks") or []
        if any(c.get("result") == "FAIL" for c in checks):
            logger.info("[SIM #%d] 检查存在 FAIL，跳过 %s", sn, pid)
            return None
    except Exception as e:
        logger.warning("[SIM #%d] 检查异常: %s", sn, e)
        return None
    # 严格闸门：必须等到生产相关性出来
    logger.info("[SIM #%d] IS 通过 S=%.3f F=%.3f，等待生产相关性...", sn, sharpe, fitness)
    pc = wait_for_production_correlation(api, pid)
    if pc is None:
        logger.warning("[SIM #%d] 生产相关性未出（超时），按规则【不提交】%s", sn, pid)
        return None
    if pc > MAX_PROD_CORR:
        logger.info("[SIM #%d] 生产相关性 %.4f > %.2f，按规则【不提交】%s",
                   sn, pc, MAX_PROD_CORR, pid)
        return None
    rec = {
        "platform_alpha_id": pid,
        "expression": expr,
        "sharpe": sharpe,
        "fitness": fitness,
        "production_correlation": pc,
        "found_at": datetime.now().isoformat(),
        "sim_number": sn,
    }
    logger.info("[SIM #%d] ✅ 可提交 alpha | id=%s | S=%.3f F=%.3f PC=%.4f",
                sn, pid, sharpe, fitness, pc)
    return rec

def short_name(fid):
    return fid.split("_")[-1][:10]

def submit_one(api, rec, idx):
    pid = rec["platform_alpha_id"]
    expr = rec["expression"]
    name = f"inst6_ppa{idx}_USA_SUBIND"
    name = name[:60]
    desc = (
        "Idea: smart-money conviction signal from institutional beneficial stake ownership "
        f"(dataset {DATASET_ID}, unlit pyramid). "
        "Rationale for data used: institutions6 covers institutional buyers/holders/sellers, "
        "shares and dollar value held/acquired/disposed. "
        "Rationale for operators used: cross-sectional ranking of a two-field interaction "
        "isolates net institutional pressure while controlling subindustry neutralization."
    )
    props = {
        "name": name,
        "tags": ["PowerPoolSelected"],
        "regular.description": desc,
    }
    try:
        ok = update_alpha_properties(pid, props, session=api.session)
        logger.info("设置属性 %s -> %s", pid, "OK" if ok else "FAIL")
    except Exception as e:
        logger.warning("设置属性异常: %s", e)
    # 设 GREEN（生产相关性 < 0.7 即满足提交/提名条件）
    try:
        update_alpha_properties(pid, {"color": "GREEN"}, session=api.session)
        logger.info("设置 color=GREEN %s", pid)
    except Exception as e:
        logger.warning("设置颜色异常: %s", e)
    rec["name"] = name
    rec["description"] = desc
    rec["color"] = "GREEN"
    return rec

def mine_pass(api, pairs, found, min_sharpe, min_fitness, extended=False):
    """执行一轮挖掘（单数据集、双字段组合）。找到 TARGET_COUNT 即停。"""
    rng = random.Random(42)
    exprs = []
    for a, b in pairs:
        for e in build_exprs_for_pair(a, b, extended=extended):
            exprs.append(e)
    # 去重 + 打乱
    seen = set(); uniq = []
    for e in exprs:
        if e not in seen:
            seen.add(e); uniq.append(e)
    rng.shuffle(uniq)
    logger.info("本轮表达式池: %d 条（去重后），门槛 S>=%.2f F>=%.2f，并发=%d",
                len(uniq), min_sharpe, min_fitness, MAX_WORKERS)
    lock = Lock()
    total = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="W") as ex:
        futs = {}
        for e in uniq:
            with lock:
                if len(found) >= TARGET_COUNT:
                    break
                total += 1
                sn = total
            futs[ex.submit(backtest_one, api, e, sn, min_sharpe, min_fitness)] = e
        for fut in as_completed(futs):
            expr = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                logger.warning("future 异常: %s", e)
                continue
            if rec:
                with lock:
                    found.append(rec)
                    logger.info("🎯 已找到 %d/%d 个可提交 alpha", len(found), TARGET_COUNT)
                submit_one(api, rec, len(found))
            with lock:
                if len(found) >= TARGET_COUNT:
                    for f in futs:
                        f.cancel()
                    break
    return len(found)

def main():
    logger.info("=" * 78)
    logger.info("USA/D1 单数据集(PPA) 双字段挖掘 | 数据集=%s(%s)", DATASET_ID, DATASET_NAME)
    logger.info("目标: 找到 %d 个可提交 alpha（生产相关性必须出且 < %.2f）",
                TARGET_COUNT, MAX_PROD_CORR)
    logger.info("=" * 78)
    api = WqApiSimple()
    found = []
    # Pass 1：精选字段对 × 7 范式，门槛 S>=1.0 F>=0.5
    mine_pass(api, PAIRS, found, min_sharpe=1.0, min_fitness=0.5, extended=False)
    # Pass 2（若不足）：扩展范式 + 放宽门槛 S>=0.8 F>=0.4
    if len(found) < TARGET_COUNT:
        logger.info("Pass 1 仅找到 %d 个，启动 Pass 2（扩展范式+放宽门槛）", len(found))
        mine_pass(api, PAIRS, found, min_sharpe=0.8, min_fitness=0.4, extended=True)
    # 保存 + 记录
    os.makedirs("results", exist_ok=True)
    out = os.path.join("results", f"usa_ppa_{DATASET_ID}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "dataset_id": DATASET_ID,
            "dataset_name": DATASET_NAME,
            "region": REGION, "universe": UNIVERSE, "delay": DELAY,
            "neutralization": NEUT, "decay": DECAY,
            "target": TARGET_COUNT, "found": len(found),
            "max_prod_corr": MAX_PROD_CORR,
            "submitted_alphas": found,
        }, f, indent=2, ensure_ascii=False)
    logger.info("=" * 78)
    logger.info("完成 | 可提交 alpha: %d/%d | 结果: %s", len(found), TARGET_COUNT, out)
    for i, r in enumerate(found, 1):
        logger.info("  [%d] id=%s | S=%.3f F=%.3f PC=%.4f | %s",
                   i, r["platform_alpha_id"], r["sharpe"], r["fitness"],
                   r["production_correlation"], r["expression"][:70])
    # tracking md
    write_tracking(found)

def write_tracking(found):
    os.makedirs("tracking", exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.join("tracking", f"{ts}_inst6_USA_PPA.md")
    lines = [f"## 提交记录 (USA/D1 PPA, 单数据集 {DATASET_ID})", "",
             f"- 数据集: {DATASET_ID} ({DATASET_NAME})",
             f"- 区域/宇宙/延迟: {REGION}/{UNIVERSE}/D{DELAY}",
             f"- 中性化/衰减: {NEUT}/{DECAY} | 截断: {TRUNCATION}",
             f"- 找到可提交 alpha: {len(found)}/{TARGET_COUNT}",
             f"- 硬闸门: 生产相关性必须出且 < {MAX_PROD_CORR}（否则绝不提交）", "",
             "| # | Alpha ID | Expression | Sharpe | Fitness | ProdCorr |",
             "|---|---|---|---|---|---|"]
    for i, r in enumerate(found, 1):
        lines.append(f"| {i} | {r['platform_alpha_id']} | {r['expression']} | "
                     f"{r['sharpe']:.3f} | {r['fitness']:.3f} | {r['production_correlation']:.4f} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("跟踪记录已写入 %s", path)

if __name__ == "__main__":
    main()
