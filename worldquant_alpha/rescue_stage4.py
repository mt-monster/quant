#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 4 抢救脚本：对最佳候选 alpha（S=1.56, TVR=47.9%）做参数扫描，
用降换手手段（decay 扫描 / hump / ts_rank 长窗口 / ts_mean 平滑 / neut 变体）
把 TVR 从 48% 压到 <20%，同时尽量保留 Sharpe。

基线表达式：rank(ts_zscore(subtract(ts_backfill(inst20_ra_sev, 66),
                                    ts_backfill(inst20_ra_sv, 66), filter=true), 66))
基线设置：USA/TOP3000/D1/decay=4/SUBINDUSTRY/truncation=0.08/FASTEXPR/P5Y
"""
import sys, os, json, time, logging
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rescue")

from wd_lib_wrapper import WqApiSimple
import mine_usa_ppa_multi as m
from wd_lib.api.alphas import update_alpha_properties

# ── 基线表达式组件 ──
A = "ts_backfill(inst20_ra_sev, 66)"
B = "ts_backfill(inst20_ra_sv, 66)"
SPREAD = f"subtract({A}, {B}, filter=true)"
BASE = f"rank(ts_zscore({SPREAD}, 66))"

# 平滑后的字段（ts_mean 22 日滑动平均，降低日频噪音）
A_S = "ts_mean(ts_backfill(inst20_ra_sev, 66), 22)"
B_S = "ts_mean(ts_backfill(inst20_ra_sv, 66), 22)"
SPREAD_S = f"subtract({A_S}, {B_S}, filter=true)"

# ── Stage 4 变体生成 ──
# 策略：从轻到重逐步加压降换手，找到 Sharpe 保留 + TVR<20% 的甜点
VARIANTS = [
    # ── decay 扫描（最直接：decay 越高 TVR 越低）──
    ("d08",       BASE,                                         {"decay": 8}),
    ("d16",       BASE,                                         {"decay": 16}),
    ("d24",       BASE,                                         {"decay": 24}),
    ("d32",       BASE,                                         {"decay": 32}),
    # ── hump 压换手（忽略小幅持仓变动）──
    ("hump01_d04", f"hump({BASE}, 0.01)",                       {"decay": 4}),
    ("hump03_d04", f"hump({BASE}, 0.03)",                       {"decay": 4}),
    ("hump01_d16", f"hump({BASE}, 0.01)",                       {"decay": 16}),
    # ── ts_rank 长窗口替代 ts_zscore（更稳定的截面排名）──
    ("trk126_d04", f"rank(ts_rank({SPREAD}, 126))",              {"decay": 4}),
    ("trk252_d04", f"rank(ts_rank({SPREAD}, 252))",              {"decay": 4}),
    ("trk126_d16", f"rank(ts_rank({SPREAD}, 126))",              {"decay": 16}),
    # ── 组合最佳：ts_rank + hump + 高 decay ──
    ("combo1",     f"hump(rank(ts_rank({SPREAD}, 126)), 0.01)",  {"decay": 16}),
    ("combo2",     f"hump(rank(ts_rank({SPREAD}, 252)), 0.01)",  {"decay": 16}),
    # ── ts_mean 平滑字段后再做 spread（降噪源头）──
    ("tsmean_d08", f"rank(ts_zscore({SPREAD_S}, 66))",           {"decay": 8}),
    ("tsmean_d16", f"rank(ts_zscore({SPREAD_S}, 66))",           {"decay": 16}),
    # ── neut 变体（换中性化层级改变 TVR 分布）──
    ("neutIND_d16", BASE,                                        {"decay": 16, "neutralization": "INDUSTRY"}),
    ("neutSEC_d16", BASE,                                        {"decay": 16, "neutralization": "SECTOR"}),
]

def run_variant(api, label, expr, settings_override):
    """回测单条变体，走完整硬闸门。返回结果 dict 或 None。"""
    settings = m.SETTINGS.copy()
    settings.update(settings_override)
    logger.info("━━━ [%s] decay=%s neut=%s ━━━ %s",
                label, settings_override.get("decay", 4),
                settings_override.get("neutralization", "SUBINDUSTRY"),
                expr[:90])
    try:
        res = api.run_backtest(expr, settings=settings)
    except Exception as e:
        logger.warning("[%s] 回测异常: %s", label, e)
        return None
    if not res or not res.get("platform_id"):
        logger.warning("[%s] 回测无结果", label)
        return None
    pid = res["platform_id"]
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    try:
        ch = api.get_alpha_check(pid)
    except Exception as e:
        logger.warning("[%s] 检查异常: %s", label, e)
        return None
    # 廉价闸门
    ok_cheap, cheap_fails = m.check_cheap_gates(is_, ch)
    s = m._to_float(is_.get("sharpe")) or 0.0
    f = m._to_float(is_.get("fitness")) or 0.0
    tvr = m._to_float(is_.get("turnover"))
    marg = m._to_float(is_.get("margin"))
    tvr_s = "%.1f%%" % (tvr * 100) if tvr is not None else "?"
    marg_s = "%.1fbp" % (marg * 10000) if marg is not None else "?"
    if not ok_cheap:
        logger.info("[%s] 廉价闸门不达标 S=%.3f F=%.3f TVR=%s Margin=%s | %s",
                    label, s, f, tvr_s, marg_s, "; ".join(cheap_fails)[:160])
        return {"label": label, "pid": pid, "expr": expr, "sharpe": s, "fitness": f,
                "tvr": tvr, "margin": marg, "passed": False, "fails": cheap_fails}
    logger.info("[%s] ✅ 廉价闸门通过 S=%.3f F=%.3f TVR=%s Margin=%s，等待生产相关性...",
                label, s, f, tvr_s, marg_s)
    # 生产相关性
    pc = m.wait_for_production_correlation(api, pid)
    if pc is None:
        logger.warning("[%s] 生产相关性未出（超时），不提交", label)
        return {"label": label, "pid": pid, "expr": expr, "sharpe": s, "fitness": f,
                "tvr": tvr, "margin": marg, "passed": False, "fails": ["PC未出"]}
    if pc >= m.MAX_PROD_CORR:
        logger.info("[%s] 生产相关性 %.4f >= %.2f，不提交", label, pc, m.MAX_PROD_CORR)
        return {"label": label, "pid": pid, "expr": expr, "sharpe": s, "fitness": f,
                "tvr": tvr, "margin": marg, "pc": pc, "passed": False, "fails": ["PC=%.4f" % pc]}
    # 最终硬闸门
    try:
        ch2 = api.get_alpha_check(pid)
    except Exception:
        ch2 = ch
    ok_final, final_fails = m.evaluate_hard_gates(is_, ch2)
    if not ok_final:
        logger.info("[%s] 最终硬闸门不达标 | %s", label, "; ".join(final_fails)[:160])
        return {"label": label, "pid": pid, "expr": expr, "sharpe": s, "fitness": f,
                "tvr": tvr, "margin": marg, "pc": pc, "passed": False, "fails": final_fails}
    logger.info("[%s] ✅✅ 全部硬闸门通过！S=%.3f F=%.3f TVR=%s Margin=%s PC=%.4f",
                label, s, f, tvr_s, marg_s, pc)
    return {"label": label, "pid": pid, "expr": expr, "sharpe": s, "fitness": f,
            "tvr": tvr, "margin": marg, "pc": pc, "passed": True, "fails": []}

def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    logger.info("=" * 78)
    logger.info("Stage 4 抢救：S=1.56 候选参数扫描 | %d 条变体（并行）", len(VARIANTS))
    logger.info("目标：TVR 48%%→<20%%，Sharpe 保留 ≥1.58")
    logger.info("=" * 78)
    api = WqApiSimple()
    results = []
    # 并行回测（信号量 C=5 控制在飞数）
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="rescue") as ex:
        futs = {}
        for label, expr, override in VARIANTS:
            futs[ex.submit(run_variant, api, label, expr, override)] = label
        for fut in as_completed(futs):
            label = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                logger.warning("[%s] future 异常: %s", label, e)
                continue
            if r:
                results.append(r)
            if r and r.get("passed"):
                logger.info("🎯 找到通过变体 [%s]，提交中...", label)
                try:
                    props = {"name": f"i20_rescue_{label}_USA_SUBIND"[:60],
                             "tags": ["PowerPoolSelected"],
                             "regular.description": (
                                 "Idea: short-selling pressure signal from institutional short-volume "
                                 "reporting (institutions20). Stage4 rescue variant with dampened "
                                 "turnover via decay/hump/ts_rank. Subindustry neutralized.")}
                    update_alpha_properties(r["pid"], props, session=api.session)
                    update_alpha_properties(r["pid"], {"color": "GREEN"}, session=api.session)
                    logger.info("   已提交 %s color=GREEN", r["pid"])
                except Exception as e:
                    logger.warning("   提交异常: %s", e)
    # 汇总
    logger.info("=" * 78)
    logger.info("Stage 4 扫描完成 | %d 条变体", len(results))
    passed = [r for r in results if r.get("passed")]
    logger.info("通过硬闸门: %d / %d", len(passed), len(results))
    # 按 Sharpe 排序打印全部
    results.sort(key=lambda x: -(x.get("sharpe") or 0))
    for r in results:
        tvr = r.get("tvr")
        marg = r.get("margin")
        tvr_s = "%.1f%%" % (tvr * 100) if tvr is not None else "?"
        marg_s = "%.1fbp" % (marg * 10000) if marg is not None else "?"
        status = "✅PASS" if r.get("passed") else "FAIL"
        logger.info("  %-14s %s S=%-6.3f F=%-6.3f TVR=%-7s M=%-7s | %s",
                    r["label"], status, r.get("sharpe", 0), r.get("fitness", 0),
                    tvr_s, marg_s, "; ".join(r.get("fails", []))[:80])
    # 保存
    os.makedirs("results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/stage4_rescue_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"base_expr": BASE, "variants": results, "passed": len(passed)}, f,
                  indent=2, ensure_ascii=False)
    logger.info("结果已保存 -> %s", out)
    if passed:
        logger.info("🎉 抢救成功！找到 %d 个可提交 alpha", len(passed))

if __name__ == "__main__":
    main()
