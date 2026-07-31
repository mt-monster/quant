#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V53: GLB/D1 未点亮金字塔 intraday_pv_feats 挖掘 (pm=1.0, MINVOL1M/TOPDIV3000).

用户硬约束:
- REGULAR, delay=1, maxTrade=OFF; 探索不同 universe (MINVOL1M / TOPDIV3000)
- IS: Sharpe>1.58, Fitness>1, 2Y-Sharpe>1.6, Margin>10bp, 5%<TVR<30%
- risk-neut(MARKET): Sharpe>1, Fitness>0.7, Margin>10bp
- 操作符数 <6; 单数据集 1-2 字段; 禁 trade_when/add()/multiply() (用 +,* 运算符也避免; 组合仅用减号 spread 形式)
- PROD_CORR 必须已出且 <0.7 才算候选 (<0.4 目标彼此独立); 绝不提交 (手动提交)
- multi-sim 8 车道流水线 (8 个 multi-sim 常驻在跑 = 64 表达式并发); 提交经 submit_gate 全局串行错峰 ≥18s
  (依据 probe_concurrency_final_report_20260725_0255.md: 令牌桶只限"瞬时提交集中度",
   不限"同时在跑 sim 数"; 实验3 K=10 分散提交全通过); 每 10 批做多样性评估
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

# 8 车道连发时提交间隔必须 ≥ 令牌补充速率(≈1/30s), 否则耗桶 429 (实测 18s 不收敛)
os.environ.setdefault("BRAIN_SUBMIT_INTERVAL", "32")

