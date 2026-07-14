# -*- coding: utf-8 -*-
"""
wd_lib_wrapper —— 轻量 WorldQuant Brain API 封装（WqApiSimple）

为 mine_usa_ppa_*.py 提供与历史脚本一致的接口：
  * WqApiSimple()             无参构造，自动从 .env 读取凭据并登录
  * .run_backtest(expr, settings=...) -> {"platform_id": ..., "status": ...} | None
  * .get_alpha_details(pid)   -> /alphas/{pid} 原始 JSON（含 is.*）
  * .get_alpha_check(pid)     -> /alphas/{pid}/check 原始 JSON（含 is.checks）
  * .session                  requests.Session，供 update_alpha_properties 使用

说明：
  - 用 requests + HTTP Basic Auth 直连 api.worldquantbrain.com，不依赖 wd_lib 的
    重客户端，避免其 run_backtest 内置的“20 分钟超时 + 随机 10~60 分钟睡眠”逻辑
    阻塞挖掘循环。
  - run_backtest 自带轮询，按 WQ 返回的 Retry-After 等待；单条回测超过
    max_wait_time 秒未出结果则返回 None（交给上层换下一条），不会随机长睡。
"""
import os
import time
import logging
import threading

import requests
from urllib.parse import urljoin
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
API_BASE = "https://api.worldquantbrain.com/"


class WqApiSimple:
    def __init__(self, max_wait_time: int = 1800):
        here = os.path.dirname(os.path.abspath(__file__))
        load_dotenv(os.path.join(here, ".env"))

        # 可选：本地自相关性加速计算器（缺失仅告警，不影响主流程）
        try:
            import local_selfcorr  # noqa: F401
            self.local_selfcorr = local_selfcorr
            logger.info("本地自相关性计算器已加载")
        except Exception as e:
            logger.warning("初始化本地自相关性计算器失败: %s", e)
            self.local_selfcorr = None

        user = os.environ.get("WQ_USERNAME")
        pwd = os.environ.get("WQ_PASSWORD")
        if not user or not pwd:
            raise RuntimeError("缺少 WQ_USERNAME / WQ_PASSWORD 环境变量")

        self._user = user
        self._pwd = pwd
        self.max_wait_time = max_wait_time
        self.session = requests.Session()
        self.session.auth = (user, pwd)
        # 全局在飞信号量：值 = 服务端并发模拟上限 C（实测=5）。
        # 在 run_backtest 中包住「提交+轮询」全程，使同时在飞回测数恒=该值，
        # 既吃满服务端配额、又不超额触发 429。
        self._sub_sem = threading.Semaphore(5)
        # 重认证锁：防止多线程同时 401 时重复认证
        self._auth_lock = threading.Lock()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        self._reauth()

    def _reauth(self):
        """重新认证（遇到 401 时自动调用）。线程安全。"""
        with self._auth_lock:
            try:
                r = self.session.post(urljoin(API_BASE, "authentication"), timeout=60)
                r.raise_for_status()
                logger.info("WqApiSimple 认证成功（用户=%s）", self._user[:3] + "***")
            except Exception as e:
                logger.error("WqApiSimple 认证失败: %s", e)
                raise

    # ───────────────────────── 回测 ─────────────────────────
    def run_backtest(self, alpha_expression, settings=None, max_wait_time=None,
                   submit_retries=40):
        if settings is None:
            settings = {}
        if max_wait_time is None:
            max_wait_time = self.max_wait_time

        data = {
            "type": "REGULAR",
            "settings": settings,
            "regular": alpha_expression,
        }
        # 信号量包住「提交 + 轮询」全程：在飞回测数恒 = 信号量值(=C=5)。
        with self._sub_sem:
            # 提交阶段：429（并发模拟上限）指数退避重试，绝不因限流丢弃候选
            attempt = 0
            r = None
            while attempt <= submit_retries:
                try:
                    r = self.session.post(
                        urljoin(API_BASE, "simulations"), json=data, timeout=120)
                except Exception as e:
                    logger.warning("回测提交网络异常，%ss 后重试: %s",
                                 15 if attempt == 0 else 30, e)
                    time.sleep(15 if attempt == 0 else 30)
                    attempt += 1
                    continue
                if r.ok:
                    break
                if r.status_code == 401:
                    # 会话过期：自动重新认证后重试（不消耗 attempt 配额）
                    logger.warning("回测提交遇 401（会话过期），重新认证...")
                    try:
                        self._reauth()
                    except Exception:
                        time.sleep(10)
                    continue
                if r.status_code == 429:
                    # 频繁短退避：配额槽位会随孤儿模拟完成而持续释放，
                    # 用 20~45s 的短间隔重试比长退避更易抓住刚空出的槽位
                    wait = min(20 + attempt * 8, 45)
                    logger.warning("回测提交遇并发上限 429，%ss 后重试 (#%d)",
                                 wait, attempt)
                    time.sleep(wait)
                    attempt += 1
                    continue
                # 其它 4xx 视为永久失败（如表达式非法）
                logger.error("回测提交失败 %s %s", r.status_code, r.text[:300])
                return None
            if r is None or not r.ok:
                logger.error("回测提交重试耗尽，放弃该表达式")
                return None

            loc = r.headers.get("Location")
            if not loc:
                logger.error("回测未返回 Location 头: %s", r.text[:300])
                return None
            prog_url = loc if loc.startswith("http") else urljoin(API_BASE, loc)
            logger.info("回测已提交，进度URL: %s", prog_url)

            waited = 0
            detail = None
            while True:
                try:
                    pr = self.session.get(prog_url, timeout=120)
                    if pr.status_code == 401:
                        logger.warning("轮询遇 401（会话过期），重新认证...")
                        self._reauth()
                        continue
                    pr.raise_for_status()
                    detail = pr.json()
                except Exception as e:
                    logger.warning("轮询回测进度异常: %s", e)
                    time.sleep(10)
                    waited += 10
                    if waited > max_wait_time:
                        return None
                    continue

                ra = float(pr.headers.get("Retry-After", 0) or 0)
                if ra == 0:
                    break
                sleep_t = min(ra, 60)
                time.sleep(sleep_t)
                waited += sleep_t
                if waited > max_wait_time:
                    logger.warning("回测等待超过 %ss，放弃该表达式", max_wait_time)
                    return None

            alpha_id = (detail or {}).get("alpha")
            if not alpha_id:
                logger.error("回测结果无 alpha id: %s",
                            str(detail)[:300])
                return None
            logger.info("回测完成，alpha_id=%s", alpha_id)
            return {"platform_id": alpha_id, "status": (detail or {}).get("status")}

    # ───────────────────────── 详情 / 检查 ─────────────────────────
    def get_alpha_details(self, alpha_id):
        for _ in range(2):
            try:
                r = self.session.get(
                    urljoin(API_BASE, f"alphas/{alpha_id}"), timeout=120)
                if r.status_code == 401:
                    logger.warning("获取详情遇 401，重新认证...")
                    self._reauth()
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                logger.error("获取 alpha 详情失败 %s: %s", alpha_id, e)
                return {}
        return {}

    def get_alpha_check(self, alpha_id):
        for _ in range(2):
            try:
                r = self.session.get(
                    urljoin(API_BASE, f"alphas/{alpha_id}/check"), timeout=120)
                if r.status_code == 401:
                    logger.warning("获取检查遇 401，重新认证...")
                    self._reauth()
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                logger.error("获取 alpha 检查失败 %s: %s", alpha_id, e)
                return {}
        return {}
