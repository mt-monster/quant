#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V57: GLB/D1 未点亮金字塔 dl_riskfree_returns (Deep Learning Risk Free Returns, pm=1.4) 挖掘.

前序: analyst15 三轮 202 变体结案 — S 天花板 0.97(ibeP_w1_TOPD_MARK) 锁死于 1.58 门槛之下.
选型依据: GLB 未点亮(cov=0.97, 57字段, pm=1.4) × USA tri 实测 bestS=2.33(114个变体S>=1.2,
全部候选最强); 骨架 group_zscore(ts_zscore(ts_backfill(f,66),189),industry) USA 已验证.

字段结构: probability_label{k}_{n}quantile_{5/20/60}day_ohlcv_img (log-softmax 概率) +
quantile_label_{n}bucket_*day (预测分位桶序号); 个股级 MATRIX, cov 0.956-1.0.
语义定向: label0(底桶)概率高=看空(取负号), 顶桶概率/bucket序号高=看多(正号).

v57c 三轮 (变换级去相关): a/b 两轮 76 变体 9 条 PASS_CHEAP 全灭于 PC 0.80-0.84,
换冷门字段无效 => 信号级拥挤; 保留唯一 M 达标核 ts_mean(ts_backfill(f,22),5),
外层换 group_rank(subindustry/sector) / SUBI-STAT 中性化 / ts_rank / ts_delta /
signed_power / TOPDIV3000 换池 六族攻 PC (v66 实证 subindustry 降 PC 0.81->0.667).

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

