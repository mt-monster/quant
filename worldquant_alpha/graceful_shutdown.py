"""
优雅关闭模块
提供进程信号处理和资源清理功能
"""
import signal
import sys
import atexit
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """优雅关闭管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._shutdown_requested = False
        self._cleanup_callbacks: list[Callable] = []
        self._original_handlers = {}

        # 注册退出回调
        atexit.register(self._do_cleanup)

        # 设置信号处理器
        self._register_signal_handlers()

        logger.info("优雅关闭管理器已初始化")

    def _register_signal_handlers(self):
        """注册信号处理器"""
        signals = [
            (signal.SIGINT, "SIGINT"),
            (signal.SIGTERM, "SIGTERM"),
        ]

        # Windows 不支持 SIGTERM
        if sys.platform != "win32":
            signals.append((signal.SIGTERM, "SIGTERM"))

        for sig, name in signals:
            try:
                # 保存原始处理器
                self._original_handlers[sig] = signal.getsignal(sig)

                # 设置新的处理器
                def make_handler(sig_name):
                    def handler(signum, frame):
                        logger.warning(f"收到 {sig_name} 信号，开始优雅关闭...")
                        self.request_shutdown()
                    return handler

                signal.signal(sig, make_handler(name))
            except (OSError, ValueError) as e:
                logger.warning(f"无法注册信号处理器 {name}: {e}")

    def request_shutdown(self):
        """请求关闭"""
        if not self._shutdown_requested:
            self._shutdown_requested = True
            logger.warning("关闭请求已收到，正在停止任务...")

            # 执行清理回调
            self._do_cleanup()

            # 退出程序
            sys.exit(0)

    def is_shutting_down(self) -> bool:
        """检查是否正在关闭"""
        return self._shutdown_requested

    def add_cleanup_callback(self, callback: Callable):
        """添加清理回调函数"""
        if callback not in self._cleanup_callbacks:
            self._cleanup_callbacks.append(callback)
            logger.debug(f"添加清理回调: {callback.__name__}")

    def remove_cleanup_callback(self, callback: Callable):
        """移除清理回调函数"""
        if callback in self._cleanup_callbacks:
            self._cleanup_callbacks.remove(callback)

    def _do_cleanup(self):
        """执行清理"""
        logger.info("执行清理任务...")

        # 按逆序执行回调
        for callback in reversed(self._cleanup_callbacks):
            try:
                callback()
                logger.info(f"清理完成: {callback.__name__}")
            except Exception as e:
                logger.error(f"清理失败 {callback.__name__}: {e}")

        # 恢复原始信号处理器
        for sig, handler in self._original_handlers.items():
            try:
                signal.signal(sig, handler)
            except Exception:
                pass

    def wait_if_shutting_down(self) -> bool:
        """在循环中检查是否需要停止

        返回:
        - True 表示需要停止循环
        - False 表示继续执行
        """
        if self._shutdown_requested:
            logger.info("检测到关闭信号，正在停止当前任务...")
            return True
        return False


# 全局实例
shutdown_manager = GracefulShutdown()


def is_shutting_down() -> bool:
    """检查是否正在关闭"""
    return shutdown_manager.is_shutting_down()


def request_shutdown():
    """请求关闭"""
    shutdown_manager.request_shutdown()


def add_cleanup_callback(callback: Callable):
    """添加清理回调"""
    shutdown_manager.add_cleanup_callback(callback)


def wait_if_shutting_down() -> bool:
    """在循环中检查是否需要停止"""
    return shutdown_manager.wait_if_shutting_down()
