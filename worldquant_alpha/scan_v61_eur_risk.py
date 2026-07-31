#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V61: EUR/D1 risk62+risk68 (风险模型残差/风格暴露) 挖掘.

用户指令: 保留 BATCH=8 但 LANES=2, 换 EUR 去挖掘.
选型: EUR 未点亮池仅 6 个全 risk 系 — risk62 主攻(233字段/cov=0.997/vs=2.0),
risk68 副攻(5字段/cov=1.0/219u/361a 竞争最低); 排除 risk70(19万alpha重灾区)/
risk72(旧脚本挖过且cov=0.60)/imbalance5(仅2字段cov=0.55).
主线: A)残差收益短反转(rsk68_residual_return/回归截距) B)低特质风险异象(ksrs负向)
C)style exposure(mtl动量/mts反转/低vol/pb价值, a仅47-82极低拥挤) D)rsk62_return探针.

用户硬约束:
- REGULAR, delay=1, maxTrade=OFF; universe TOP2500 (robust探针换TOP800)
- IS: Sharpe>1.58, Fitness>1, 2Y-Sharpe>1.6, Margin>10bp, 5%<TVR<30%
- risk-neut(MARKET): Sharpe>1, Fitness>0.7, Margin>10bp
- 操作符数 <6; 单数据集 1-2 字段; 禁 trade_when/add()/multiply() (组合仅用减号 spread 形式)
- PROD_CORR 必须已出且 <0.7 才算候选 (<0.4 目标彼此独立); 绝不提交 (手动提交)
- multi-sim 2 车道流水线; 提交经 submit_gate 全局串行错峰 ≥32s; 每 10 批做多样性评估
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

