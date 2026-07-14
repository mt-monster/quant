#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USA / delay=1 / 多未点亮金字塔数据集(PM==1.0) / 双字段组合 / PPA 挖掘（审计重构版）
==================================================================================
审计后核心改进：
  1. 降换手优先表达式族（P1）：所有表达式至少含一个降换手机制
     （ts_rank 长窗口 / hump / ts_mean 平滑 / ts_corr），解决 TVR 40-52% 结构性偏高。
  2. Stage 4 参数扫描（workflow Stage 4）：Sharpe≥0.9 但 TVR/Margin 不达标时，
     自动生成 decay/hump/ts_rank 变体逐条回测，抢救边界候选。
  3. Stage 3.3 快速失败（workflow 3.3）：连续 32 条最高 Sharpe<0.7 → PROBABLE_FAIL 切换。
  4. 数据集切换：institutions6（22 MATRIX 日频）+ fund_holdings_panel（30 VECTOR 季频）。
     fund_holdings_panel 的 VECTOR 字段用 vec_avg 聚合，季频数据天然低换手。

设计要点（严守用户硬约束）：
  * 【保持单数据集】：每个 alpha 仅使用【单个】未点亮数据集内的两个字段组合。
  * 双字段组合：每对字段套用多种 FASTEXPR 范式。
  * 严格闸门（用户硬约束 + workflow 硬闸门，全部满足才允许提交 color=GREEN）：
      - 【用户强制】生产相关性必须出来且 < 0.70；没出来绝不提交。
      - 【Stage5.1】自相关性 SELF_CORRELATION < 0.50。
      - 【Stage4.4】Margin > 5bp、TVR ∈ [5%,20%]、Returns > 5%、Returns > Drawdown。
      - 【平台 no-FAIL】任一检查项 FAIL 一律淘汰。
  * 全局目标：跨所有数据集【找到 2 个可提交 alpha 即全部停止】。