LOG_PATH = os.path.join(_HERE, "results", "v53_glb_intraday.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("v53")

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, envelope_summary, run_multi_batch, chunked
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
N_LANES = int(os.environ.get("V53_LANES", "7"))  # 用户指示: 8 个 lane 先只开 7 个
COOLDOWN = float(os.environ.get("V53_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
CKPT = os.path.join(_HERE, "results", "v53b_glb_intraday_checkpoint.json")
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
DIVERSITY = os.path.join(_HERE, "results", "v53_diversity_report.jsonl")
DATASET = "intraday_pv_feats"

# ---------------- 闸门 ----------------
GATE_S, GATE_F, GATE_M_BP = 1.58, 1.00, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
GATE_RET = 0.05
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


# ---------------- 模板族 v53d (第24轮多样性评估后重构) ----------------
# 归因: 长窗口尾盘反转 margin 过 10bp 但 2Y-Sharpe 仅 0.54~1.05 (信号近两年衰减) + EMEA 结构性弱
# 新方向: 收益来源正交的微观结构字段族 + 短窗口(近端敏感, 抱 2Y) ; 操作符<6; 禁 trade_when/add()/multiply()
BF = lambda f: f"ts_backfill({f}, 66)"

STYLES: Dict[str, List[Tuple[str, str]]] = {
    # A) 委托簿失衡 (order book imbalance) — 单字段, 微观结构流动性需求信号
    "obi": [
        ("obiP_w5", "group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 5), industry)"),
        ("obiP_w10", "group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 10), industry)"),
        ("obiP_w22", "group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 22), industry)"),
        ("obiN_w5", "-group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 5), industry)"),
        ("obiN_w10", "-group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 10), industry)"),
        ("obiN_w22", "-group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 22), industry)"),
    ],
    # B) 买卖报价收益不对称 (ask涨幅-bid涨幅 spread) — 买压/卖压方向信号, 2 字段减号组合
    "ba_gap": [
        ("bagP_w5", "group_zscore(ts_mean(ts_backfill(mean_ask_price_return_60m_pre_close_2 - mean_bid_price_return_60m_pre_close_2, 66), 5), industry)"),
        ("bagP_w10", "group_zscore(ts_mean(ts_backfill(mean_ask_price_return_60m_pre_close_2 - mean_bid_price_return_60m_pre_close_2, 66), 10), industry)"),
        ("bagN_w5", "-group_zscore(ts_mean(ts_backfill(mean_ask_price_return_60m_pre_close_2 - mean_bid_price_return_60m_pre_close_2, 66), 5), industry)"),
        ("bagN_w10", "-group_zscore(ts_mean(ts_backfill(mean_ask_price_return_60m_pre_close_2 - mean_bid_price_return_60m_pre_close_2, 66), 10), industry)"),
    ],
    # C) 成交价-VWAP 收益缺口 (尾盘冲高/砸盘 MOC 压力) — 2 字段同量纲减号
    "vwap_gap": [
        ("vwgN_w5", "-group_zscore(ts_mean(ts_backfill(mean_last_trade_price_return_30m_pre_close_2 - mean_vwap_return_30m_pre_close_2, 66), 5), industry)"),
        ("vwgN_w10", "-group_zscore(ts_mean(ts_backfill(mean_last_trade_price_return_30m_pre_close_2 - mean_vwap_return_30m_pre_close_2, 66), 10), industry)"),
        ("vwgN_w22", "-group_zscore(ts_mean(ts_backfill(mean_last_trade_price_return_30m_pre_close_2 - mean_vwap_return_30m_pre_close_2, 66), 22), industry)"),
        ("vwgP_w10", "group_zscore(ts_mean(ts_backfill(mean_last_trade_price_return_30m_pre_close_2 - mean_vwap_return_30m_pre_close_2, 66), 10), industry)"),
    ],
    # D) 日内漂移 (开盘价 vs 尾盘价, 同股时序 zscore 消价格量纲) — 日内动量/反转
    "intra_drift": [
        ("driN_w3", "-group_zscore(ts_mean(ts_zscore(ts_backfill(last_trade_price_60m_pre_close_2 - last_trade_price_60m_post_open, 66), 63), 3), industry)"),
        ("driN_w8", "-group_zscore(ts_mean(ts_zscore(ts_backfill(last_trade_price_60m_pre_close_2 - last_trade_price_60m_post_open, 66), 63), 8), industry)"),
        ("driP_w3", "group_zscore(ts_mean(ts_zscore(ts_backfill(last_trade_price_60m_pre_close_2 - last_trade_price_60m_post_open, 66), 63), 3), industry)"),
        ("driP_w8", "group_zscore(ts_mean(ts_zscore(ts_backfill(last_trade_price_60m_pre_close_2 - last_trade_price_60m_post_open, 66), 63), 8), industry)"),
    ],
    # E) 整数价位聊尔效应 (round-number clustering) — 行为学风格, 单字段
    "round_num": [
        ("rndP_w10", "group_rank(ts_mean(ts_backfill(mean_price_modulo_100_ratio_30m_pre_close_2, 66), 10), industry)"),
        ("rndP_w22", "group_rank(ts_mean(ts_backfill(mean_price_modulo_100_ratio_30m_pre_close_2, 66), 22), industry)"),
        ("rndN_w10", "-group_rank(ts_mean(ts_backfill(mean_price_modulo_100_ratio_30m_pre_close_2, 66), 10), industry)"),
        ("rndN_w22", "-group_rank(ts_mean(ts_backfill(mean_price_modulo_100_ratio_30m_pre_close_2, 66), 22), industry)"),
    ],
    # ---- v53e 攻坚 (基于 v53d 中期证据) ----
    # F) 委托簿失衡变化量 (obiN 方向对但强度弱 → 用 delta 捕捉边际变化, 30m 更近收盘)
    "obi_delta": [
        ("obdP_w3", "group_zscore(ts_delta(ts_backfill(mean_bid_ask_size_ratio_30m_pre_close_2, 66), 3), industry)"),
        ("obdP_w5", "group_zscore(ts_delta(ts_backfill(mean_bid_ask_size_ratio_30m_pre_close_2, 66), 5), industry)"),
        ("obdN_w3", "-group_zscore(ts_delta(ts_backfill(mean_bid_ask_size_ratio_30m_pre_close_2, 66), 3), industry)"),
        ("obdN_w5", "-group_zscore(ts_delta(ts_backfill(mean_bid_ask_size_ratio_30m_pre_close_2, 66), 5), industry)"),
    ],
    # G) 委托簿失衡慢速版 (obiN w5=1.04>w22=0.91, 但试更长平滑抬稳定性 + ts_rank 强化截面)
    "obi_slow": [
        ("obsN_w42", "-group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 42), industry)"),
        ("obsN_w63", "-group_zscore(ts_mean(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 63), industry)"),
        ("obrN_w22", "-group_rank(ts_rank(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 22), industry)"),
        ("obrN_w63", "-group_rank(ts_rank(ts_backfill(mean_bid_ask_size_ratio_60m_pre_close_2, 66), 63), industry)"),
    ],
    # H) 整数价位细粒度版 (rndP margin 10-21bp 但 S/TVR 双低 → modulo_10 更细价位提截面强度, delta 提换手)
    "rnd_fine": [
        ("rnfP_w10", "group_zscore(ts_mean(ts_backfill(mean_price_modulo_10_ratio_30m_pre_close_2, 66), 10), industry)"),
        ("rnfP_w22", "group_zscore(ts_mean(ts_backfill(mean_price_modulo_10_ratio_30m_pre_close_2, 66), 22), industry)"),
        ("rnfN_w10", "-group_zscore(ts_mean(ts_backfill(mean_price_modulo_10_ratio_30m_pre_close_2, 66), 10), industry)"),
        ("rndDP_w5", "group_zscore(ts_delta(ts_backfill(mean_price_modulo_100_ratio_30m_pre_close_2, 66), 5), industry)"),
        ("rndDN_w5", "-group_zscore(ts_delta(ts_backfill(mean_price_modulo_100_ratio_30m_pre_close_2, 66), 5), industry)"),
    ],
    # I) 日内高低幅度比 (尾盘波动率代理, 2字段除法, 低波溢价风格未探索)
    "range_ratio": [
        ("rngN_w10", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 10), industry)"),
        ("rngN_w22", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), industry)"),
        ("rngP_w10", "group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 10), industry)"),
    ],
    # J) v53f: rng 骨架提Sharpe定向改造 (F=0.9/M=44bp 已达标, 只换平滑/预处理)
    "range_sharpen": [
        ("rgrN_w22", "-group_rank(ts_rank(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), industry)"),
        ("rgrN_w44", "-group_rank(ts_rank(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 44), industry)"),
        ("rgzN_w22", "-group_zscore(ts_zscore(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), industry)"),
        ("rgwN_w14", "-group_zscore(winsorize(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 14)), industry)"),
        ("rgwN_w22", "-group_zscore(winsorize(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22)), industry)"),
        ("rgdN_w14", "-group_zscore(ts_decay_linear(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 14), industry)"),
        ("rgdN_w34", "-group_zscore(ts_decay_linear(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 34), industry)"),
        ("rgsN_w22", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), sector)"),
        ("rgmN_w22", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), market)"),
        ("rgrN_w14", "-group_rank(ts_rank(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 14), industry)"),
    ],
    # K) v53g: rng 骨架 Sharpe 卡 1.0 平台 -> 换维度: STATISTICAL 中性化剥离统计风险因子,
    #    TOP3000 大截面提 breadth, d3 低衰减把 TVR 拉回 5% 以上 (rgdN_w34_d10 TVR=4.3% 不达标)
    "range_boost": [
        ("rbzN_w22", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), industry)"),
        ("rbzN_w44", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 44), industry)"),
        ("rbdN_w34", "-group_zscore(ts_decay_linear(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 34), industry)"),
        ("rbdN_w66", "-group_zscore(ts_decay_linear(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 66), industry)"),
        ("rbsN_w22", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), sector)"),
        ("rbmN_w22", "-group_zscore(ts_mean(ts_backfill(max_last_trade_price_60m_pre_close_2 / min_last_trade_price_60m_pre_close_2, 66), 22), market)"),
    ],
    # L) v53h: revDz_w21 margin 定向提升. 证据: revDz_w21_MINV_d6_COUN_t2 S=2.27 F=1.51 TVR=16.5%
    #    唯一失败项 M=8.8bp (差1.2bp), 且 EMEA/2Y 平台检查全过 (w34 起才触发 2Y 衰减).
    #    杠杆: trunc 0.05/0.08 集中仓位提 margin; w18-w26 微调; d8 折中; sector/rank 对照.
    #    (range_boost+STAT 已被 risk-neut 证伪: RN S=0.62, 放弃)
    "rev_margin": [
        ("rvmDz_w18", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 18), industry)"),
        ("rvmDz_w21", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 21), industry)"),
        ("rvmDz_w24", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 24), industry)"),
        ("rvmDz_w26", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 26), industry)"),
        ("rvmDs_w21", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 21), sector)"),
        ("rvmDr_w21", "-group_rank(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 21), industry)"),
    ],
    # M) v53i: margin 甜点区. v53h 实验结论: trunc 无效(zscore 仓位不触截断线), group_rank 证伪(M 掉 6.4);
    #    有效杠杆: sector 分组 +1.2bp (w21: 8.8→10.0), 窗口 +0.35bp/2d (w18=8.4→w26=9.5), d8 +0.3~0.4bp.
    #    组合推演: sector × w24-w30 × d6/d8 可稳过 10bp; w30 靠近 w34 需监控 2Y 衰减.
    "rev_margin2": [
        ("rvnDs_w24", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 24), sector)"),
        ("rvnDs_w26", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 26), sector)"),
        ("rvnDs_w30", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 30), sector)"),
        ("rvnDz_w28", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 28), industry)"),
        ("rvnDz_w30", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 30), industry)"),
        ("rvnDm_w26", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 26), market)"),
    ],
    # N) v53j-1: rev 族收尾. v53i 结论: margin/2Y 的墙在 w28<->w30 之间 (rvnDz_w28_d6 S=2.15 2Y过 M=9.8;
    #    w30_d6 M=10.2 但 2Y挂). d7 期望 +0.2bp 不像 d8 杀 2Y; w27/29 同时给 EMEA 抖动第二次采样.
    "rev_final": [
        ("rvoDz_w27", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 27), industry)"),
        ("rvoDz_w28", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 28), industry)"),
        ("rvoDz_w29", "-group_zscore(ts_decay_linear(ts_backfill(mean_last_trade_price_return_30m_pre_close_2, 66), 29), industry)"),
    ],
    # O) v53j-2: 报价-VWAP 定位价差 (未用字段 cov=1.00). ask/bid 报价相对 VWAP 的位置 = 做市商挂单倾斜,
    #    与价格反转收益来源正交. 2字段同量纲减法.
    "quote_vwap": [
        ("qvgP_w5", "group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 5), industry)"),
        ("qvgN_w5", "-group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 5), industry)"),
        ("qvgP_w22", "group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 22), industry)"),
        ("qvgN_w22", "-group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 22), industry)"),
    ],
    # P) v53j-3: 尾盘成交量集中度 (最后10分钟 interval 量 / 尾盘30m 均量, 未用字段 cov=1.00).
    #    MOC 拍卖资金流代理, 纯量维度与价格族正交. 2字段除法.
    "close_vol": [
        ("clvP_w10", "group_zscore(ts_mean(ts_backfill(trade_volume_last_interval / mean_trade_volume_30m_pre_close_2, 66), 10), industry)"),
        ("clvN_w10", "-group_zscore(ts_mean(ts_backfill(trade_volume_last_interval / mean_trade_volume_30m_pre_close_2, 66), 10), industry)"),
        ("clvP_w22", "group_zscore(ts_mean(ts_backfill(trade_volume_last_interval / mean_trade_volume_30m_pre_close_2, 66), 22), industry)"),
        ("clvN_w22", "-group_zscore(ts_mean(ts_backfill(trade_volume_last_interval / mean_trade_volume_30m_pre_close_2, 66), 22), industry)"),
    ],
    # Q) v53k: qvg 骨架 Sharpe 定向改造. 证据: qvgN_w22_d6 S=1.10 M=30.4bp(门槛3倍) TVR=3.7%.
    #    短板只在 S 与 TVR; 杆杆: 中窗口提TVR / subindustry细分组 / rank去尾 / winsorize / 30m近收盘版 / decay_linear / sector.
    "qvg_sharpen": [
        ("qvsN_w10", "-group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 10), industry)"),
        ("qvsN_w14", "-group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 14), industry)"),
        ("qvsNu_w22", "-group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 22), subindustry)"),
        ("qvsNr_w22", "-group_rank(ts_rank(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 22), industry)"),
        ("qvsNw_w22", "-group_zscore(winsorize(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 22)), industry)"),
        ("qv3N_w22", "-group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_30m_pre_close_2 - mean_bid_vwap_ratio_30m_pre_close_2, 66), 22), industry)"),
        ("qvsNd_w22", "-group_zscore(ts_decay_linear(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 22), industry)"),
        ("qvsNs_w22", "-group_zscore(ts_mean(ts_backfill(mean_ask_vwap_ratio_60m_pre_close_2 - mean_bid_vwap_ratio_60m_pre_close_2, 66), 22), sector)"),
    ],
}

