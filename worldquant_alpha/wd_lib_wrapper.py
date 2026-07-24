#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WqApiSimple — WQ Brain 轻量封装（从 .pyc 重建）"""
import os, time, logging, threading
import requests
from urllib.parse import urljoin
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

API_BASE = "https://api.worldquantbrain.com"

_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_here, ".env"))


class WqApiSimple:
    def __init__(self, max_wait_time=1800):
        self.max_wait_time = max_wait_time
        here = os.path.dirname(os.path.abspath(__file__))
        load_dotenv(os.path.join(here, ".env"))
        self.user = os.getenv("WQ_USERNAME", "")
        self.pwd = os.getenv("WQ_PASSWORD", "")
        self.session = requests.Session()
        self._auth_lock = threading.Lock()
        self._thread_local = threading.local()
        self._reauth()
        self._sub_sem = threading.Semaphore(5)
        try:
            from local_selfcorr import LocalSelfCorr
            self.local_sc = LocalSelfCorr()
        except Exception as e:
            logger.warning("初始化本地自相关性计算器失败: %s", e)
            self.local_sc = None

    def _reauth(self, max_tries=6):
        with self._auth_lock:
            last = None
            for attempt in range(max_tries):
                try:
                    r = self.session.post(
                        urljoin(API_BASE, "authentication"),
                        auth=(self.user, self.pwd),
                        timeout=30,
                    )
                    if r.status_code == 201:
                        logger.info("WqApiSimple 认证成功（用户=%s***）", self.user[:3])
                        return
                    last = f"HTTP {r.status_code} {r.text[:100]}"
                except Exception as e:
                    last = str(e)
                wait = min(15 + attempt * 15, 60)
                logger.warning("认证失败（第 %d/%d 次）: %s，%ss 后重试", attempt + 1, max_tries, last, wait)
                time.sleep(wait)
            raise RuntimeError(f"认证失败: {last}")

    def _get_session(self):
        """每个工作线程独占连接池，避免 requests.Session 并发死锁。"""
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(self.session.headers)
            session.cookies.update(self.session.cookies)
            self._thread_local.session = session
        return session

    def run_backtest(self, alpha_expression, settings, max_wait_time=None, submit_retries=40):
        if max_wait_time is None:
            max_wait_time = self.max_wait_time
        data = {"type": "REGULAR", "settings": settings, "regular": alpha_expression}
        session = self._get_session()
        with self._sub_sem:
            attempt = 0
            r = None
            while attempt <= submit_retries:
                try:
                    r = session.post(
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
                    logger.warning("回测提交遇 401（会话过期），重新认证...")
                    try:
                        self._reauth()
                        session.cookies.clear()
                        session.cookies.update(self.session.cookies)
                    except:
                        time.sleep(10)
                    continue
                if r.status_code == 429:
                    wait = min(20 + attempt * 8, 45)
                    logger.warning("回测提交遇并发上限 429，%ss 后重试 (#%d)", wait, attempt)
                    time.sleep(wait)
                    attempt += 1
                    continue
                if r.status_code == 400:
                    try:
                        detail = r.json()
                    except:
                        detail = r.text[:200]
                    logger.error("回测结果无 alpha id: %s", str(detail)[:300])
                    return None
                logger.warning("回测提交 HTTP %s，%ss 后重试", r.status_code, 20)
                time.sleep(20)
                attempt += 1
            if r is None or not r.ok:
                return None
            loc = r.headers.get("Location", "")
            prog_url = loc if loc else r.json().get("location", "")
            if not prog_url:
                return None
            started_at = time.monotonic()
            sleep_t = 5
            while time.monotonic() - started_at < max_wait_time:
                try:
                    pr = session.get(prog_url, timeout=60)
                except Exception as e:
                    logger.warning("轮询回测进度异常: %s", e)
                    time.sleep(10)
                    continue
                if pr.status_code == 200:
                    try:
                        detail = pr.json()
                    except:
                        time.sleep(sleep_t)
                        continue
                    status = detail.get("status", "")
                    if status == "COMPLETE":
                        alpha_id = detail.get("alpha")
                        if alpha_id:
                            return {"platform_id": alpha_id, "status": "COMPLETE"}
                        return None
                    elif status == "ERROR":
                        logger.error("回测结果无 alpha id: %s", str(detail)[:300])
                        return None
                elif pr.status_code == 401:
                    self._reauth()
                    session.cookies.clear()
                    session.cookies.update(self.session.cookies)
                time.sleep(sleep_t)
            logger.warning("回测等待超过 %ss，放弃该表达式", max_wait_time)
            return None

    def get_alpha_details(self, alpha_id):
        session = self._get_session()
        for _ in range(3):
            try:
                r = session.get(
                    urljoin(API_BASE, f"alphas/{alpha_id}"), timeout=60)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 401:
                    self._reauth()
                    continue
            except Exception as e:
                logger.warning("get_alpha_details 异常: %s", e)
            time.sleep(5)
        return {}

    def get_alpha_check(self, alpha_id):
        session = self._get_session()
        for _ in range(3):
            try:
                r = session.get(
                    urljoin(API_BASE, f"alphas/{alpha_id}/check"), timeout=60)
                if r.status_code == 200 and r.text.strip():
                    return r.json()
                if r.status_code == 401:
                    self._reauth()
                    continue
            except Exception as e:
                logger.warning("get_alpha_check 异常: %s", e)
            time.sleep(5)
        return {}
