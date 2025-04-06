"""
WorldQuant Brain API会话管理模块
提供会话创建、刷新和管理功能
"""

import os
import time
import logging
import requests
from typing import Optional
from urllib.parse import urljoin

from ..config.constants import API_BASE_URL, REQUEST_TIMEOUT
from ..utils.exceptions import AuthenticationError, APIError

# 配置日志
logger = logging.getLogger(__name__)

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
        创建WorldQuant API会话
        
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
        
        # 创建会话对象
        session = requests.Session()
        session.auth = (username, password)
        
        # 发送认证请求
        try:
            response = session.post(
                urljoin(API_BASE_URL, 'authentication'), 
                timeout=REQUEST_TIMEOUT
            )
            
            if response.status_code not in [200, 201]:
                error_msg = f"认证失败: HTTP {response.status_code}"
                logger.error(error_msg)
                raise AuthenticationError(error_msg)
                
            logger.info("WorldQuant API会话创建成功")
            self._current_session = session
            return session
            
        except requests.exceptions.RequestException as e:
            error_msg = f"创建会话时网络错误: {str(e)}"
            logger.error(error_msg)
            raise AuthenticationError(error_msg) from e
    
    def refresh_session(self) -> requests.Session:
        """
        刷新WorldQuant API会话
        
        返回:
        - 刷新后的requests.Session对象
        
        异常:
        - AuthenticationError: 刷新失败时抛出
        """
        if not self._username or not self._password:
            raise AuthenticationError("无法刷新会话，未保存认证凭据")
            
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