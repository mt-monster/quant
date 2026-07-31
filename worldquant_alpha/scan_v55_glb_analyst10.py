#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V55: GLB/D1 未点亮金字塔 analyst10 (Performance-Weighted Analyst Estimates) 挖掘.

前序: intraday_pv_feats 713 变体全证伪; sentiment21 140 变体 S 锁死 1.05 平台 (gddN_w22 最佳
S=1.06 F=0.47 M=4.3bp, 全部杠杆试尽), 切换分析师预期类 (收益来源与情绪/量价正交, 4321 alphas).
字段结构: anl10_{cps|grm|ent|fcf}{fy1|fy2|fq1|fq2}_{consensus|smart_ests_v0-2|pred_surps_v0-2};
GLB 视图 4 指标族, FY1/FY2 全 cov=1.0 免 backfill; 主矿脉=cps surprise (198 alphas).

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

LOG_PATH = os.path.join(_HERE, "results", "v55_glb_analyst10.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("v55")

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, envelope_summary, run_multi_batch, chunked
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
N_LANES = int(os.environ.get("V53_LANES", "7"))  # 用户指示: 8 个 lane 先只开 7 个
COOLDOWN = float(os.environ.get("V53_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
CKPT = os.path.join(_HERE, "results", "v55_glb_analyst10_checkpoint.json")
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
DIVERSITY = os.path.join(_HERE, "results", "v55_diversity_report.jsonl")
DATASET = "analyst10"

# ---------------- 闸门 ----------------
GATE_S, GATE_F, GATE_M_BP = 1.58, 1.00, 10.0
GATE_TVR_LO, GATE_TVR_HI = 0.05, 0.30
GATE_RET = 0.0   # v55f 移除: 用户 IS 门槛无 Ret 项 (v53 遗留自设); F>1 已隐含 Ret≥4%
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

STYLES_V53_ARCHIVE: Dict[str, List[Tuple[str, str]]] = {
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

# ---------------- v55 模板族 (analyst10) ----------------
# 约束: 操作符<6; 1-2 字段同数据集; 禁 trade_when/add()/multiply(); 减号 spread 允许
# 方向未知 → P/N 双符号探测; 全字段 cov=1.0 免 backfill (吸取 v54b 干净字段翻倍效应教训)
STYLES: Dict[str, List[Tuple[str, str]]] = {
    # A) 预测惊喜 cps FY1 (主矿脉 198 alphas): smart estimate 领先 consensus 的方向
    "surp_cps": [
        ("spcP_w5", "group_zscore(ts_mean(anl10_cpsfy1_pred_surps_v0_6272, 5), industry)"),
        ("spcP_w22", "group_zscore(ts_mean(anl10_cpsfy1_pred_surps_v0_6272, 22), industry)"),
        ("spcN_w5", "-group_zscore(ts_mean(anl10_cpsfy1_pred_surps_v0_6272, 5), industry)"),
        ("spcN_w22", "-group_zscore(ts_mean(anl10_cpsfy1_pred_surps_v0_6272, 22), industry)"),
    ],
    # B) 预测惊喜 grm Q1 (毛利率, 百分比量纲截面可比)
    "surp_grm": [
        ("spgP_w5", "group_zscore(ts_mean(anl10_grmfq1_pred_surps_v0_6232, 5), industry)"),
        ("spgP_w22", "group_zscore(ts_mean(anl10_grmfq1_pred_surps_v0_6232, 22), industry)"),
        ("spgN_w5", "-group_zscore(ts_mean(anl10_grmfq1_pred_surps_v0_6232, 5), industry)"),
        ("spgN_w22", "-group_zscore(ts_mean(anl10_grmfq1_pred_surps_v0_6232, 22), industry)"),
    ],
    # C) 智能预期-共识分歧 cps FY1 (2字段减法, ts_zscore 消每股量纲)
    "sdiv_cps": [
        ("sdcP_w22", "group_zscore(ts_zscore(anl10_cpsfy1_smart_ests_v0_6291 - anl10_cpsfy1_consensus_6271, 22), industry)"),
        ("sdcP_w63", "group_zscore(ts_zscore(anl10_cpsfy1_smart_ests_v0_6291 - anl10_cpsfy1_consensus_6271, 63), industry)"),
        ("sdcN_w22", "-group_zscore(ts_zscore(anl10_cpsfy1_smart_ests_v0_6291 - anl10_cpsfy1_consensus_6271, 22), industry)"),
        ("sdcN_w63", "-group_zscore(ts_zscore(anl10_cpsfy1_smart_ests_v0_6291 - anl10_cpsfy1_consensus_6271, 63), industry)"),
    ],
    # D) 智能预期-共识分歧 grm FY1 (量纲天然可比, 直接水平)
    "sdiv_grm": [
        ("sdgP_w10", "group_zscore(ts_mean(anl10_grmfy1_smart_ests_v0_6242 - anl10_grmfy1_consensus_6249, 10), industry)"),
        ("sdgP_w22", "group_zscore(ts_mean(anl10_grmfy1_smart_ests_v0_6242 - anl10_grmfy1_consensus_6249, 22), industry)"),
        ("sdgN_w10", "-group_zscore(ts_mean(anl10_grmfy1_smart_ests_v0_6242 - anl10_grmfy1_consensus_6249, 10), industry)"),
        ("sdgN_w22", "-group_zscore(ts_mean(anl10_grmfy1_smart_ests_v0_6242 - anl10_grmfy1_consensus_6249, 22), industry)"),
    ],
    # E) 共识修正动量 grm FY1 (revision momentum, 分析师上调毛利率预期)
    "rev_grm": [
        ("rvgP_w22", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 22), industry)"),
        ("rvgP_w63", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 63), industry)"),
        ("rvgN_w22", "-group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 22), industry)"),
        ("rvgN_w63", "-group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 63), industry)"),
    ],
    # F) v55b: rvgP 定向强化. 证据: rvgP_w63_d6 S=0.99 F=0.51 TVR=5.9% M=11.4bp (M/TVR 已达标,
    #    只缺 S 0.6); w22 S=0.29 → S 随窗口单调增. 杠杆: 更长 delta 窗口 / FY2 / smart_ests 版 /
    #    平滑 / winsorize / 分组切换 / rank / cps 跨指标复制 / FY1-FY2 斜率.
    "rvg_boost": [
        ("rvbP_w42", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 42), industry)"),
        ("rvbP_w84", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 84), industry)"),
        ("rvbP_w126", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 126), industry)"),
        ("rvbY2_w63", "group_zscore(ts_delta(anl10_grmfy2_consensus_6236, 63), industry)"),
        ("rvbSm_w63", "group_zscore(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 63), industry)"),
        ("rvbMn_w63", "group_zscore(ts_mean(ts_delta(anl10_grmfy1_consensus_6249, 63), 10), industry)"),
        ("rvbWz_w63", "group_zscore(winsorize(ts_delta(anl10_grmfy1_consensus_6249, 63)), industry)"),
        ("rvbSec_w63", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 63), sector)"),
        ("rvbSub_w63", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249, 63), subindustry)"),
        ("rvbRk_w63", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 63), industry)"),
        ("rvcP_w63", "group_zscore(ts_zscore(ts_delta(anl10_cpsfy1_consensus_6271, 63), 63), industry)"),
        ("rvsP_w63", "group_zscore(ts_delta(anl10_grmfy1_consensus_6249 - anl10_grmfy2_consensus_6236, 63), industry)"),
    ],
    # G) v55c: rvbRk 破线攻坚. 证据: rvbRk_w63 S=1.59(过线!) M=25.9-28.8bp(3倍门槛), 短板 F=0.85 /
    #    TVR=2.5-2.8%(同源: 换手太低压 returns). d6->d10 TVR 只降 0.3pp -> decay 非主杠杆.
    #    rank 对单调变换不变(winsorize/zscore 无效), 有效杠杆: 短窗口 / subindustry 细分组 /
    #    ts_rank 内嵌滚动重排序提换手 / d0-d3 低衰减. 目标: TVR 拉到 5%+ 同时 S 保 1.58+.
    "rank_boost": [
        ("rkbP_w42", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 42), industry)"),
        ("rkbP_w52", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 52), industry)"),
        ("rkbP_w63", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 63), industry)"),
        ("rkbP_w84", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 84), industry)"),
        ("rkbSub_w63", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 63), subindustry)"),
        ("rkbSub_w42", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 42), subindustry)"),
        ("rkbSec_w63", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 63), sector)"),
        ("rkbMkt_w63", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 63), market)"),
        ("rkbY2_w63", "group_rank(ts_delta(anl10_grmfy2_consensus_6236, 63), industry)"),
        ("rkbSm_w63", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 63), industry)"),
        ("rkbTs_w63", "group_rank(ts_rank(ts_delta(anl10_grmfy1_consensus_6249, 63), 22), industry)"),
        ("rkbTs_w42", "group_rank(ts_rank(ts_delta(anl10_grmfy1_consensus_6249, 42), 22), industry)"),
    ],
    # H) v55d: 合成冲刺. 证据: rkbP_w84_d0 S=1.65 F=0.90 TVR=3.2%(S过线/F差e0.10/TVR缺);
    #    rkbSm_w63_d0 TVR=6.1%(破下限!) S=1.53(差0.05) -> smart 天然高换手, S 随窗口单调增.
    #    合成: smart×w84/w126 期望 S/TVR 兼得; ent(税后盈利)族复制; smart v1/v2 版本对照.
    #    rkbTs 证伪(S砍區1.0), TVR 副杠杆只剩 d0.
    "rank_smart": [
        ("rksP_w84", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 84), industry)"),
        ("rksP_w126", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 126), industry)"),
        ("rksV1_w63", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v1_6254, 63), industry)"),
        ("rksV2_w63", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v2_6262, 63), industry)"),
        ("rksSub_w84", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 84), subindustry)"),
        ("rksEnt_w63", "group_rank(ts_delta(anl10_entfy1_smart_ests_v0_6491, 63), industry)"),
        ("rksEnt_w84", "group_rank(ts_delta(anl10_entfy1_smart_ests_v0_6491, 84), industry)"),
        ("rksEntC_w84", "group_rank(ts_delta(anl10_entfy1_consensus_6473, 84), industry)"),
    ],
    # I) v55d-2: TOP3000 大截面提 breadth/returns (F 杠杆), 复用最强骨架.
    "rank_top": [
        ("rktP_w84", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 84), industry)"),
        ("rktSm_w63", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 63), industry)"),
        ("rktSm_w84", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 84), industry)"),
        ("rktEnt_w63", "group_rank(ts_delta(anl10_entfy1_smart_ests_v0_6491, 63), industry)"),
    ],
    # J) v55e: 最后一堵墙 Ret≈M×TVR×500 (现圥85需100). 证据: rksP_w126_d0 S=1.85 F=1.08(双过线!)
    #    TVR=4.03%/Ret=4.28% 双差一口气. ent/TOP3000/v1v2 证伪. 三支箭: fq1 季度频修正提 TVR /
    #    w168 长窗口提 S×M / consensus×w126 rank 版(v55c 漏测点). d0 单 decay 省预算.
    "ret_push": [
        ("rkqSm_w126", "group_rank(ts_delta(anl10_grmfq1_smart_ests_v0_6238, 126), industry)"),
        ("rkqSm_w84", "group_rank(ts_delta(anl10_grmfq1_smart_ests_v0_6238, 84), industry)"),
        ("rkqC_w126", "group_rank(ts_delta(anl10_grmfq1_consensus_6261, 126), industry)"),
        ("rkqC_w84", "group_rank(ts_delta(anl10_grmfq1_consensus_6261, 84), industry)"),
        ("rksP_w168", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 168), industry)"),
        ("rksP_w105", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 105), industry)"),
        ("rkcP_w126", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 126), industry)"),
        ("rkcP_w168", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 168), industry)"),
    ],
    # K) v55e-2: trunc 集中仓位提 M (rank 均匀权重可能触截断线, 与 zscore 不同).
    "ret_trunc": [
        ("rktrP_w126", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 126), industry)"),
    ],
    # L) v55f: TVR 决战. 证据: 头部变体唯一卡 TVR<5% (rksP_w105 4.54% / rkcP_w126 S=1.86 M=32bp
    #    平台预检全过); trunc/fq1/w168 证伪. 杠杆实测: subindustry +0.7pp TVR (-0.03 S),
    #    窗口缩短 +TVR. 合成 sub×w94-w126 扫 S/TVR 交点 (期望: w105 sub TVR≈5.2% S≈1.79 F≈1.0).
    "tvr_final": [
        ("rkfSub_w94", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 94), subindustry)"),
        ("rkfSub_w105", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 105), subindustry)"),
        ("rkfSub_w115", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 115), subindustry)"),
        ("rkfSub_w126", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 126), subindustry)"),
    ],
    # M) v55f-2: TOPDIV3000 截面探针 (未试 universe, TVR/M 剖面未知).
    "tvr_div": [
        ("rkfDiv_w105", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 105), industry)"),
        ("rkfDiv_w126", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 126), industry)"),
    ],
    # N) v55g: EMEA 甜点扫描. 证据: rkfDiv_w126_TOPD S=1.64 F=1.08 TVR=7.2% M=15.1bp
    #    用户IS四门槛全过, 唯一挂 LOW_GLB_EMEA_SHARPE; 而 w105_TOPD 平台检查全过但 S=1.55.
    #    EMEA 随窗口变长衰减 -> 甜点在 w105-w126 之间. consensus 版 M 更肥且 MINV_w126 EMEA 过.
    "emea_sweet": [
        ("rkgS_w110", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 110), industry)"),
        ("rkgS_w115", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 115), industry)"),
        ("rkgS_w120", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 120), industry)"),
        ("rkgC_w105", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 105), industry)"),
        ("rkgC_w126", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 126), industry)"),
    ],
    # O) v55h: EMEA 收口. 证据: TOPD 上 S≥1.58 区(w110+, 挂EMEA)与 EMEA 通过区(w105, S=1.55)
    #    差 0.03 不相交; w120/consensus_w105 证伪. 三路: w107/w108 缝隙精扫 /
    #    rkgC_w126 批 multi-sim ERROR 重跑(consensus M肥且 MINV_w126 EMEA 预检曾过) /
    #    country 分组未试杠杆(国家内排名直接重塑 EMEA 剖面).
    "emea_final": [
        ("rkhS_w107", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 107), industry)"),
        ("rkhS_w108", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 108), industry)"),
        ("rkhC_w126", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 126), industry)"),
        ("rkhCty_w110", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 110), country)"),
        ("rkhCty_w126", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 126), country)"),
    ],
    # P) v55i: consensus×TOPD 金点重跑. 证据: rkcP_w126_MINV S=1.86 平台预检全过(含EMEA)
    #    只挂 TVR=2.65%; TOPD 实测把 TVR 翻倍/S 降~0.2 -> 预期 S~1.66 TVR~5.3% EMEA过.
    #    原 rkgC_w126_TOPD 批 multi-sim ERROR 丢失; t3 绕去重键(trunc 对 rank 均匀权重已证不咬合).
    #    搭车: w115 中间点 + subindustry 版(TVR 保险).
    "cons_div": [
        ("rkiC_w126", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 126), industry)"),
        ("rkiC_w115", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 115), industry)"),
        ("rkiCSub_w126", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 126), subindustry)"),
    ],
    # Q) v55j: 最后缺口. checkpoint 翻案: MINV 全线挂 EMEA(含 rkcP_w126), 全场唯一平台全过
    #    = rkfDiv_w105_TOPD_d0 S=1.55(差0.03). 实测 d0→d3 稳定 +0.01~0.03 S, 而 w105_TOPD
    #    只跑过 d0 -> d3/d6 未测点(d3 预期 S~1.57-1.58 TVR~5.7%). w106 微步搭车.
    #    STAT 探针: 换中性化重塑 EMEA 剖面(高S窗口 w110/w126).
    "final_gap": [
        ("rkjS_w105", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 105), industry)"),
        ("rkjS_w106", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 106), industry)"),
    ],
    "stat_probe": [
        ("rkjSt_w110", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 110), industry)"),
        ("rkjSt_w126", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 126), industry)"),
    ],
    # R) v55k: subindustry×TOPD 最后一张牌. 证据: TOPD 上 sub 是 +0.12 S 杠杆(rkiC_w126
    #    1.63→rkiCSub 1.75, 与 MINV 相反); 而 w105/106 左右 EMEA 已过只差 S 0.01
    #    (rkjS_w106_d0/w105_d3 S=1.57). 交点未测: smart×sub×w105-110 预期 S~1.67 全绿.
    #    consensus×sub×w115/120 副线(TVR 略短但 M 肥).
    "sub_final": [
        ("rkkSS_w105", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 105), subindustry)"),
        ("rkkSS_w106", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 106), subindustry)"),
        ("rkkSS_w110", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 110), subindustry)"),
        ("rkkCS_w115", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 115), subindustry)"),
        ("rkkCS_w120", "group_rank(ts_delta(anl10_grmfy1_consensus_6249, 120), subindustry)"),
    ],
    # S) v55l: F 收口. 证据: rkkSS_w105_d0 史上最近候选 S=1.61 TVR=8.3% M=11.2 EMEA过,
    #    唯挂 F=0.98(差0.02); d3 版 F=1.02 但 EMEA 翻挂 -> EMEA 边界在 w105×d0 附近.
    #    两路: d1/d2 中间 decay (F 插值过 1.0, EMEA 贴 d0 侧) / w103-104 短一步(EMEA 更稳)×d0/d3.
    "f_push_a": [
        ("rklSS_w105", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 105), subindustry)"),
    ],
    "f_push_b": [
        ("rklSS_w103", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 103), subindustry)"),
        ("rklSS_w104", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 104), subindustry)"),
    ],
    # T) v55m: 山脊加密. 证据: F 与 EMEA 逐点反相(w103/105 EMEA过 F=0.98; w104/106 F=1.01
    #    EMEA挂), 两检查均在边界噪声区 -> 沿 w101-111 加密找 F≥1.01∩EMEA 同过点.
    #    另: ts_decay_linear 在 rank 前(信号端平滑, 非仓位端), 与 settings decay 路径不同.
    "ridge_scan": [
        ("rkmSS_w101", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 101), subindustry)"),
        ("rkmSS_w102", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 102), subindustry)"),
        ("rkmSS_w107", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 107), subindustry)"),
        ("rkmSS_w108", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 108), subindustry)"),
        ("rkmSS_w109", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 109), subindustry)"),
        ("rkmSS_w111", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 111), subindustry)"),
        ("rkmTdl_w105", "group_rank(ts_decay_linear(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 105), 5), subindustry)"),
        ("rkmTdl_w110", "group_rank(ts_decay_linear(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 110), 5), subindustry)"),
    ],
    # U) v55n: neut 维度破局. 证据: w101-111 山脊上 F 与 EMEA 严格反相(结构性,
    #    非噪声), COUNTRY neut 下交集为空. INDUSTRY/MARKET neut 从未在 TOPD×sub 骨架上
    #    试过, 直接重塑 EMEA 内部组合; w108/111 有 0.11-0.12 S 余量可消耗.
    "neut_break": [
        ("rknSS_w108", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 108), subindustry)"),
        ("rknSS_w111", "group_rank(ts_delta(anl10_grmfy1_smart_ests_v0_6242, 111), subindustry)"),
    ],
}

