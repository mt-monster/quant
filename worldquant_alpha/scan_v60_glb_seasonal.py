#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V60: GLB/D1 global_seasonal_model (季节性/regime 条件化收益预测模型) 挖掘.

前序: predictive_starmine v59 八轮 135 变体结案 — pw_y60w15 过 IS/RN/robust 全部门槛
但 PC=0.809 淘汰, est-revision 主线拥挤. 选型依据: GLB 全景榜 score=7.67 榜首,
690 字段 cov≈0.99, 212 users/620 alphas 整集低拥挤, 字段级 alphaCount 几乎全 0-13;
结构 = {输入: pv/analyst/option/ts} x {条件: calendar/event/monthqtr/regime} x {5d/20d/60d/120d}.

PC 风险分层: option 输入最正交(主攻) > timeseries > analyst(中危) > pv(dlrfr 翻版, 仅探针).
方向先验: predicted return / qtile label 越高 -> 看多 (正号).

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

LOG_PATH = os.path.join(_HERE, "results", "v60_glb_seasonal.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("v60")

from multi_sim import API_BASE, DEFAULT_COOLDOWN_SEC, envelope_summary, run_multi_batch, chunked
from wd_lib_wrapper import WqApiSimple

BATCH_SIZE = 8
N_LANES = int(os.environ.get("V53_LANES", "7"))  # 用户指示: 8 个 lane 先只开 7 个
COOLDOWN = float(os.environ.get("V53_COOLDOWN", str(DEFAULT_COOLDOWN_SEC)))
CKPT = os.path.join(_HERE, "results", "v60_glb_seasonal_checkpoint.json")
READY = os.path.join(_HERE, "results", "manual_submit_ready.json")
DIVERSITY = os.path.join(_HERE, "results", "v60_diversity_report.jsonl")
DATASET = "global_seasonal_model"

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


# ---------------- 模板族 v60a: 首轮 — v59 验证决定性骨架 group_rank(平滑(f), market)
# 字段全 MATRIX cov=1.0 (模型输出日频连续值/离散标签).
# 车道设计: option 主攻(a≈0) + ts 次之 + analyst/pv 对照探针 (PC 风险分层).
STYLES: Dict[str, List[Tuple[str, str]]] = {
    # A) option 系连续预测 (零拥挤主攻): regime/event/calendar 条件 x 20d/60d/120d
    "opt": [
        ("optP_rg20", "group_rank(ts_mean(ts_backfill(option_regime_20d_forward_return_pred, 22), 5), market)"),
        ("optP_ev60", "group_rank(ts_mean(ts_backfill(option_event_60d_forward_return_pred, 22), 5), market)"),
        ("optP_ev120", "group_rank(ts_mean(ts_backfill(option_event_120d_forward_return_pred, 22), 5), market)"),
        ("optP_evr20", "group_rank(ts_mean(ts_backfill(opt_event_20d_return_regression, 22), 5), market)"),
        ("optP_calr20", "group_rank(ts_mean(ts_backfill(opt_cal_20d_return_regression, 22), 5), market)"),
        ("optP_mqr20", "group_rank(ts_mean(ts_backfill(opt_monthqtr_20d_return_regression, 22), 5), market)"),
    ],
    # B) option 裸 rank 对照 (验证 group_rank 骨架在本数据集是否同样占优)
    "optR": [
        ("optR_rg20", "rank(ts_mean(ts_backfill(option_regime_20d_forward_return_pred, 22), 5))"),
        ("optR_ev60", "rank(ts_mean(ts_backfill(option_event_60d_forward_return_pred, 22), 5))"),
    ],
    # C) timeseries 系 5d 预测 (更新快 -> d3/d6 控 TVR)
    "tsr": [
        ("tsrP_ts5", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_5d, 22), 5), market)"),
        ("tsrP_ev5", "group_rank(ts_mean(ts_backfill(predicted_return_event_only_5d, 22), 5), market)"),
        ("tsrP_tse5", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 5), market)"),
        ("tsrP_ev60q", "group_rank(ts_mean(ts_backfill(timeseries_event_60d_qtile_pred, 22), 5), market)"),
    ],
    # D) analyst 系长 horizon 回归 (中危对照: starmine 同源 PC 风险)
    "anl": [
        ("anlP_120", "group_rank(ts_mean(ts_backfill(analyst_120d_return_regression, 22), 5), market)"),
        ("anlP_rg120", "group_rank(ts_mean(ts_backfill(analyst_regime_120d_regression_pred, 22), 5), market)"),
        ("anlP_ev120", "group_rank(ts_mean(ts_backfill(analyst_event_120d_regression_pred, 22), 5), market)"),
        ("anlP_cal60", "group_rank(ts_mean(ts_backfill(analyst_calendar_60d_regression_pred, 22), 5), market)"),
    ],
    # E) pv 系探针 (dlrfr PC=0.8 带对照, 各 1 条足矣)
    "pvp": [
        ("pvpP_ev20", "group_rank(ts_mean(ts_backfill(pvweekly_event_20d_1bucket_pred, 22), 5), market)"),
        ("pvpP_rg20", "group_rank(ts_mean(ts_backfill(pvweekly_regime_20d_1bucket_pred, 22), 5), market)"),
    ],
    # ---- v60b: 首轮诊断: anl族 IS四关全过只卡 PF:LOW_GLB_EMEA_SHARPE (ev120 d3 S=1.70/F=1.15/M=10.2);
    # rg120 M=18.6肥但S=1.25. 对策: group换country/industry拉EMEA分区 + 深decay追肥M
    "anl2": [
        ("anl2C_ev120", "group_rank(ts_mean(ts_backfill(analyst_event_120d_regression_pred, 22), 5), country)"),
        ("anl2I_ev120", "group_rank(ts_mean(ts_backfill(analyst_event_120d_regression_pred, 22), 5), industry)"),
        ("anl2C_120", "group_rank(ts_mean(ts_backfill(analyst_120d_return_regression, 22), 5), country)"),
        ("anl2C_rg120", "group_rank(ts_mean(ts_backfill(analyst_regime_120d_regression_pred, 22), 5), country)"),
    ],
    "anl3": [
        ("anl3M_ev120", "group_rank(ts_mean(ts_backfill(analyst_event_120d_regression_pred, 22), 5), market)"),
        ("anl3M_rg120", "group_rank(ts_mean(ts_backfill(analyst_regime_120d_regression_pred, 22), 5), market)"),
    ],
    # ---- v60c: anl2/3 zhen duan: group huan country/industry wu xiao, suo you ev120 tong ka
    # PF:LOW_GLB_EMEA_SHARPE -> bing zao zai neut ceng mian. dui ce: STATISTICAL neut la ping fen qu
    "anl4": [
        ("anl4M_ev120", "group_rank(ts_mean(ts_backfill(analyst_event_120d_regression_pred, 22), 5), market)"),
        ("anl4C_ev120", "group_rank(ts_mean(ts_backfill(analyst_event_120d_regression_pred, 22), 5), country)"),
        ("anl4M_rg120", "group_rank(ts_mean(ts_backfill(analyst_regime_120d_regression_pred, 22), 5), market)"),
    ],
    # ---- v60d: STATISTICAL zheng wei (M=3.2bp bei sha, EMEA reng 0.59); dan 2Y=1.96 jian kang.
    # dui ce: huan mo xing gong EMEA -- cal120 hui gui + 5bucket fen lei (a~0 ji di yong ji)
    "anl5": [
        ("anl5M_cal120", "group_rank(ts_mean(ts_backfill(analyst_calendar_120d_regression_pred, 22), 5), market)"),
        ("anl5C_cal120", "group_rank(ts_mean(ts_backfill(analyst_calendar_120d_regression_pred, 22), 5), country)"),
        ("anl5M_ev5b", "group_rank(ts_mean(ts_backfill(analyst_event_120d_5bucket_pred, 22), 5), market)"),
        ("anl5M_cal5b", "group_rank(ts_mean(ts_backfill(analyst_calendar_120d_5bucket_pred, 22), 5), market)"),
    ],
    # ---- v60e: anl5 tu po: 5bucket fen lei bu chu fa EMEA! ev5b d3 S=1.56/M=9.1 cha yi bu.
    # chong ci: prob_label_4-0 spread geng rui li + score4-0 spread + ev5b shen decay bu M
    "anl6": [
        ("anl6M_p40s", "group_rank(ts_mean(ts_backfill(analyst_event_120d_5bucket_prob_label_4, 22), 5) - ts_mean(ts_backfill(analyst_event_120d_5bucket_prob_label_0, 22), 5), market)"),
        ("anl6M_q40s", "group_rank(ts_mean(ts_backfill(analyst_event_120d_return_quantile5_score4, 22), 5) - ts_mean(ts_backfill(analyst_event_120d_return_quantile5_score0, 22), 5), market)"),
        ("anl6M_p4", "group_rank(ts_mean(ts_backfill(analyst_event_120d_5bucket_prob_label_4, 22), 5), market)"),
    ],
    "anl7": [
        ("anl7M_ev5b", "group_rank(ts_mean(ts_backfill(analyst_event_120d_5bucket_pred, 22), 5), market)"),
    ],
    # ---- v60f: anl6 zhen duan: prob spread S=1.71 dan hui gui hua chong fa EMEA; anl7 shen decay S diao.
    # gui lv: 5bucket pred wei yi mian EMEA dan dan tui S=1.56. po ju: shuang jian hao ji cheng la S
    # (cov=0.9993 sheng lue backfill kong ops<6)
    "anl8": [
        ("anl8M_evcal", "group_rank(ts_mean(analyst_event_120d_5bucket_pred, 5), market) - group_rank(-ts_mean(analyst_calendar_120d_5bucket_pred, 5), market)"),
        ("anl8M_evp0", "group_rank(ts_mean(analyst_event_120d_5bucket_pred, 5), market) - group_rank(ts_mean(analyst_event_120d_5bucket_prob_label_0, 5), market)"),
        ("anl8C_ev5b", "group_rank(ts_mean(analyst_event_120d_5bucket_pred, 5), country)"),
        ("anl8M_ev5bf", "group_rank(ts_mean(analyst_event_120d_5bucket_pred, 10), market)"),
    ],
    # ---- v60g: anl8 jie an: EMEA-free xing tai S ding 1.56. xian suo: tsrP_tse5 S=1.76/M=5.5
    # ye bu chu fa EMEA -> gao S tui + fei M tui shuang jian hao ji cheng (v61e mix tong kuan da fa)
    "anl9": [
        ("anl9M_tsev", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 5), market) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), market)"),
        ("anl9C_tsev", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 5), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), country)"),
        ("anl9M_tsev10", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 10), market) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 10), market)"),
    ],
    # ---- v60h: anl9 fen qu zhen duan: EMEA 0.76 cha 0.04; gui lv: kuai=EMEA gao, country +0.03.
    # chong ci: geng kuai ping hua ts_mean 3 + d0 + industry dui zhao (M zhang li: d0 hui ya M)
    "anl10": [
        ("anl10C_f3", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 3), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country)"),
        ("anl10C_f5", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 5), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), country)"),
        ("anl10I_f5", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 5), industry) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), industry)"),
        ("anl10C_evf", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 10), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country)"),
    ],
    # ---- v60i: anl10 jie an: kuai=EMEA jie feng dan M 5-7bp. gan gan: trunc fang kuan
    # (cang wei ji zhong du huan M, bu jian su bu diu EMEA)
    "anl11": [
        ("anl11C_f3", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 3), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country)"),
        ("anl11C_f5", "group_rank(ts_mean(ts_backfill(predicted_return_timeseries_event_5d, 22), 5), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), country)"),
    ],
    # ---- v60j: anl11 jie an: trunc wu xiao (spread quan zhong ben lai fen san). M gong jian:
    # hump lv xiao e diao cang (TVR down M up bu jian su). sheng lue backfill teng ops (cov=0.9993)
    "anl12": [
        ("anl12C_nb", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), country)"),
        ("anl12C_h1", "hump(group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), country), hump = 0.01)"),
        ("anl12C_h2", "hump(group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), country), hump = 0.02)"),
        ("anl12C_f3h", "hump(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country), hump = 0.01)"),
    ],
    # ---- v60k: hump dong si zheng wei. xin fei M tui: optP_rg20 M=24-26bp/TVR=4.3%/wu EMEA
    # (ev5b M jin 9bp bu gou fei) -> tse5 gao S tui + rg20 fei M tui shuang jian hao
    "anl13": [
        ("anl13C_tsrg", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), country) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 5), country)"),
        ("anl13M_tsrg", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), market) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 5), market)"),
        ("anl13C_f3rg", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 10), country)"),
        ("anl13C_evrg", "group_rank(ts_mean(analyst_event_120d_5bucket_pred, 5), country) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 5), country)"),
    ],
    # ---- v60l: anl13 qian yan: M_tsrg_d0 S=1.53/M=10.3 cha S 0.05; C ban S=1.58/M=8.7.
    # chong ci: market gu jia bao M + kuai tse tui (3) / man rg tui (10) la S
    "anl14": [
        ("anl14M_f3rg5", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), market) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 5), market)"),
        ("anl14M_f3rg10", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), market) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 10), market)"),
        ("anl14M_ts5rg10", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), market) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 10), market)"),
        ("anl14C_f3rg5", "group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 5), country)"),
    ],
    # ---- v60m: anl14 qian yan suo si S~1.55/M~10.5. zui hou M gang gan: signed_power ji zhong
    # cang wei (wei bu quan zhong ti M, bu gai shi xu bu diu EMEA/S). ops=5 he gui
    "anl15": [
        ("anl15C_pw3", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country), 2)"),
        ("anl15C_pw5", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 5), country), 2)"),
        ("anl15M_pwrg", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 5), market) - group_rank(-ts_mean(option_regime_20d_forward_return_pred, 10), market), 2)"),
        ("anl15C_pw3c", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country), 3)"),
    ],
    # ---- v60n: anl15 S bao biao 2.47 dan M bu sheng (power tui gao TVR). ji hui: S fu yu ju da
    # -> shen decay shou ge M (d0->d3: M+1.3bp/S-0.1, wai tui d9-12 M~10 S~2.0)
    "anl16": [
        ("anl16C_pw3", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country), 2)"),
        ("anl16C_pw3c", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(analyst_event_120d_5bucket_pred, 3), country), 3)"),
    ],
    # ---- v60o: anl16 PC=0.83-0.85 tao tai (ev5b PC=0.90/rg20=0.86 yong ji). di PC tui chi:
    # tse5=0.61 ev5=0.62 ev60q=0.62 evr20=0.69 -> di PC x di PC ji cheng + pw + shen decay
    "anl17": [
        ("anl17C_tsq", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(timeseries_event_60d_qtile_pred, 3), country), 2)"),
        ("anl17C_tsev5", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(predicted_return_event_only_5d, 3), country), 2)"),
        ("anl17C_tsevr", "signed_power(group_rank(ts_mean(predicted_return_timeseries_event_5d, 3), country) - group_rank(-ts_mean(opt_event_20d_return_regression, 5), country), 2)"),
        ("anl17C_qevr", "signed_power(group_rank(ts_mean(timeseries_event_60d_qtile_pred, 3), country) - group_rank(-ts_mean(opt_event_20d_return_regression, 5), country), 2)"),
    ],
}

