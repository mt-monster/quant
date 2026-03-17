"""
WorldQuant Brain API会话管理模块
提供会话创建、刷新和管理功能
"""

import os
import time
import random
import logging
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional
from urllib.parse import urljoin

from ..config.constants import API_BASE_URL, REQUEST_TIMEOUT
from ..utils.exceptions import AuthenticationError, APIError

# 配置日志
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# 最短刷新间隔（秒），防止多线程并发认证导致 ConnectionReset
# ─────────────────────────────────────────────────────────
_SESSION_MIN_REFRESH_INTERVAL = 30.0
_session_refresh_lock = threading.Lock()
_last_session_refresh: float = 0.0


def _build_session_with_retry() -> requests.Session:
    """创建带 HTTPAdapter 重试适配器的 Session"""
    session = requests.Session()
    retry_policy = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PATCH", "DELETE"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry_policy,
        pool_connections=4,
        pool_maxsize=16,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class SessionManager:
    """
    WorldQuant API会话管理器
    使用单例模式实现，确保全局只有一个会话实例
    """
    
    _instance = None
    _current_session = None
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(SessionManager, cls).__new__(cls)
            cls._instance._username = None
            cls._instance._password = None
        return cls._instance
    
    def create_session(self, username=None, password=None) -> requests.Session:
        """
        创建WorldQuant API会话（带指数退避重试，最多 5 次）
        
        参数:
        - username: 用户名，如果为None则从环境变量获取
        - password: 密码，如果为None则从环境变量获取
        
        返回:
        - requests.Session对象
        
        异常:
        - AuthenticationError: 认证失败时抛出
        """
        # 如果没有提供用户名或密码，从环境变量获取
        if username is None:
            username = os.getenv('WQ_USERNAME')
        if password is None:
            password = os.getenv('WQ_PASSWORD')
        
        if not username or not password:
            raise AuthenticationError("必须提供用户名和密码，或设置WQ_USERNAME和WQ_PASSWORD环境变量")
        
        # 保存凭据以备刷新使用
        self._username = username
        self._password = password
        
        logger.info("正在创建WorldQuant API会话...")
        
        last_exc = None
        for attempt in range(1, 6):
            try:
                # 每次重试都创建带重试适配器的新 Session
                session = _build_session_with_retry()
                session.auth = (username, password)
                
                response = session.post(
                    urljoin(API_BASE_URL, 'authentication'),
                    timeout=REQUEST_TIMEOUT
                )
                
                if response.status_code not in [200, 201]:
                    raise AuthenticationError(f"认证失败: HTTP {response.status_code}")
                
                logger.info("WorldQuant API会话创建成功")
                self._current_session = session
                return session

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError,
                    ConnectionResetError) as e:
                last_exc = e
                wait = min(5 * (2 ** (attempt - 1)), 60) + random.uniform(0, 3)
                logger.warning(
                    f"连接错误（第 {attempt}/5 次），{wait:.1f}s 后重试: {e}"
                )
                time.sleep(wait)

            except AuthenticationError:
                raise

            except requests.exceptions.RequestException as e:
                error_msg = f"创建会话时网络错误: {str(e)}"
                logger.error(error_msg)
                raise AuthenticationError(error_msg) from e

        error_msg = f"创建会话失败（已重试 5 次）: {last_exc}"
        logger.error(error_msg)
        raise AuthenticationError(error_msg) from last_exc
    
    def refresh_session(self) -> requests.Session:
        """
        刷新WorldQuant API会话（带防抖保护，30s 内只刷一次）
        
        返回:
        - 刷新后的requests.Session对象
        
        异常:
        - AuthenticationError: 刷新失败时抛出
        """
        global _last_session_refresh

        if not self._username or not self._password:
            raise AuthenticationError("无法刷新会话，未保存认证凭据")

        now = time.time()
        with _session_refresh_lock:
            if (now - _last_session_refresh < _SESSION_MIN_REFRESH_INTERVAL
                    and self._current_session is not None):
                logger.debug("会话刷新防抖：距上次刷新不足 30s，复用现有会话")
                return self._current_session
            _last_session_refresh = now

        logger.info("正在刷新WorldQuant API会话...")
        
        try:
            return self.create_session(self._username, self._password)
        except Exception as e:
            error_msg = f"刷新会话失败: {str(e)}"
            logger.error(error_msg)
            raise AuthenticationError(error_msg) from e
    
    def get_session(self) -> requests.Session:
        """
        获取当前的WorldQuant API会话，如果不存在则创建一个新的
        
        返回:
        - 当前的requests.Session对象
        """
        if self._current_session is None:
            logger.info("当前没有活动会话，正在创建新会话...")
            return self.create_session()
        
        return self._current_session


# 全局会话管理器实例
_session_manager = SessionManager()

# 导出便捷函数
def create_session(username=None, password=None) -> requests.Session:
    """创建新会话的便捷函数"""
    return _session_manager.create_session(username, password)

def refresh_session() -> requests.Session:
    """刷新会话的便捷函数"""
    return _session_manager.refresh_session()

def get_session() -> requests.Session:
    """获取当前会话的便捷函数"""
    return _session_manager.get_session() 