LOG_PATH = os.path.join(_HERE, "results", "v61_eur_risk.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("v61")

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, envelope_summary, run_multi_batch, chunked
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
N_LANES = int(os.environ.get("V53_LANES", "2"))  # 用户指示: 保留 BATCH=8 但 LANES=2
COOLDOWN = float(os.environ.get("V53_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
CKPT = os.path.join(_HERE, "results", "v61_eur_risk_checkpoint.json")
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
DIVERSITY = os.path.join(_HERE, "results", "v61_diversity_report.jsonl")
DATASET = "risk62+risk68"

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
        "instrumentType": "EQUITY", "region": "EUR", "universe": uni, "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc,
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "ON",
        "language": "FASTEXPR", "visualization": False, "testPeriod": "P6Y", "maxTrade": "OFF",
    }


# ---------------- 模板族 v61a: 首轮 — 残差反转/低风险/style exposure/模型预测探针
# 字段全 MATRIX cov 0.93-1.0. EUR 经验: SUBINDUSTRY neut + trunc 0.08 (旧 PPA 验证).
STYLES: Dict[str, List[Tuple[str, str]]] = {
    # A) 残差收益短反转 (risk68 竞争最低 + risk62 回归截距同义对照)
    "res": [
        ("resP_r68s5", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 5), subindustry)"),
        ("resP_r68s10", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 10), subindustry)"),
        ("resR_r68s5", "rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 5))"),
        ("resP_i62s5", "group_rank(-ts_sum(ts_backfill(rsk62_1_1_100_intercept, 5), 5), subindustry)"),
        ("resP_i62As5", "group_rank(-ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 5), subindustry)"),
        ("resP_r68z22", "group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 5), 22), subindustry)"),
    ],
    # B) 低特质风险异象 (ksrs 负向, 慢信号)
    "ksr": [
        ("ksrP_62", "group_rank(-ts_mean(ts_backfill(rsk62_1_100_ksrs, 22), 22), subindustry)"),
        ("ksrR_62", "rank(-ts_mean(ts_backfill(rsk62_1_100_ksrs, 22), 22))"),
        ("ksrP_62b", "group_rank(-ts_mean(ts_backfill(rsk62_1_1_100_ksrs, 22), 22), subindustry)"),
    ],
    # C) style exposure (a≤47-82 极低拥挤): 长动量+/短动量反转-/低vol-/价值+
    "sty": [
        ("styP_mtl", "group_rank(ts_mean(ts_backfill(rsk62_risk_mtl, 22), 5), subindustry)"),
        ("styP_mts", "group_rank(-ts_mean(ts_backfill(rsk62_risk_mts, 22), 5), subindustry)"),
        ("styP_vol", "group_rank(-ts_mean(ts_backfill(rsk62_risk_volatility, 22), 5), subindustry)"),
        ("styP_pb", "group_rank(ts_mean(ts_backfill(rsk62_risk_pb, 22), 5), subindustry)"),
        ("styP_mspr", "group_rank(ts_mean(ts_backfill(rsk62_risk_mtl, 22), 5) - ts_mean(ts_backfill(rsk62_risk_mts, 22), 5), subindustry)"),
    ],
    # D) rsk62_return 模型 1 天期预测探针 (a=737 略拥挤, 正/反两向)
    "ret": [
        ("retP_p5", "group_rank(ts_mean(ts_backfill(rsk62_return, 5), 5), subindustry)"),
        ("retP_rev5", "group_rank(-ts_sum(ts_backfill(rsk62_return, 5), 5), subindustry)"),
    ],
    # ---- v61b: 二轮 — 首轮诊断: res方向对但M=3-4bp太薄; ksr M=11-13bp过线但S低/TVR低;
    # i62截距应做动量(反转为负); sty全灭结案. 杠杆: 长窗口降TVR提M + pw尾部集中 + country 骨架.
    # E) 长窗口残差反转 (降TVR提Margin; z189=旧EUR PPA范式正反两向)
    "res2": [
        ("res2P_r68s20", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 20), subindustry)"),
        ("res2P_r68s60", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 60), subindustry)"),
        ("res2P_r68z189", "group_rank(ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 189), subindustry)"),
        ("res2P_r68z189n", "group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 189), subindustry)"),
        ("res2W_r68pw", "signed_power(group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 5), subindustry) - 0.5, 2)"),
    ],
    # F) 截距动量 (首轮反转为负 -> 翻正号拉长窗口)
    "i62m": [
        ("i62mP_s20", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 20), subindustry)"),
        ("i62mP_s60", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 60), subindustry)"),
        ("i62mP_b_s20", "group_rank(ts_sum(ts_backfill(rsk62_1_1_100_intercept, 5), 20), subindustry)"),
    ],
    # G) country 骨架对照 (EUR 多国别, 类比 GLB group_rank(market) 决定性验证)
    "cty": [
        ("ctyP_r68s10", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 10), country)"),
        ("ctyP_ksr", "group_rank(-ts_mean(ts_backfill(rsk62_1_100_ksrs, 22), 5), country)"),
    ],
    # H) ksr 提速版 (快平滑提TVR过5%地板) + pw 尾部集中提S/M
    "ksr2": [
        ("ksr2P_f5", "group_rank(-ts_mean(ts_backfill(rsk62_1_100_ksrs, 22), 5), subindustry)"),
        ("ksr2W_pw", "signed_power(group_rank(-ts_mean(ts_backfill(rsk62_1_100_ksrs, 22), 5), subindustry) - 0.5, 2)"),
    ],
    # ---- v61c: 三轮 — v61b诊断: i62动量窗口单调走强(s60 S=1.07/M=27.7bp 但TVR=3%);
    # country骨架抬升反转(1.38>1.26); z189n S=1.40但M薄; pw高TVR下反M证伪.
    # I) i62 动量强化: country骨架/更长窗/zscore提TVR/长短spread提TVR
    "i62c": [
        ("i62cC_s60", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 60), country)"),
        ("i62cC_s120", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 120), country)"),
        ("i62cP_s120", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 120), subindustry)"),
        ("i62cP_z60", "group_rank(ts_zscore(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 60), 60), subindustry)"),
        ("i62cP_sp", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 60) - ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 5), subindustry)"),
    ],
    # J) ILLIQUID_MINVOL1M 宇宙探针: 流动性差 -> 反转Margin天然高 (M 4bp->10bp 最硬杠杆)
    "ill": [
        ("illP_r68s10", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 10), subindustry)"),
        ("illC_r68s10", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 10), country)"),
        ("illP_i62s60", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 60), subindustry)"),
    ],
    # K) country 反转配大 decay 12/16 压TVR提M
    "cty2": [
        ("cty2C_r68s10", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 10), country)"),
        ("cty2C_r68z189n", "group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 189), country)"),
    ],
    # ---- v61d: 四轮 — v61c诊断: cty2 z189n d12 S=1.49/M=6.2 最强线(decay↑→M↑单调);
    # ILLIQUID证伪结案(M反降); i62动量S峰值1.10/TVR地板卡死. 新弹药: beta(a=62)/短波动(a=52).
    # L) z189n 冲顶: decay 20/24 + 长窗z250
    "z3": [
        ("z3C_z189", "group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 189), country)"),
        ("z3C_z250", "group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 250), country)"),
    ],
    # M) z189n 宽截断 0.15 提集中度提Margin
    "z3t": [
        ("z3tC_z189", "group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 189), country)"),
    ],
    # N) z189n + pw 尾部集中 (低TVR下重试pw, v61b高TVR下失败)
    "z3w": [
        ("z3wC_pw", "signed_power(group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 189), country) - 0.5, 2)"),
    ],
    # O) 低beta异象 BAB (a=62 极低拥挤, 慢信号高Margin潜力)
    "bab": [
        ("babP", "group_rank(-ts_mean(ts_backfill(rsk68_beta, 5), 22), subindustry)"),
        ("babC", "group_rank(-ts_mean(ts_backfill(rsk68_beta, 5), 22), country)"),
    ],
    # P) 低短期波动异象 (a=52)
    "lvs": [
        ("lvsP", "group_rank(-ts_mean(ts_backfill(rsk68_weight_volatility_short, 5), 22), subindustry)"),
        ("lvsC", "group_rank(-ts_mean(ts_backfill(rsk68_weight_volatility_short, 5), 22), country)"),
    ],
    # Q) 反转-低波 spread (同数据集2字段, 减号形式, 5操作符)
    "vrs": [
        ("vrsC", "group_rank(-ts_sum(ts_backfill(rsk68_residual_return, 5), 10), country) - group_rank(ts_mean(rsk68_weight_volatility_short, 22), country)"),
    ],
    # ---- v61e: 五轮 — v61d诊断: z189n天花板 S=1.49/M~8bp; trunc/pw/bab/lvs证伪.
    # 破局: risk62内双字段spread = 慢动量腿(M=26bp/TVR=3%) - 快反转腿(S=1.18/TVR=32%), 两腿互补.
    # R) 动量-反转 spread (cov=1.0 字段省去 backfill 控操作符数=4)
    "mix": [
        ("mixP_60_5", "group_rank(ts_sum(rsk62_1_100_intercept, 60), subindustry) - group_rank(ts_sum(rsk62_return, 5), subindustry)"),
        ("mixC_60_5", "group_rank(ts_sum(rsk62_1_100_intercept, 60), country) - group_rank(ts_sum(rsk62_return, 5), country)"),
        ("mixP_120_5", "group_rank(ts_sum(rsk62_1_100_intercept, 120), subindustry) - group_rank(ts_sum(rsk62_return, 5), subindustry)"),
        ("mixP_60_10", "group_rank(ts_sum(rsk62_1_100_intercept, 60), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
    ],
    # S) settings 级 COUNTRY 中性化对照 (此前仅表达式内 country group)
    "z4": [
        ("z4C_z189", "group_rank(-ts_zscore(ts_sum(ts_backfill(rsk68_residual_return, 5), 10), 189), country)"),
    ],
    "i62n": [
        ("i62nP_s60", "group_rank(ts_sum(ts_backfill(rsk62_1_100_intercept, 5), 60), subindustry)"),
    ],
    # ---- v61f: 六轮 — v61e突破: mixP_60_10 d4 S=1.87/F=1.15/TVR=21% 只Margin差(7.6<10).
    # 规律: 反转腿放慢+decay↑ => M单调上(3.2->7.6). 冲刺: 腿更慢 + d8/12 + country版.
    "mix2": [
        ("mix2P_60_20", "group_rank(ts_sum(rsk62_1_100_intercept, 60), subindustry) - group_rank(ts_sum(rsk62_return, 20), subindustry)"),
        ("mix2P_120_10", "group_rank(ts_sum(rsk62_1_100_intercept, 120), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
        ("mix2C_60_10", "group_rank(ts_sum(rsk62_1_100_intercept, 60), country) - group_rank(ts_sum(rsk62_return, 10), country)"),
        ("mix2C_120_10", "group_rank(ts_sum(rsk62_1_100_intercept, 120), country) - group_rank(ts_sum(rsk62_return, 10), country)"),
    ],
    "mix3": [
        ("mix3P_60_10", "group_rank(ts_sum(rsk62_1_100_intercept, 60), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
        ("mix3C_60_5", "group_rank(ts_sum(rsk62_1_100_intercept, 60), country) - group_rank(ts_sum(rsk62_return, 5), country)"),
    ],
    # ---- v61g: 七轮 — v61f: S/F/M/TVR全破(mix2C_120_10_d8 S=2.01/F=1.52/M=11.4), 卡 2Y=0.5-0.71<<1.6.
    # 对策: 动量腿短窗适应更快(20/40d) + ksrs稳定腿替换动量腿.
    "mixg": [
        ("mixgP_20_10", "group_rank(ts_sum(rsk62_1_100_intercept, 20), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
        ("mixgP_40_10", "group_rank(ts_sum(rsk62_1_100_intercept, 40), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
    ],
    "kmix": [
        ("kmixP_22_10", "group_rank(-ts_mean(ts_backfill(rsk62_1_100_ksrs, 22), 22), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
        ("kmixC_22_10", "group_rank(-ts_mean(ts_backfill(rsk62_1_100_ksrs, 22), 22), country) - group_rank(ts_sum(rsk62_return, 10), country)"),
    ],
    # ---- v61h: 八轮 — 2Y衰减专项: 换B族截距字段(不同估计窗口) + 换TOP1200人群(顺带修SUB_UNI).
    "mixb": [
        ("mixbP_60_10", "group_rank(ts_sum(rsk62_1_1_100_intercept, 60), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
        ("mixbC_120_10", "group_rank(ts_sum(rsk62_1_1_100_intercept, 120), country) - group_rank(ts_sum(rsk62_return, 10), country)"),
    ],
    "mixu": [
        ("mixuP_60_10", "group_rank(ts_sum(rsk62_1_100_intercept, 60), subindustry) - group_rank(ts_sum(rsk62_return, 10), subindustry)"),
        ("mixuC_120_10", "group_rank(ts_sum(rsk62_1_100_intercept, 120), country) - group_rank(ts_sum(rsk62_return, 10), country)"),
    ],
    # ---- v61i: 九轮 — mix线2Y结构性衰减判死(mixb 2Y=0.16/mixu塌掉). 新弹药: risk60借券费率
    # (short-fee premium 经典异象, 高fee=>负超额; offer a=546/crowding a=190/lending_bid a=23 低拥挤)
    "sho": [
        ("shoP_lvl", "group_rank(-ts_mean(ts_backfill(rsk60_offer, 10), 22), subindustry)"),
        ("shoC_lvl", "group_rank(-ts_mean(ts_backfill(rsk60_offer, 10), 22), country)"),
        ("shoP_last", "group_rank(-ts_mean(ts_backfill(rsk60_last, 10), 22), subindustry)"),
        ("shoP_chg", "group_rank(-ts_delta(ts_mean(ts_backfill(rsk60_offer, 10), 5), 22), subindustry)"),
        ("crwP", "group_rank(-ts_mean(ts_backfill(rsk60_crowding, 10), 22), subindustry)"),
        ("lfbP", "group_rank(-ts_mean(ts_backfill(lending_fee_bid_rate, 10), 22), subindustry)"),
    ],
    # ---- v61i-fix: rsk60 是 event 输入, ts_backfill 不支持 -> 直接 ts_mean 平滑
    "sho2": [
        ("sho2P_lvl", "group_rank(-ts_mean(rsk60_offer, 22), subindustry)"),
        ("sho2C_lvl", "group_rank(-ts_mean(rsk60_offer, 22), country)"),
        ("sho2P_last", "group_rank(-ts_mean(rsk60_last, 22), subindustry)"),
        ("sho2P_chg", "group_rank(-ts_delta(ts_mean(rsk60_offer, 5), 22), subindustry)"),
        ("crw2P", "group_rank(-ts_mean(rsk60_crowding, 22), subindustry)"),
        ("lfb2P", "group_rank(-ts_mean(lending_fee_bid_rate, 22), subindustry)"),
    ],
    # ---- v61i-fix2: rsk60 全部是 VECTOR(events vector) 输入, 常规算子不兼容
    # -> 必须先 vec_avg 聚合成 matrix (探针 3ODhfm6Z34E9b0cgsgilkmP 已验证 COMPLETE)
    "sho3": [
        ("sho3P_lvl", "group_rank(-ts_mean(vec_avg(rsk60_offer), 22), subindustry)"),
        ("sho3C_lvl", "group_rank(-ts_mean(vec_avg(rsk60_offer), 22), country)"),
        ("sho3P_last", "group_rank(-ts_mean(vec_avg(rsk60_last), 22), subindustry)"),
        ("sho3P_chg", "group_rank(-ts_delta(ts_mean(vec_avg(rsk60_offer), 5), 22), subindustry)"),
        ("crw3P", "group_rank(-ts_mean(vec_avg(rsk60_crowding), 22), subindustry)"),
        ("lfb3P", "group_rank(-ts_mean(vec_avg(lending_fee_bid_rate), 22), subindustry)"),
    ],
    # ---- v61j: sho3诊断: shoC_lvl S=0.80/M=13.7-16.3bp 全族最强(country骨架再验证);
    # 病灶=S天花板0.8+TVR 3-4%卡地板. 对策: z189n范式冲S + 快平滑/vec_max/费率动量提TVR
    "sho4": [
        ("sho4C_z189", "group_rank(-ts_zscore(ts_mean(vec_avg(rsk60_offer), 22), 189), country)"),
        ("sho4C_z60", "group_rank(-ts_zscore(ts_mean(vec_avg(rsk60_offer), 22), 60), country)"),
        ("sho4P_z189", "group_rank(-ts_zscore(ts_mean(vec_avg(rsk60_offer), 22), 189), subindustry)"),
        ("sho4C_f5", "group_rank(-ts_mean(vec_avg(rsk60_offer), 5), country)"),
        ("sho4C_max", "group_rank(-ts_mean(vec_max(rsk60_offer), 22), country)"),
        ("sho4C_mom60", "group_rank(-ts_delta(ts_mean(vec_avg(rsk60_offer), 22), 60), country)"),
    ],
}

UNIVERSES = ["TOP2500"]
DECAYS = [0, 4]
# EUR 旧 PPA 经验: SUBINDUSTRY 主战场; COUNTRY 留二轮
NEUTS = ["SUBINDUSTRY"]
TRUNCS = [0.08]
MAX_VARIANTS = int(os.environ.get("V53_MAX_VARIANTS", "560"))

# 每风格覆盖 (universe/decay/neut), 未列出的风格沿用全局默认
STYLE_OVERRIDES: Dict[str, Dict[str, list]] = {
    # 日频反转/预测信号快 -> 大 decay 控 TVR
    "res": {"decays": [4, 8]},
    "ret": {"decays": [4, 8]},
    "res2": {"decays": [4, 8]},
    "cty": {"decays": [4, 8]},
    # v61c
    "i62c": {"decays": [0]},
    "ill": {"universes": ["ILLIQUID_MINVOL1M"], "decays": [4, 8]},
    "cty2": {"decays": [12, 16]},
    # v61d
    "z3": {"decays": [20, 24]},
    "z3t": {"decays": [12, 16], "truncs": [0.15]},
    "z3w": {"decays": [12, 16]},
    "bab": {"decays": [0]},
    "lvs": {"decays": [0]},
    "vrs": {"decays": [8, 12]},
    # v61e
    "mix": {"decays": [0, 4]},
    "z4": {"decays": [12, 20], "neuts": ["COUNTRY"]},
    "i62n": {"decays": [0], "neuts": ["COUNTRY", "MARKET"]},
    # v61f: mix胜者骨架冲Margin
    "mix2": {"decays": [4, 8]},
    "mix3": {"decays": [8, 12]},
    # v61g: 冲2Y-Sharpe
    "mixg": {"decays": [8, 12]},
    "kmix": {"decays": [8, 12]},
    # v61h: 2Y衰减专项
    "mixb": {"decays": [8, 12]},
    "mixu": {"universes": ["TOP1200"], "decays": [8, 12]},
    # v61i: risk60 借券费率
    "sho": {"decays": [0, 4]},
    "sho2": {"decays": [0, 4]},
    "sho3": {"decays": [0, 4]},
    "sho4": {"decays": [0, 4]},
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
    alt_uni = "TOP800" if base_s["universe"] == "TOP2500" else "TOP2500"
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
                "region": "EUR", "submitted": False,
                "tags": ["v61", DATASET, "EUR_D1", "READY_MANUAL", "NO_SUBMIT"],
            }
            set_props(api, r["pid"], f"v61_{r['label']}", info["tags"],
                      f"EUR D1 unlit pyramid {DATASET}. {r['style']}. NO AUTO SUBMIT.")
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
    logger.info("V61 EUR risk62+risk68 | %d variants | lanes=%d | %s",
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