UNIVERSES = ["MINVOL1M"]
DECAYS = [3, 6]
NEUTS = ["COUNTRY"]  # GLB 多国: COUNTRY 去国别噪声 (v54 实证全面优于 SUBINDUSTRY)
TRUNCS = [0.02]
MAX_VARIANTS = int(os.environ.get("V53_MAX_VARIANTS", "560"))

# 每风格覆盖 (universe/decay/neut), 未列出的风格沿用全局默认
STYLE_OVERRIDES_V53_ARCHIVE: Dict[str, Dict[str, list]] = {
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


# v55: 首轮 5 风格沿用全局默认 (MINVOL1M × d3/d6 × COUNTRY); v55b: d6/d10 压 TVR 提平滑
STYLE_OVERRIDES: Dict[str, Dict[str, list]] = {
    "rvg_boost": {
        "universes": ["MINVOL1M"],
        "decays": [6, 10],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55c: d0/d3 低衰减拉 TVR (rank 骨架 TVR 2.5-2.8% 需翻倍到 5%+)
    "rank_boost": {
        "universes": ["MINVOL1M"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55d: smart/ent 合成冲刺 (d0 拉 TVR); TOP3000 大截面提 F
    "rank_smart": {
        "universes": ["MINVOL1M"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "rank_top": {
        "universes": ["TOP3000"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55e: d0 单点省预算; trunc 探针 0.05/0.08
    "ret_push": {
        "universes": ["MINVOL1M"],
        "decays": [0],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "ret_trunc": {
        "universes": ["MINVOL1M"],
        "decays": [0],
        "neuts": ["COUNTRY"],
        "truncs": [0.05, 0.08],
    },
    # v55f: TVR 决战 d0 单点; TOPDIV3000 探针
    "tvr_final": {
        "universes": ["MINVOL1M"],
        "decays": [0],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "tvr_div": {
        "universes": ["TOPDIV3000"],
        "decays": [0],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55g: TOPD 甜点扫描, d0/d3 给 EMEA 二次采样
    "emea_sweet": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55h: EMEA 收口 (缝隙精扫 + ERROR重跑 + country分组探针)
    "emea_final": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55i: consensus×TOPD 金点 (t3 绕去重键, 结果等价 t2)
    "cons_div": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.03],
    },
    # v55j: w105/106 未测 decay 点 (w105_d0 重键自动跳); STAT 中性化探针
    "final_gap": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 3, 6],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "stat_probe": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 3],
        "neuts": ["STATISTICAL"],
        "truncs": [0.02],
    },
    # v55k: subindustry×TOPD 交点
    "sub_final": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55l: F 收口 (d1/d2 中间点; w103/104 短窗口)
    "f_push_a": {
        "universes": ["TOPDIV3000"],
        "decays": [1, 2],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    "f_push_b": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 3],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55m: 山脊加密 d0/d1
    "ridge_scan": {
        "universes": ["TOPDIV3000"],
        "decays": [0, 1],
        "neuts": ["COUNTRY"],
        "truncs": [0.02],
    },
    # v55n: neut 维度 (INDUSTRY/MARKET 重塑 EMEA 剖面)
    "neut_break": {
        "universes": ["TOPDIV3000"],
        "decays": [0],
        "neuts": ["INDUSTRY", "MARKET"],
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
    logger.info("V55 GLB analyst10 | %d variants | lanes=%d | %s",
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
