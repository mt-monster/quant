"""
重试机制工具
"""

import time
import asyncio
import logging
import functools
import requests
from typing import Callable, Any, Optional

from .exceptions import AuthenticationError, APIError
from ..config.constants import DEFAULT_MAX_RETRIES

# 配置日志
logger = logging.getLogger(__name__)

def with_retry(max_retries: int = DEFAULT_MAX_RETRIES, retry_delay: float = 2.0, 
               error_types: tuple = (requests.RequestException, AuthenticationError, APIError)):
    """
    带重试机制的装饰器，支持同步和异步函数
    
    参数:
    - max_retries: 最大重试次数
    - retry_delay: 重试间隔（秒）
    - error_types: 需要重试的异常类型
    
    返回:
    - 装饰后的函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            """异步函数的装饰器实现"""
            retries = 0
            last_error = None
            
            while retries <= max_retries:
                try:
                    return await func(*args, **kwargs)
                except error_types as e:
                    retries += 1
                    last_error = e
                    
                    if retries > max_retries:
                        logger.error(f"达到最大重试次数 {max_retries}，操作失败: {str(e)}")
                        break
                    
                    # 指数退避策略
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.warning(f"操作失败，{wait_time:.1f}秒后重试 ({retries}/{max_retries}): {str(e)}")
                    await asyncio.sleep(wait_time)
                    
            # 如果所有重试都失败，抛出最后一个异常
            if last_error:
                raise last_error
            
            raise RuntimeError("未知错误导致重试失败")
            
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            """同步函数的装饰器实现"""
            retries = 0
            last_error = None
            
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except error_types as e:
                    retries += 1
                    last_error = e
                    
                    if retries > max_retries:
                        logger.error(f"达到最大重试次数 {max_retries}，操作失败: {str(e)}")
                        break
                    
                    # 指数退避策略
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.warning(f"操作失败，{wait_time:.1f}秒后重试 ({retries}/{max_retries}): {str(e)}")
                    time.sleep(wait_time)
            
            # 如果所有重试都失败，抛出最后一个异常
            if last_error:
                raise last_error
            
            raise RuntimeError("未知错误导致重试失败")
            
        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
        
    return decorator 