UNIVERSES = ["MINVOL1M"]
DECAYS = [0, 3]
# v57 教训: INDU neut 被 PF:LOW_GLB_EMEA_SHARPE 系统性卡死, GLB 首轮只跑 COUN
NEUTS = ["COUNTRY"]
TRUNCS = [0.02]
MAX_VARIANTS = int(os.environ.get("V53_MAX_VARIANTS", "560"))

# 每风格覆盖 (universe/decay/neut), 未列出的风格沿用全局默认
STYLE_OVERRIDES: Dict[str, Dict[str, list]] = {
    # 5d 预测更新快 -> 大 decay 控 TVR
    "tsr": {"decays": [3, 6]},
    "anl2": {"decays": [3, 6]},
    "anl3": {"decays": [6, 9]},
    "anl4": {"decays": [3, 6], "neuts": ["STATISTICAL"]},
    "anl5": {"decays": [3, 6]},
    "anl6": {"decays": [3, 6]},
    "anl7": {"decays": [9, 12]},
    "anl8": {"decays": [3, 6]},
    "anl9": {"decays": [3, 6]},
    "anl10": {"decays": [0, 3]},
    "anl11": {"decays": [0, 3], "truncs": [0.05, 0.08]},
    "anl12": {"decays": [0, 3]},
    "anl13": {"decays": [0, 3]},
    "anl14": {"decays": [0, 3]},
    "anl15": {"decays": [0, 3]},
    "anl16": {"decays": [6, 9, 12]},
    "anl17": {"decays": [6, 9, 12]},
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
                "region": "GLB", "submitted": False,
                "tags": ["v60", DATASET, "GLB_D1", "READY_MANUAL", "NO_SUBMIT"],
            }
            set_props(api, r["pid"], f"v60_{r['label']}", info["tags"],
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
    logger.info("V60 GLB global_seasonal_model | %d variants | lanes=%d | %s",
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