UNIVERSES = ["MINVOL1M", "TOPDIV3000"]
DECAYS = [6, 10]
NEUTS = ["COUNTRY", "SUBINDUSTRY"]  # GLB 多国: COUNTRY 去国别噪声; SUBINDUSTRY 细粒度
TRUNCS = [0.02]
MAX_VARIANTS = int(os.environ.get("V53_MAX_VARIANTS", "560"))

# 每风格覆盖 (universe/decay/neut), 未列出的风格沿用全局默认
STYLE_OVERRIDES: Dict[str, Dict[str, list]] = {
    "range_boost": {
        "universes": ["MINVOL1M", "TOP3000"],
        "decays": [3, 6],
        "neuts": ["STATISTICAL", "COUNTRY"],
    },
    "rev_margin": {
        "universes": ["MINVOL1M"],
        "decays": [6, 8],
        "neuts": ["COUNTRY"],
        "truncs": [0.02, 0.05, 0.08],
    },
    "rev_margin2": {
        "universes": ["MINVOL1M"],
        "decays": [6, 8],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "rev_final": {
        "universes": ["MINVOL1M"],
        "decays": [6, 7],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "quote_vwap": {
        "universes": ["MINVOL1M"],
        "decays": [3, 6],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "close_vol": {
        "universes": ["MINVOL1M"],
        "decays": [3, 6],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "qvg_sharpen": {
        "universes": ["MINVOL1M"],
        "decays": [3, 6],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
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
        if s["decay"] == 6: sc += 1
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


# ---------------- 主流程: 8 车道流水线 ----------------
# 设计依据 (probe_concurrency_final_report_20260725_0255.md):
#   - 令牌桶只限 POST /simulations 的瞬时集中度 (C=7, refill≈1/30s), 不限同时在跑数
#   - submit_gate 文件锁将全部提交串行化 ≥18s → 瞬时提交并发恒=1 (安全区≤6)
#   - 8 车道各自提交→轮询→评估→再取下一批; 稳态提交率≈8/600s=1/75s < refill

_LOCK = threading.RLock()


def _save_ckpt(state):
    with _LOCK:
        with open(CKPT, "w", encoding="utf-8") as f:
            json.dump({"results": state["results"], "found": state["found"]}, f, ensure_ascii=False, indent=2)


def _lane_worker(lane_id: int, q: "_queue.Queue", state: Dict[str, Any], total_jobs: int, start_ts: float):
    time.sleep(lane_id * 5)  # 起步错峰, 避免 8 认证/提交同时拉起
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
                "tags": ["v53", DATASET, "GLB_D1", "READY_MANUAL", "NO_SUBMIT"],
            }
            set_props(api, r["pid"], f"v53_{r['label']}", info["tags"],
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
    logger.info("V53 GLB intraday_pv_feats | %d variants | lanes=%d | %s",
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