LOG_PATH = os.path.join(_HERE, "results", "v57_glb_dlrfr.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("v57")

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, envelope_summary, run_multi_batch, chunked
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
N_LANES = int(os.environ.get("V53_LANES", "7"))  # 用户指示: 8 个 lane 先只开 7 个 (探索车道)
N_DEEP = int(os.environ.get("V53_DEEP", "2"))    # 深检专用 worker 数 (与探索解耦, 避免车道被 PC 轮询阻塞)
COOLDOWN = float(os.environ.get("V53_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
CKPT = os.path.join(_HERE, "results", "v57_glb_dlrfr_checkpoint.json")
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
DIVERSITY = os.path.join(_HERE, "results", "v57_diversity_report.jsonl")
DATASET = "dl_riskfree_returns"

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


# ---------------- 模板族 v57a: 首轮—USA 验证骨架移植 GLB + 简单探针 ----------------
# USA tri 实测: rank(group_zscore(ts_zscore(ts_backfill(f,66),189),industry)) S=2.33;
#   GLB 字段命名不同(带 _ohlcv_img 后缀), 选 6 个高覆盖代表字段跨 5/20/60day 三期限.
# 字段个股级 -> INDUSTRY neut 可用(analyst15 的 group 级消零问题不存在).
STYLES: Dict[str, List[Tuple[str, str]]] = {
    # A) USA 验证骨架: group_zscore + 长窗 ts_zscore (4 ops)
    "gzs": [
        ("gzP_p1q2_5d", "rank(group_zscore(ts_zscore(ts_backfill(probability_label1_2quantile_5day_ohlcv_img, 66), 189), industry))"),
        ("gzP_p1q2_20d", "rank(group_zscore(ts_zscore(ts_backfill(probability_label1_2quantile_20day_ohlcv_img, 66), 189), industry))"),
        ("gzN_p0q2_20d", "-rank(group_zscore(ts_zscore(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 66), 189), industry))"),
        ("gzN_p0q2_60d", "-rank(group_zscore(ts_zscore(ts_backfill(probability_label0_2quantile_60day_ohlcv_img, 66), 189), industry))"),
        ("gzP_p4q5_5d", "rank(group_zscore(ts_zscore(ts_backfill(probability_label4_5quantile_5day_ohlcv_img, 66), 189), industry))"),
        ("gzP_ql2_20d", "rank(group_zscore(ts_zscore(ts_backfill(quantile_label_2bucket_20day_ohlcv_img, 66), 189), industry))"),
    ],
    # B) 简单骨架探针 (验证信号是否依赖 group_zscore 包裹)
    "raw": [
        ("rwP_p1q2_5d", "rank(ts_mean(ts_backfill(probability_label1_2quantile_5day_ohlcv_img, 22), 5))"),
        ("rwN_p0q2_20d", "-rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5))"),
        ("rwP_ql2_20d", "rank(ts_backfill(quantile_label_2bucket_20day_ohlcv_img, 22))"),
    ],
    # C) 顶桶-底桶 log-prob 减号 spread (2 字段合规)
    "sprd": [
        ("spP_q2_5d", "rank(ts_backfill(probability_label1_2quantile_5day_ohlcv_img - probability_label0_2quantile_5day_ohlcv_img, 22))"),
        ("spP_q2_20d", "rank(ts_backfill(probability_label1_2quantile_20day_ohlcv_img - probability_label0_2quantile_20day_ohlcv_img, 22))"),
        ("gspP_q2_20d", "rank(group_zscore(ts_zscore(ts_backfill(probability_label1_2quantile_20day_ohlcv_img - probability_label0_2quantile_20day_ohlcv_img, 66), 189), industry))"),
    ],
    # D) v57b 二轮: PC 去拥挤 — 首轮 rwP_p1q2_5d 全部倒在 PC≈0.84 (热门字段 alphas 307-915).
    #   骨架锁定唯一 M 达标路径 rank(ts_mean(ts_backfill(f,22),5)), 字段全换 alphas≤18 冷门:
    #   4/5分位中间桶 + 60day 长期限. 语义: 低桶概率高=看空取负, 高桶概率高=看多正号.
    #   INDU neut 已被 PF:LOW_GLB_EMEA_SHARPE 证伪, 只跑 COUN (见 STYLE_OVERRIDES).
    "cold": [
        ("cP_p3q5_5d", "rank(ts_mean(ts_backfill(probability_label3_5quantile_5day_ohlcv_img, 22), 5))"),
        ("cP_p3q5_20d", "rank(ts_mean(ts_backfill(probability_label3_5quantile_20day_ohlcv_img, 22), 5))"),
        ("cP_p3q5_60d", "rank(ts_mean(ts_backfill(probability_label3_5quantile_60day_ohlcv_img, 22), 5))"),
        ("cP_p3q4_60d", "rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img, 22), 5))"),
        ("cP_p2q4_60d", "rank(ts_mean(ts_backfill(probability_label2_4quantile_60day_ohlcv_img, 22), 5))"),
        ("cP_ql4_60d", "rank(ts_mean(ts_backfill(quantile_label_4bucket_60day_ohlcv_img_2, 22), 5))"),
        ("cN_p1q4_5d", "-rank(ts_mean(ts_backfill(probability_label1_4quantile_5day_ohlcv_img, 22), 5))"),
        ("cN_p1q4_60d", "-rank(ts_mean(ts_backfill(probability_label1_4quantile_60day_ohlcv_img, 22), 5))"),
        ("cN_p0q4_60d", "-rank(ts_mean(ts_backfill(probability_label0_4quantile_60day_ohlcv_img, 22), 5))"),
        ("cN_p1q5_20d", "-rank(ts_mean(ts_backfill(probability_label1_5quantile_20day_ohlcv_img_2, 22), 5))"),
        ("cN_p0q3_60d", "-rank(ts_mean(ts_backfill(probability_label0_3quantile_60day_ohlcv_img_2, 22), 5))"),
        ("cN_p0q5_60d", "-rank(ts_mean(ts_backfill(probability_label0_5quantile_60day_ohlcv_img, 22), 5))"),
    ],
    # E) v57b 冷门对 spread (2 字段, 减号合规)
    "csp": [
        ("cspP_q4_60d", "rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5))"),
        ("cspP_q5_20d", "rank(ts_mean(ts_backfill(probability_label3_5quantile_20day_ohlcv_img - probability_label0_5quantile_20day_ohlcv_img, 22), 5))"),
    ],
    # ---- v57c 三轮: 变换级去相关 ----
    # 结案复盘: v57a/b 全部 9 条 PASS_CHEAP 灭于 PC 0.80-0.84, 且换冷门字段(alphas<=18)无效
    # => 拥挤在信号级(模型各输出高度同源), 只能改横截面变换/中性化/universe.
    # v66 实证: subindustry group_rank 把同源 est-revision 信号 PC 0.81->0.667.
    # 幸存骨架唯一 M>10bp 路径 ts_mean(ts_backfill(f,22),5) 保留为核, 外层全换.
    # 核心字段取 4 条幸存腿: p0q2_20d(负), p1q2_5d(正), p3q4-p0q4_60d spread(正), ql4_60d(正).
    # F) 细分组 group_rank (v66 验证的最强 PC 降杠杆)
    "gsub": [
        ("gsN_p0q2_20d_sub", "-group_rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), subindustry)"),
        ("gsP_p1q2_5d_sub", "group_rank(ts_mean(ts_backfill(probability_label1_2quantile_5day_ohlcv_img, 22), 5), subindustry)"),
        ("gsP_q4sp_60d_sub", "group_rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5), subindustry)"),
        ("gsP_ql4_60d_sub", "group_rank(ts_mean(ts_backfill(quantile_label_4bucket_60day_ohlcv_img_2, 22), 5), subindustry)"),
        ("gsN_p0q2_20d_sec", "-group_rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), sector)"),
        ("gsP_q4sp_60d_sec", "group_rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5), sector)"),
    ],
    # G) 中性化换轴 (raw 骨架不动, SUBINDUSTRY/STATISTICAL 见 STYLE_OVERRIDES)
    "ntx": [
        ("nxN_p0q2_20d", "-rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5))"),
        ("nxP_q4sp_60d", "rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5))"),
        ("nxP_ql4_60d", "rank(ts_mean(ts_backfill(quantile_label_4bucket_60day_ohlcv_img_2, 22), 5))"),
    ],
    # H) 时序分位替代截面 rank (与截面排名系拥挤天然低相关)
    "tsr": [
        ("trN_p0q2_20d", "-ts_rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), 126)"),
        ("trP_q4sp_60d", "ts_rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5), 126)"),
        ("trP_ql4_60d", "ts_rank(ts_mean(ts_backfill(quantile_label_4bucket_60day_ohlcv_img_2, 22), 5), 126)"),
    ],
    # I) 信号动量 ts_delta (时点错开, TVR 偏高 -> decay 3/6)
    "dlt": [
        ("dlN_p0q2_20d", "-rank(ts_delta(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), 22))"),
        ("dlP_p1q2_5d", "rank(ts_delta(ts_mean(ts_backfill(probability_label1_2quantile_5day_ohlcv_img, 22), 5), 22))"),
    ],
    # J) signed_power 尾部集中 x 细分组 (v59g/v66 验证的 F/M 杠杆, 减号合规)
    "pw": [
        ("pwN_p0q2_20d_sub", "-signed_power(group_rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), subindustry) - 0.5, 2)"),
        ("pwP_q4sp_60d_sub", "signed_power(group_rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5), subindustry) - 0.5, 2)"),
    ],
    # K) TOPDIV3000 换池 (v57a/b 从未跑过, PC 参照池不同)
    "uni": [
        ("tdN_p0q2_20d", "-rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5))"),
        ("tdP_q4sp_60d", "rank(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5))"),
        ("tdP_ql4_60d", "rank(ts_mean(ts_backfill(quantile_label_4bucket_60day_ohlcv_img_2, 22), 5))"),
    ],
    # ---- v57e 五轮: 模板级换血 (用户拍板: 实在不行就换模板) ----
    # 常规四维(字段/变换/universe/中性化)穷尽, PC 全区间 0.788-0.859. 全场唯一
    # 撼动 PC 的是 dlt 时间结构模板 (ts_delta lag22, PC=0.788 最低), 但只测了
    # rank x COUNTRY 单组合. v57e 弃截面 rank 骨架, 以 delta 为新核, 首次叠加
    # 三把已验证杠杆: subindustry group_rank / signed_power 尾部 / STATISTICAL.
    # L) delta x 细分组/尾部集中 (PC 最低模板 x 最强 PC/M 杠杆)
    "dxg": [
        ("dgN_p0q2_20d", "-group_rank(ts_delta(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), 22), subindustry)"),
        ("dgP_p1q2_5d", "group_rank(ts_delta(ts_mean(ts_backfill(probability_label1_2quantile_5day_ohlcv_img, 22), 5), 22), subindustry)"),
        ("dgN_pw_p0q2_20d", "-signed_power(group_rank(ts_delta(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), 22), subindustry) - 0.5, 2)"),
    ],
    # M) delta x STATISTICAL (两个次优杠杆叠加, dlt/stx 轮均未组合过)
    "dxs": [
        ("dsN_p0q2_20d", "-rank(ts_delta(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), 22))"),
        ("dsN_pw_p0q2_20d", "-signed_power(rank(ts_delta(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), 22)) - 0.5, 2)"),
    ],
    # N) 纯时序 z-score 模板 (无截面 rank, 与截面拥挤池结构性脱钩)
    "tz": [
        ("tzN_p0q2_20d", "-ts_zscore(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5), 66)"),
        ("tzP_q4sp_60d", "ts_zscore(ts_mean(ts_backfill(probability_label3_4quantile_60day_ohlcv_img - probability_label0_4quantile_60day_ohlcv_img, 22), 5), 66)"),
        ("tzP_ql4_60d", "ts_zscore(ts_mean(ts_backfill(quantile_label_4bucket_60day_ohlcv_img_2, 22), 5), 66)"),
    ],
    # ---- v57d 四轮: STAT 近失追击 ----
    # nxN_p0q2_20d_STAT_d3 S=5.24 F=3.69 M=9.9bp 差 0.1bp; STATISTICAL 的 PC 从未测到
    # (便宜闸门即死), 是最后未验证的去相关杠杆. 上 Margin 杠杆: signed_power 尾部
    # 集中(v59g 验证) + decay 6 降 TVR + trunc 0.05 允许集中持仓 (见 OVERRIDES).
    "stx": [
        ("sxN_pw_p0q2_20d", "-signed_power(rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5)) - 0.5, 2)"),
        ("sxP_pw_p1q2_5d", "signed_power(rank(ts_mean(ts_backfill(probability_label1_2quantile_5day_ohlcv_img, 22), 5)) - 0.5, 2)"),
        ("sxN_p0q2_20d", "-rank(ts_mean(ts_backfill(probability_label0_2quantile_20day_ohlcv_img, 22), 5))"),
    ],
}

UNIVERSES = ["MINVOL1M"]
DECAYS = [0, 3]
# 个股级字段: COUNTRY(GLB 去国别噪声) + INDUSTRY(去行业共性, USA 验证方向)
NEUTS = ["COUNTRY", "INDUSTRY"]
TRUNCS = [0.02]
MAX_VARIANTS = int(os.environ.get("V53_MAX_VARIANTS", "560"))

# 每风格覆盖 (universe/decay/neut), 未列出的风格沿用全局默认
STYLE_OVERRIDES: Dict[str, Dict[str, list]] = {
    # v57b: INDU 被 EMEA 子区检查证伪, 冷门轮只跑 COUN
    "cold": {"neuts": ["COUNTRY"]},
    "csp": {"neuts": ["COUNTRY"]},
    # v57c: 去相关轮 — 变换族各锁自身对照轴, 其余沿用 COUN 基线
    "gsub": {"neuts": ["COUNTRY"]},
    "ntx": {"neuts": ["SUBINDUSTRY", "STATISTICAL"]},
    "tsr": {"neuts": ["COUNTRY"]},
    "dlt": {"neuts": ["COUNTRY"], "decays": [3, 6]},
    "pw": {"neuts": ["COUNTRY"]},
    "uni": {"universes": ["TOPDIV3000"], "neuts": ["COUNTRY"]},
    # v57d: STAT 近失追击 — 只跑 STATISTICAL, M 杠杆组合 decay x trunc
    "stx": {"neuts": ["STATISTICAL"], "decays": [3, 6], "truncs": [0.02, 0.05]},
    # v57e: 模板换血轮 — delta 系 TVR 偏高固定 decay 3/6, trunc 双档保 Margin
    "dxg": {"neuts": ["COUNTRY"], "decays": [3, 6], "truncs": [0.02, 0.05]},
    "dxs": {"neuts": ["STATISTICAL"], "decays": [3, 6], "truncs": [0.02, 0.05]},
    "tz": {"neuts": ["COUNTRY"], "decays": [3, 6]},
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


def _bt_metrics(api, pid):
    det = api.get_alpha_details(pid)
    is_ = det.get("is") or {}
    s = _f(is_.get("sharpe")) or 0
    f = _f(is_.get("fitness")) or 0
    m_bp = (_f(is_.get("margin")) or 0) * 10000
    return s, f, m_bp


def deep_check_batched(api, expr, base_s):
    """把 risk-neut(MARKET) + 4 个 robust 探针合并成 1 次 multi-sim (5 子任务, 占 1 令牌).

    替代旧的 test_risk_neut + robust_overfit_test 5 次单发串行 (5 个 gate-turn -> 1 个).
    判据与短路顺序与旧实现完全一致: 先判 risk-neut, 通过才判 4 个 robust.
    返回 (rn_ok, rn_info, robust_report).
    """
    alt_uni = "TOPDIV3000" if base_s["universe"] == "MINVOL1M" else "MINVOL1M"
    flip = expr[1:] if expr.startswith("-") else f"-{expr}"
    probes = [
        ("rn_market", expr, {**base_s, "neutralization": "MARKET"}),
        ("alt_universe", expr, {**base_s, "universe": alt_uni}),
        ("decay+2", expr, {**base_s, "decay": min(int(base_s.get("decay", 4)) + 2, 12)}),
        ("decay-1", expr, {**base_s, "decay": max(int(base_s.get("decay", 4)) - 1, 0)}),
        ("sign_flip", flip, base_s),
    ]
    batch = [{"label": n, "expr": e, "settings": st} for n, e, st in probes]
    raw = run_multi_batch(api, batch, session=api.session, max_wait=2400, fallback_single=True)
    by_pid = {item["label"]: (item.get("pid") if item.get("ok") else None) for item in raw}
    # ---- risk-neut (MARKET) ----
    rn_pid = by_pid.get("rn_market")
    if not rn_pid:
        return False, {}, {"ok": False, "tests": [{"name": "rn_market", "error": "no_pid"}]}
    rs, rf, rm = _bt_metrics(api, rn_pid)
    rn = {"s": rs, "f": rf, "m_bp": rm}
    if not (rs > RN_S and rf > RN_F and rm > RN_M_BP):
        return False, rn, {"ok": True, "tests": []}
    # ---- robust/overfit (仅在 risk-neut 通过后判, 判据同旧) ----
    judges = {
        "alt_universe": lambda s, f: s > 1.0 and f > 0.5,
        "decay+2": lambda s, f: s > 1.2,
        "decay-1": lambda s, f: s > 1.2,
        "sign_flip": lambda s, f: s < -0.8,
    }
    report = {"ok": True, "tests": []}
    for name in ("alt_universe", "decay+2", "decay-1", "sign_flip"):
        pid = by_pid.get(name)
        if not pid:
            report["tests"].append({"name": name, "error": "no_pid"})
            report["ok"] = False
            continue
        s, f, _ = _bt_metrics(api, pid)
        ok = judges[name](s, f)
        report["tests"].append({"name": name, "sharpe": s, "fitness": f, "ok": ok})
        if not ok:
            report["ok"] = False
    return True, rn, report


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
_EXPLORE_DONE = threading.Event()  # 探索车道全部退出后置位, 深检 worker 据此排空退出


def _save_ckpt(state):
    with _LOCK:
        with open(CKPT, "w", encoding="utf-8") as f:
            json.dump({"results": state["results"], "found": state["found"]}, f, ensure_ascii=False, indent=2)


def _lane_worker(lane_id: int, q: "_queue.Queue", deepq: "_queue.Queue", state: Dict[str, Any], total_jobs: int, start_ts: float):
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
            if r["status"] == "PASS_CHEAP":
                deepq.put(r)  # 交给深检 worker 池, 探索车道立即取下一批, 不阻塞在 PC 轮询
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


def _deep_worker(did: int, deepq: "_queue.Queue", state: Dict[str, Any]):
    """深检专用 worker: 从 deepq 取 PASS_CHEAP 候选, 批量探针 -> PC 判定.

    与探索车道解耦: 探索命中后只 put 队列即返回取下一批;
    深检 5 探针合并成 1 次 multi-sim (占 1 令牌) -> 令牌利用率大幅提升.
    据 _EXPLORE_DONE 且 deepq 空时自然退出.
    """
    try:
        api = WqApiSimple()
    except Exception as e:
        logger.error("[deep%d] auth fail: %s", did, e)
        return
    while True:
        with _LOCK:
            if len(state["found"]) >= TARGET_FOUND:
                break
        try:
            r = deepq.get(timeout=5)
        except _queue.Empty:
            if _EXPLORE_DONE.is_set():
                break
            continue
        try:
            rn_ok, rn, rob = deep_check_batched(api, r["expr"], r["settings"])
            if not rn_ok:
                logger.info("  [deep%d] %s risk-neut FAIL %s", did, r["label"], rn)
                continue
            if not rob["ok"]:
                logger.info("  [deep%d] %s robust/overfit FAIL %s", did, r["label"],
                            [t.get("name") for t in rob["tests"] if not t.get("ok", False)])
                continue
            pc = wait_pc(api, r["pid"])
            if pc is None:
                logger.warning("  [deep%d] %s PC 未出 -> 跳过 (不提交)", did, r["label"])
                continue
            if pc >= MAX_PC:
                logger.warning("  [deep%d] %s PC=%.4f >= 0.70 淘汰", did, r["label"], pc)
                continue
            info = {
                "dataset": DATASET, "style": r["style"], "pid": r["pid"], "label": r["label"],
                "expr": r["expr"], "sharpe": r["sharpe"], "fitness": r["fitness"],
                "tvr": r["tvr"], "margin_bp": r["margin_bp"], "prod_corr": pc,
                "risk_neut": rn, "robust": rob, "settings": r["settings"],
                "region": "GLB", "submitted": False,
                "tags": ["v57", DATASET, "GLB_D1", "READY_MANUAL", "NO_SUBMIT"],
            }
            set_props(api, r["pid"], f"v57_{r['label']}", info["tags"],
                      f"GLB D1 unlit pyramid {DATASET}. {r['style']}. NO AUTO SUBMIT.")
            with _LOCK:
                state["found"].append(info)
                append_ready(info)
                _save_ckpt(state)
            logger.info("*** FOUND #%d %s S=%.2f M=%.1fbp PC=%.4f style=%s (NO SUBMIT) ***",
                        len(state["found"]), r["pid"], r["sharpe"], r["margin_bp"], pc, r["style"])
        finally:
            deepq.task_done()
    logger.info("[deep%d] exit", did)


def main():
    variants = build_variants()
    logger.info("V57 GLB dl_riskfree_returns | %d variants | lanes=%d deep=%d | %s",
                len(variants), N_LANES, N_DEEP, envelope_summary())
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
    deepq: "_queue.Queue" = _queue.Queue()
    for b in chunked(variants, BATCH_SIZE):
        q.put(b)

    _EXPLORE_DONE.clear()
    lanes = [threading.Thread(target=_lane_worker, args=(i, q, deepq, state, total_jobs, start_ts), daemon=True)
             for i in range(N_LANES)]
    deeps = [threading.Thread(target=_deep_worker, args=(i, deepq, state), daemon=True)
             for i in range(N_DEEP)]
    for t in lanes + deeps:
        t.start()
    for t in lanes:
        t.join()
    _EXPLORE_DONE.set()  # 探索车道全部退出 -> 深检 worker 排空 deepq 后自然退出
    for t in deeps:
        t.join()
    _save_ckpt(state)

    diversity_report(state["results"], -1)
    ok = [r for r in state["results"] if r.get("sharpe")]
    ok.sort(key=lambda x: -(x.get("sharpe") or 0))
    logger.info("DONE found=%d; top: %s", len(state["found"]), [
        (x.get("label"), round(x.get("sharpe") or 0, 2), round(x.get("margin_bp") or 0, 1)) for x in ok[:8]
    ])


if __name__ == "__main__":
    main()