"""
import sys, os, json, time, logging, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))

try:
    from wd_lib_wrapper import WqApiSimple
except ImportError:
    from worldquant_alpha.wd_lib_wrapper import WqApiSimple
try:
    from wd_lib.api.alphas import update_alpha_properties
except ImportError:
    from worldquant_alpha.wd_lib.api.alphas import update_alpha_properties

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ppa_multi")

# ───────────────────────── 全局配置 ─────────────────────────
REGION = "USA"
UNIVERSE = "TOP3000"
DELAY = 1
DECAY = 4
NEUT = "SUBINDUSTRY"          # PPA 用子行业中性化
TRUNCATION = 0.08
TARGET_COUNT = 2               # 跨数据集共找到 2 个可提交才停
MAX_PROD_CORR = 0.70          # 【用户强制硬约束】生产相关性必须出来且 < 0.70；>0.70 或未出 -> 绝不提交
SELF_CORR_MAX = 0.50         # 【workflow Stage5.1 硬闸门】自相关性 >= 0.50 硬淘汰
# 提交前“廉价闸门”阈值（PC 等待之前即可判定，避免对必败 alpha 做昂贵的 PC 等待）
#  注：下列两值等于 WorldQuant 平台对应检查（LOW_SHARPE≈1.58 / LOW_FITNESS≈1.0）的限额；
#      低于它们的 alpha 平台必判定 FAIL（见下方“no FAIL”闸门），因此无需为其消耗 PC 等待配额。
PRE_SHARPE = 1.58             # 预筛 Sharpe 下限（= 平台 LOW_SHARPE 限额）
PRE_FITNESS = 1.00            # 预筛 Fitness 下限（= 平台 LOW_FITNESS 限额）
HARD_MARGIN_BP = 5.0         # 【workflow Stage4.4 硬闸门】USA: Margin > 5bp
HARD_TVR_MIN = 0.05          # 【workflow Stage4.4 硬闸门】TVR >= 5%
HARD_TVR_MAX = 0.20          # 【workflow Stage4.4 硬闸门】TVR <= 20%
HARD_RETURNS = 0.05          # 【workflow Stage4.4 硬闸门】Returns > 5%
HARD_RET_DD = True             # 【workflow Stage4.4 硬闸门】Returns 必须 > Drawdown
PROD_CORR_WAIT = 3600         # 等生产相关性最多 1 小时（应对集群拥堵）
MAX_WORKERS_PER_DS = 3        # 每数据集 3 线程 × 2 数据集 = 6 线程总数；
                                 # 实际在飞回测数由 wd_lib_wrapper 的信号量锁定 = 服务端并发上限 C=5，
                                 # 多出的 1 个线程作为缓冲，随时补位，保证 5 个槽位始终打满。
                                 # 注：早期"4 线程"已实测为欠利用（C=5，4 仅用满 80%）。
# ── Stage 3.3 快速失败（workflow 3.3）──
FAST_FAIL_BATCH = 32          # 连续 32 条最高 Sharpe < 0.7 → 标记 PROBABLE_FAIL
FAST_FAIL_SHARPE = 0.7        # 快速失败的 Sharpe 阈值
# ── Stage 4 触发（workflow Stage 4）──
STAGE4_SHARPE_TRIGGER = 0.9   # Sharpe≥0.9 但 TVR>20% 时，自动触发参数扫描
STAGE4_DECAYS = [8, 16, 24]   # decay 扫描值
STAGE4_HUMPS = [0.01, 0.03]   # hump 阈值扫描

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
    "testPeriod": "P5Y",       # 缩短回测窗口以加速；生产相关性仍为最终闸门
}

# ───────────────────────── 数据集定义 ─────────────────────────
# 审计后切换：institutions6（22 MATRIX 字段，日频机构持仓/交易）
#   + fund_holdings_panel（30 VECTOR 字段，季频基金持仓，天然低换手）
# VECTOR 字段需 vec_* 聚合（workflow 2.2），由 w() 自动处理。
DATASETS = {
    "institutions6": {
        "name": "Institutions and Beneficial Stake Ownership",
        "prefix": "i6",
        "backfill": 66,
        "field_type": "MATRIX",
        "fields": [
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
        ],
        "pairs": [
            # 买 vs 卖压力（value）
            ("inst6_value_of_institutional_shares_bought", "inst6_value_of_institutional_shares_sold"),
            # 买 vs 卖压力（quantity）
            ("inst6_num_of_institutional_shares_bought", "inst6_num_of_institutional_shares_sold"),
            # 买 vs 卖广度（count）
            ("inst6_num_of_institutional_buyers", "inst6_num_of_institutional_sellers"),
            # 机构 vs 全部持有人
            ("inst6_value_held_by_institutions", "inst6_value_held_by_owners"),
            ("inst6_total_shares_held_by_institutions", "aggregate_share_count_all_owners"),
            # 收购 vs 处置（market value）
            ("market_value_institutional_shares_acquired", "market_value_institutional_shares_disposed"),
            # 收购 vs 处置（quantity）
            ("quantity_institutional_shares_acquired", "quantity_institutional_shares_disposed"),
            # 活跃买家 vs 总持有人
            ("count_institutional_buyers_security", "count_institutional_holders_security"),
            # 价值 vs 数量（隐含均价信号）
            ("inst6_value_of_institutional_shares_bought", "inst6_num_of_institutional_shares_bought"),
            # 持有人 vs 卖家（持仓粘性信号）
            ("inst6_num_of_institutional_holders", "inst6_num_of_institutional_sellers"),
        ],
        "desc_idea": (
            "Idea: institutional flow imbalance signal from beneficial stake ownership data. "
            "Dataset institutions6 covers daily institutional buyer/seller counts, share "
            "quantities and market values acquired/disposed. "
            "Rationale: dampened cross-sectional ranking of buy-sell pressure interactions "
            "isolates smart-money conviction with subindustry neutralization."
        ),
    },
    "fund_holdings_panel": {
        "name": "Global Institutional Fund Holdings",
        "prefix": "fhp",
        "backfill": 66,
        "field_type": "VECTOR",
        "vec_agg": "vec_avg",   # VECTOR 字段用 vec_avg 聚合（中心趋势/共识）
        "fields": [
            "herfindahl_index_holdings",
            "herfindahl_index_transactions",
            "holder_account_total",
            "holding_value_distribution_score",
            "large_trade_count_50bps",
            "mean_security_weight",
            "security_holding_usd_value",
            "security_transaction_usd_value",
            "stable_boundary_trade_count_21d",
            "top_weighted_account_number",
            "top_weighted_transaction_number",
            "transaction_account_total",
            "transaction_value_distribution_score",
        ],
        "pairs": [
            # 持仓集中度 vs 交易集中度
            ("herfindahl_index_holdings", "herfindahl_index_transactions"),
            # 持仓价值 vs 交易价值（持仓 vs 流量）
            ("security_holding_usd_value", "security_transaction_usd_value"),
            # 平均权重 vs 持仓分布质量
            ("mean_security_weight", "holding_value_distribution_score"),
            # 持有人广度 vs 交易者广度
            ("holder_account_total", "transaction_account_total"),
            # 顶级持有人 vs 顶级交易者
            ("top_weighted_account_number", "top_weighted_transaction_number"),
            # 持仓分布 vs 交易分布
            ("holding_value_distribution_score", "transaction_value_distribution_score"),
            # 大宗交易 vs 稳定边界交易
            ("large_trade_count_50bps", "stable_boundary_trade_count_21d"),
            # 持仓价值 vs 平均权重（规模 vs 集中度）
            ("security_holding_usd_value", "mean_security_weight"),
            # 持有人广度 vs 持仓分布
            ("holder_account_total", "holding_value_distribution_score"),
            # 交易者广度 vs 交易分布
            ("transaction_account_total", "transaction_value_distribution_score"),
        ],
        "desc_idea": (
            "Idea: fund concentration and flow divergence from global institutional fund "
            "holdings panel. Dataset fund_holdings_panel covers Herfindahl indices, holding/"
            "transaction USD values, account totals and distribution scores. "
            "Rationale: vec_avg aggregated VECTOR fields ranked cross-sectionally capture "
            "fund-level conviction vs flow divergence with subindustry neutralization."
        ),
    },
}

_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION", "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION", "PRODUCTION_CORR",
)

def w(f, bf, field_type="MATRIX", vec_agg="vec_avg"):
    """字段预处理包装器。MATRIX → ts_backfill；VECTOR → vec_* 聚合后 ts_backfill（workflow 2.2）。"""
    if field_type == "VECTOR":
        return f"ts_backfill({vec_agg}({f}), {bf})"
    return f"ts_backfill({f}, {bf})"

def build_exprs_for_pair(a_raw, b_raw, bf, extended=False, field_type="MATRIX", vec_agg="vec_avg"):
    a, b = w(a_raw, bf, field_type, vec_agg), w(b_raw, bf, field_type, vec_agg)
    spread = f"subtract({a}, {b}, filter=true)"
    # 审计后重构：降换手优先（dampening-first）。
    # 核心问题：rank(ts_zscore(subtract/divide(日频字段))) 确定性产 TVR 40-52%。
    # 解决：每条表达式至少含一个降换手机制（ts_rank 长窗口 / hump / ts_mean 平滑 / ts_corr）。
    # ── 核心范式（Pass1）：5 条，全部含降换手算子 ──
    core = [
        # P1_SPREAD + ts_rank 长窗口（126 日稳定排名，替代 ts_zscore 66）
        f"rank(ts_rank({spread}, 126))",
        # P1_SPREAD + hump 压换手（忽略 <1% 持仓变动，hump 为命名参数）
        f"hump(rank(ts_zscore({spread}, 66)), hump=0.01)",
        # P1_SPREAD + ts_mean 平滑 spread（22 日滑动降噪）
        f"rank(ts_zscore(ts_mean({spread}, 22), 66))",
        # P5_CORRELATION（关系类，天然低换手）
        f"rank(ts_corr(ts_delta({a}, 5), ts_delta({b}, 5), 126))",
        # P2_RATIO + ts_rank 长窗口
        f"rank(ts_rank(divide({a}, abs({b}) + 0.01), 126))",
    ]
    if not extended:
        return core
    # ── 扩展范式（Pass2）：补齐更多降换手变体 + P3/P4/P6/P7 ──
    ext = [
        # ts_rank 超长窗口（252 日，极稳定）
        f"rank(ts_rank({spread}, 252))",
        # hump + ts_rank 组合（双重压换手）
        f"hump(rank(ts_rank({spread}, 126)), hump=0.01)",
        # ts_quantile 分位变换（默认 gaussian driver）
        f"rank(ts_quantile({spread}, 126))",
        # group_rank + ts_rank（子行业内稳定排名）
        f"group_rank(ts_rank({spread}, 126), subindustry)",
        # P4_REGRESSION（时序回归关系，低换手）
        f"rank(ts_regression({a}, {b}, 126))",
        # P3_CONDITIONAL + ts_rank（条件门控 + 稳定排名）
        f"trade_when(ts_delta({b}, 22) > 0, rank(ts_rank({spread}, 126)))",
        # signed_power 压缩极值（+ ts_rank 稳定基座）
        f"signed_power(rank(ts_rank({spread}, 126)), 0.5)",
        # ts_mean 平滑 + hump 组合
        f"hump(rank(ts_zscore(ts_mean({spread}, 22), 66)), hump=0.01)",
        # P7_DIVERGENCE：变化分歧（ts_delta 22 日，中等频率）
        f"rank(ts_rank(subtract(ts_delta({a}, 22), ts_delta({b}, 22)), 126))",
        # P6_EVENT：事件间隔分歧
        f"rank(subtract(days_from_last_change({a}), days_from_last_change({b})))",
        # group_zscore + ts_corr（分组 + 相关性，双低换手）
        f"group_zscore(ts_corr({a}, {b}, 126), sector)",
    ]
    return core + ext

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

_SELF_CORR_NAMES = (
    "SELF_CORRELATION", "SELF_CORR", "MAX_SELF_CORRELATION",
)
def parse_self_correlation(check_payload):
    """workflow Stage 5.1：SelfCorr >= 0.50 为硬淘汰。
    若该检查项未上报（None）则放行（不阻塞提交）。"""
    if not check_payload:
        return None
    checks = (check_payload.get("is") or {}).get("checks") or []
    for c in checks:
        name = (c.get("name") or "").upper()
        if any(k in name for k in _SELF_CORR_NAMES):
            v = c.get("value")
            if v is None:
                return None
            try:
                return abs(float(v))
            except (TypeError, ValueError):
                return None
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
        logger.info("    生产相关性未出，%ss 后重试... (%s)", poll_s, pid)
        time.sleep(poll_s)
    return None

def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def check_cheap_gates(is_, ch):
    """PC 等待【之前】即可判定的廉价闸门（均为硬闸门 / 平台 FAIL 项）。
    返回 (ok, fails[list])；ok=False 时无需再做昂贵的 PC 等待，直接放弃。"""
    fails = []
    sharpe = _to_float(is_.get("sharpe"))
    fitness = _to_float(is_.get("fitness"))
    margin = _to_float(is_.get("margin"))      # 分数（1bp = 0.0001）
    turnover = _to_float(is_.get("turnover"))  # 分数
    returns = _to_float(is_.get("returns"))    # 分数
    drawdown = _to_float(is_.get("drawdown"))  # 分数
    if sharpe is None or sharpe < PRE_SHARPE:
        fails.append("Sharpe=%.3f < 预筛 %.2f" % (sharpe if sharpe is not None else -9, PRE_SHARPE))
    if fitness is None or fitness < PRE_FITNESS:
        fails.append("Fitness=%.3f < 预筛 %.2f" % (fitness if fitness is not None else -9, PRE_FITNESS))
    if margin is None or margin * 10000 < HARD_MARGIN_BP:
        mb = "None" if margin is None else "%.2fbp" % (margin * 10000)
        fails.append("Margin=%s < %sbp" % (mb, HARD_MARGIN_BP))
    if turnover is None or not (HARD_TVR_MIN <= turnover <= HARD_TVR_MAX):
        tv = "None" if turnover is None else "%.1f%%" % (turnover * 100)
        fails.append("TVR=%s 越界(需 5%%-20%%)" % tv)
    if returns is None or returns < HARD_RETURNS:
        rv = "None" if returns is None else "%.1f%%" % (returns * 100)
        fails.append("Returns=%s < %s%%" % (rv, HARD_RETURNS * 100))
    if HARD_RET_DD and returns is not None and drawdown is not None and returns <= drawdown:
        fails.append("Returns(%.1f%%) <= Drawdown(%.1f%%)" % (returns * 100, drawdown * 100))
    # 平台检查项：存在 FAIL 一律淘汰（含 LOW_SHARPE/LOW_FITNESS/LOW_2Y_SHARPE/LOW_SUB_UNIVERSE_SHARPE 等）
    checks = (ch.get("is") or {}).get("checks") or []
    fail_names = [c.get("name") for c in checks if c.get("result") == "FAIL"]
    if fail_names:
        fails.append("平台 FAIL 项: " + ",".join(fail_names))
    return (len(fails) == 0, fails)

def evaluate_hard_gates(is_, ch):
    """PC 等待【之后】、提交【之前】的最终硬闸门校验
    （workflow Stage4.4 + Stage5.1 + 用户强制约束 + 平台 no-FAIL）。
    返回 (ok, fails[list])。仅当 ok=True 才允许提交（设 GREEN）。"""
    fails = []
    # 1) 生产相关性：必须出来且 < 0.70（用户强制硬约束，绝对红线）
    pc = parse_production_correlation(ch)
    if pc is None:
        fails.append("PROD_CORRELATION 未出")
    elif pc >= MAX_PROD_CORR:
        fails.append("PROD_CORRELATION=%.4f >= %.2f" % (pc, MAX_PROD_CORR))
    # 2) 自相关性：>= 0.50 硬淘汰（Stage5.1；此处须已算出，不在 PENDING 时放行）
    sc = parse_self_correlation(ch)
    if sc is not None and sc >= SELF_CORR_MAX:
        fails.append("SELF_CORRELATION=%.4f >= %.2f" % (sc, SELF_CORR_MAX))
    # 3) 复校廉价闸门（防止并发期间数据/检查结果变更）
    ok_cheap, cheap_fails = check_cheap_gates(is_, ch)
    if not ok_cheap:
        fails.extend(cheap_fails)
    return (len(fails) == 0, fails)

# ── Stage 3.3 快速失败统计（线程安全）──
_ds_stats = {}          # {ds_id: {"total_bt": int, "max_sharpe": float}}
_stats_lock = Lock()

def _update_ds_stats(ds_id, sharpe):
    with _stats_lock:
        st = _ds_stats.setdefault(ds_id, {"total_bt": 0, "max_sharpe": -9.0})
        st["total_bt"] += 1
        if sharpe is not None and sharpe > st["max_sharpe"]:
            st["max_sharpe"] = sharpe

def _check_fast_fail(ds_id):
    """workflow Stage 3.3：连续 FAST_FAIL_BATCH 条最高 Sharpe < 0.7 → PROBABLE_FAIL"""
    with _stats_lock:
        st = _ds_stats.get(ds_id)
        if not st:
            return False
        return st["total_bt"] >= FAST_FAIL_BATCH and st["max_sharpe"] < FAST_FAIL_SHARPE

def stage4_sweep(api, ds_conf, base_expr, base_is, sn):
    """Stage 4 参数扫描（workflow Stage 4）：当候选 Sharpe≥0.9 但 TVR/Margin 不达标时，
    自动生成降换手变体（decay 扫描 / hump / ts_rank 替换），逐条回测。
    返回通过全部硬闸门的 rec 或 None。"""
    s = _to_float(base_is.get("sharpe")) or 0.0
    tvr = _to_float(base_is.get("turnover")) or 0.0
    logger.info("[%s #%d] Stage4 触发：S=%.3f TVR=%.1f%%，生成降换手变体...",
                ds_conf["prefix"], sn, s, tvr * 100)
    variants = []
    # decay 扫描（最直接：decay 越高 TVR 越低）
    for decay in STAGE4_DECAYS:
        variants.append((f"d{decay}", base_expr, {"decay": decay}))
    # hump 压换手
    for hv in STAGE4_HUMPS:
        variants.append((f"hump{hv}", f"hump({base_expr}, hump={hv})", {}))
    # ts_rank 替换 ts_zscore（长窗口稳定排名）
    trk = base_expr.replace("ts_zscore(", "ts_rank(").replace(", 66)", ", 126)")
    if trk != base_expr:
        variants.append(("trk126", trk, {}))
        variants.append(("trk126_d16", trk, {"decay": 16}))
    # hump + ts_rank 组合
    if trk != base_expr:
        variants.append(("hump_trk126", f"hump({trk}, hump=0.01)", {"decay": 16}))
    for label, expr, override in variants:
        settings = SETTINGS.copy()
        settings.update(override)
        logger.info("[%s #%d] Stage4 [%s] %s", ds_conf["prefix"], sn, label, expr[:80])
        try:
            res = api.run_backtest(expr, settings=settings)
        except Exception as e:
            logger.warning("[%s #%d] Stage4 [%s] 异常: %s", ds_conf["prefix"], sn, label, e)
            continue
        if not res or not res.get("platform_id"):
            continue
        vpid = res["platform_id"]
        vdet = api.get_alpha_details(vpid)
        vis_ = vdet.get("is") or {}
        try:
            vch = api.get_alpha_check(vpid)
        except Exception:
            continue
        _update_ds_stats(ds_conf["id"], _to_float(vis_.get("sharpe")))
        ok_c, cf = check_cheap_gates(vis_, vch)
        vs = _to_float(vis_.get("sharpe")) or 0.0
        vtvr = _to_float(vis_.get("turnover"))
        vts = "%.1f%%" % (vtvr * 100) if vtvr is not None else "?"
        if not ok_c:
            logger.info("[%s #%d] Stage4 [%s] 不达标 S=%.3f TVR=%s | %s",
                        ds_conf["prefix"], sn, label, vs, vts, "; ".join(cf)[:120])
            continue
        logger.info("[%s #%d] Stage4 [%s] 廉价闸门通过 S=%.3f TVR=%s，等PC...",
                    ds_conf["prefix"], sn, label, vs, vts)
        vpc = wait_for_production_correlation(api, vpid)
        if vpc is None or vpc >= MAX_PROD_CORR:
            logger.info("[%s #%d] Stage4 [%s] PC 未出或超标", ds_conf["prefix"], sn, label)
            continue
        try:
            vch2 = api.get_alpha_check(vpid)
        except Exception:
            vch2 = vch
        ok_f, ff = evaluate_hard_gates(vis_, vch2)
        if not ok_f:
            logger.info("[%s #%d] Stage4 [%s] 最终闸门不达标 | %s",
                        ds_conf["prefix"], sn, label, "; ".join(ff)[:120])
            continue
        rec = {
            "dataset_id": ds_conf["id"],
            "platform_alpha_id": vpid,
            "expression": expr,
            "pair_idx": -1,
            "sharpe": vs,
            "fitness": _to_float(vis_.get("fitness")) or 0.0,
            "production_correlation": vpc,
            "self_correlation": parse_self_correlation(vch2),
            "found_at": datetime.now().isoformat(),
            "sim_number": sn,
            "stage4_variant": label,
        }
        logger.info("[%s #%d] Stage4 [%s] ✅✅ 全部硬闸门通过！S=%.3f TVR=%s PC=%.4f",
                    ds_conf["prefix"], sn, label, vs, vts, vpc)
        return rec
    logger.info("[%s #%d] Stage4 扫描完毕，%d 条变体无通过", ds_conf["prefix"], sn, len(variants))
    return None

def backtest_one(api, ds_conf, pair_idx, expr, sn):
    logger.info("[%s #%d] %s", ds_conf["prefix"], sn, expr[:95])
    try:
        res = api.run_backtest(expr, settings=SETTINGS.copy())
    except Exception as e:
        logger.warning("[%s #%d] 回测异常: %s", ds_conf["prefix"], sn, e)
        return None
    if not res or not res.get("platform_id"):
        return None
    pid = res["platform_id"]
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s_val = _to_float(is_.get("sharpe")) or 0.0
    _update_ds_stats(ds_conf["id"], s_val)
    try:
        ch = api.get_alpha_check(pid)
    except Exception as e:
        logger.warning("[%s #%d] 检查异常: %s", ds_conf["prefix"], sn, e)
        return None
    # ── 廉价闸门（PC 等待前）── 不达标直接放弃，省去昂贵的 PC 等待配额 ──
    ok_cheap, cheap_fails = check_cheap_gates(is_, ch)
    if not ok_cheap:
        # Stage 4 触发（workflow Stage 4）：Sharpe≥0.9 但 TVR/Margin 不达标 → 自动参数扫描
        if s_val >= STAGE4_SHARPE_TRIGGER:
            logger.info("[%s #%d] 廉价闸门不达标但 Sharpe=%.3f≥%.1f，触发 Stage 4 参数扫描...",
                        ds_conf["prefix"], sn, s_val, STAGE4_SHARPE_TRIGGER)
            return stage4_sweep(api, ds_conf, expr, is_, sn)
        logger.info("[%s #%d] 廉价闸门不达标 -> 不提交 | %s",
                    ds_conf["prefix"], sn, "; ".join(cheap_fails)[:220])
        return None
    s_now = _to_float(is_.get("sharpe")) or 0.0
    f_now = _to_float(is_.get("fitness")) or 0.0
    logger.info("[%s #%d] 廉价闸门通过 S=%.3f F=%.3f，等待生产相关性...",
                ds_conf["prefix"], sn, s_now, f_now)
    # ── 生产相关性（用户强制硬约束，绝对红线）──
    pc = wait_for_production_correlation(api, pid)
    if pc is None:
        logger.warning("[%s #%d] 生产相关性未出（超时），按规则【不提交】%s",
                       ds_conf["prefix"], sn, pid)
        return None
    if pc >= MAX_PROD_CORR:
        logger.info("[%s #%d] 生产相关性 %.4f >= %.2f，按规则【不提交】%s",
                    ds_conf["prefix"], sn, pc, MAX_PROD_CORR, pid)
        return None
    # ── 复取检查（此时 SelfCorr 多半已算出），做最终硬闸门 ──
    try:
        ch2 = api.get_alpha_check(pid)
    except Exception:
        ch2 = ch
    ok_final, final_fails = evaluate_hard_gates(is_, ch2)
    if not ok_final:
        logger.info("[%s #%d] 最终硬闸门不达标 -> 不提交 %s | %s",
                    ds_conf["prefix"], sn, pid, "; ".join(final_fails)[:220])
        return None
    rec = {
        "dataset_id": ds_conf["id"],
        "platform_alpha_id": pid,
        "expression": expr,
        "pair_idx": pair_idx,
        "sharpe": s_now,
        "fitness": f_now,
        "production_correlation": pc,
        "self_correlation": parse_self_correlation(ch2),
        "found_at": datetime.now().isoformat(),
        "sim_number": sn,
    }
    logger.info("[%s #%d] ✅ 全部硬闸门通过，可提交 | id=%s | S=%.3f F=%.3f PC=%.4f",
                ds_conf["prefix"], sn, pid, rec["sharpe"], rec["fitness"], pc)
    return rec

def submit_one(api, rec, idx):
    pid = rec["platform_alpha_id"]
    # 防御性终审：提交（设 GREEN）前再核一次硬闸门，
    # 绝不把“未达硬性标准”的 alpha 推上平台。
    try:
        det = api.get_alpha_details(pid)
        ch = api.get_alpha_check(pid)
        ok, fails = evaluate_hard_gates(det.get("is") or {}, ch)
        if not ok:
            logger.warning("   终审未过，放弃提交 %s | %s", pid, "; ".join(fails)[:220])
            return rec
    except Exception as e:
        logger.warning("   终审异常，放弃提交 %s: %s", pid, e)
        return rec
    ds_conf = DATASETS[rec["dataset_id"]]
    name = f"{ds_conf['prefix']}_ppa{idx}_USA_SUBIND"
    name = name[:60]
    desc = ds_conf["desc_idea"]
    props = {"name": name, "tags": ["PowerPoolSelected"], "regular.description": desc}
    try:
        ok = update_alpha_properties(pid, props, session=api.session)
        logger.info("    设置属性 %s -> %s", pid, "OK" if ok else "FAIL")
    except Exception as e:
        logger.warning("    设置属性异常: %s", e)
    try:
        update_alpha_properties(pid, {"color": "GREEN"}, session=api.session)
        logger.info("    设置 color=GREEN %s", pid)
    except Exception as e:
        logger.warning("    设置颜色异常: %s", e)
    rec["name"] = name
    rec["description"] = desc
    rec["color"] = "GREEN"
    return rec

def mine_pass(api, ds_id, ds_conf, found, lock, extended=False):
    bf = ds_conf["backfill"]
    ft = ds_conf.get("field_type", "MATRIX")
    va = ds_conf.get("vec_agg", "vec_avg")
    rng = random.Random(1234)
    exprs = []
    for pi, (a, b) in enumerate(ds_conf["pairs"]):
        for e in build_exprs_for_pair(a, b, bf, extended=extended, field_type=ft, vec_agg=va):
            exprs.append((pi, e))
    # 去重：跳过已找到（已提交）的表达式，避免重循环时重复占用配额槽位
    skip = {r.get("expression") for r in found if r.get("expression")}
    seen = set(); uniq = []
    for pi, e in exprs:
        if e not in seen and e not in skip:
            seen.add(e); uniq.append((pi, e))
    rng.shuffle(uniq)
    logger.info("[%s] 本程表达式池: %d 条（去重后）| 廉价闸门 S>=%.2f F>=%.2f | 硬闸门 PC<%.2f SC<%.2f | 并发=%d",
                ds_conf["prefix"], len(uniq), PRE_SHARPE, PRE_FITNESS,
                MAX_PROD_CORR, SELF_CORR_MAX, MAX_WORKERS_PER_DS)
    total = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_PER_DS,
                            thread_name_prefix=ds_conf["prefix"]) as ex:
        futs = {}
        for pi, e in uniq:
            with lock:
                if len(found) >= TARGET_COUNT:
                    break
                total += 1
                sn = total
            futs[ex.submit(backtest_one, api, ds_conf, pi, e, sn)] = (pi, e)
        for fut in as_completed(futs):
            with lock:
                if len(found) >= TARGET_COUNT:
                    for f in futs:
                        f.cancel()
                    break
            try:
                rec = fut.result()
            except Exception as e:
                logger.warning("[%s] future 异常: %s", ds_conf["prefix"], e)
                continue
            if rec:
                with lock:
                    if len(found) >= TARGET_COUNT:
                        break
                    found.append(rec)
                    logger.info("🎯 全局已找到 %d/%d 个可提交 alpha",
                                len(found), TARGET_COUNT)
                    submit_one(api, rec, len(found))
                with lock:
                    if len(found) >= TARGET_COUNT:
                        for f in futs:
                            f.cancel()
                        break
    return len(found)

def mine_dataset(ds_id, ds_conf, found, lock):
    """单数据集挖掘线程：自有会话，挖到全局目标即停。

    含 workflow Stage 3.3 快速失败：连续 FAST_FAIL_BATCH 条最高 Sharpe < 0.7
    → 标记 PROBABLE_FAIL，切换数据集（不再在死数据集上空转）。
    含无限重循环：配额被孤儿模拟占满时 sleep 后重试。
    """
    ds_conf = dict(ds_conf); ds_conf["id"] = ds_id
    logger.info("▶ 启动数据集线程 %s (%s) [%s]", ds_id, ds_conf["name"],
                ds_conf.get("field_type", "MATRIX"))
    api = WqApiSimple()
    MAX_LOOPS = 40
    loop = 0
    while True:
        with lock:
            if len(found) >= TARGET_COUNT:
                break
        loop += 1
        if loop > MAX_LOOPS:
            logger.info("[%s] 已达最大循环 %d，退出线程", ds_conf["prefix"], MAX_LOOPS)
            break
        # Stage 3.3 快速失败检查
        if _check_fast_fail(ds_id):
            with _stats_lock:
                st = _ds_stats.get(ds_id, {})
            logger.warning("[%s] ⚠️ Stage 3.3 快速失败：%d 条回测最高 Sharpe=%.3f < %.1f "
                           "→ PROBABLE_FAIL，切换数据集",
                           ds_conf["prefix"], st.get("total_bt", 0),
                           st.get("max_sharpe", -9), FAST_FAIL_SHARPE)
            break
        logger.info("▶ [%s] 挖掘循环 #%d", ds_conf["prefix"], loop)
        # Pass 1：核心范式（降换手优先）
        mine_pass(api, ds_id, ds_conf, found, lock, extended=False)
        with lock:
            if len(found) >= TARGET_COUNT:
                break
        # 再次检查快速失败（Pass 1 可能已累积足够样本）
        if _check_fast_fail(ds_id):
            with _stats_lock:
                st = _ds_stats.get(ds_id, {})
            logger.warning("[%s] ⚠️ Stage 3.3 快速失败（Pass1后）：%d 条最高 Sharpe=%.3f < %.1f "
                           "→ PROBABLE_FAIL，切换",
                           ds_conf["prefix"], st.get("total_bt", 0),
                           st.get("max_sharpe", -9), FAST_FAIL_SHARPE)
            break
        # Pass 2：扩展范式
        mine_pass(api, ds_id, ds_conf, found, lock, extended=True)
        with lock:
            done = len(found) >= TARGET_COUNT
        if done:
            break
        wait_s = 300
        logger.info("[%s] 本轮未集满，%ss 后重新循环", ds_conf["prefix"], wait_s)
        time.sleep(wait_s)
    logger.info("■ 数据集线程 %s 结束（全局已找到 %d/%d）",
                ds_conf["prefix"], len(found), TARGET_COUNT)

def write_outputs(found):
    os.makedirs("results", exist_ok=True)
    os.makedirs("tracking", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join("results", f"usa_ppa_multi_{ts}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "datasets": list(DATASETS.keys()),
            "region": REGION, "universe": UNIVERSE, "delay": DELAY,
            "neutralization": NEUT, "decay": DECAY,
            "target": TARGET_COUNT, "found": len(found),
            "max_prod_corr": MAX_PROD_CORR,
            "submitted_alphas": found,
        }, f, indent=2, ensure_ascii=False)
    tpath = os.path.join("tracking", f"{ts}_multi_USA_PPA.md")
    lines = ["## 提交记录 (USA/D1 PPA, 多未点亮数据集)", "",
             f"- 数据集: {', '.join(DATASETS.keys())}",
             f"- 区域/宇宙/延迟: {REGION}/{UNIVERSE}/D{DELAY}",
             f"- 中性化/衰减: {NEUT}/{DECAY} | 截断: {TRUNCATION}",
             f"- 找到可提交 alpha: {len(found)}/{TARGET_COUNT}",
             f"- 硬闸门: 生产相关性必须出且 < {MAX_PROD_CORR}（否则绝不提交）", "",
             "| # | 数据集 | Alpha ID | Expression | Sharpe | Fitness | ProdCorr |",
             "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(found, 1):
        lines.append(f"| {i} | {r['dataset_id']} | {r['platform_alpha_id']} | "
                     f"{r['expression']} | {r['sharpe']:.3f} | {r['fitness']:.3f} | "
                     f"{r['production_correlation']:.4f} |")
    with open(tpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("结果已写入 %s", out)
    logger.info("跟踪记录已写入 %s", tpath)

def main():
    logger.info("=" * 78)
    logger.info("USA/D1 多未点亮数据集(PPA) 双字段挖掘 | 数据集=%s",
                ", ".join(DATASETS.keys()))
    logger.info("约束: 每个 alpha 仅用【单数据集】内双字段；生产相关性必须出且 < %.2f",
                MAX_PROD_CORR)
    logger.info("全局目标: 跨数据集找到 %d 个可提交 alpha 即停", TARGET_COUNT)
    logger.info("=" * 78)
    found = []
    lock = Lock()
    threads = []
    for ds_id, ds_conf in DATASETS.items():
        t = ThreadPoolExecutor(max_workers=1)
        # 用线程跑每个数据集（各自独立会话），主线程等待
        fut = t.submit(mine_dataset, ds_id, ds_conf, found, lock)
        threads.append((ds_id, t, fut))
    for ds_id, t, fut in threads:
        try:
            fut.result()
        except Exception as e:
            logger.warning("数据集 %s 线程异常: %s", ds_id, e)
        t.shutdown(wait=False)
    write_outputs(found)
    logger.info("=" * 78)
    logger.info("完成 | 可提交 alpha: %d/%d", len(found), TARGET_COUNT)
    for i, r in enumerate(found, 1):
        logger.info("  [%d] %s | id=%s | S=%.3f F=%.3f PC=%.4f | %s",
                    i, r["dataset_id"], r["platform_alpha_id"], r["sharpe"],
                    r["fitness"], r["production_correlation"], r["expression"][:70])

if __name__ == "__main__":
    main()
