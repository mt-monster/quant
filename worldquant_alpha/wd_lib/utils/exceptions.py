"""
WorldQuant Brain API异常类定义
"""

class WQAPIError(Exception):
    """WorldQuant API错误基类"""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class AuthenticationError(WQAPIError):
    """认证相关错误"""
    pass


class SimulationError(WQAPIError):
    """模拟过程中的错误"""
    pass


class APIError(WQAPIError):
    """API调用错误"""
    pass


class ValidationError(WQAPIError):
    """数据验证错误"""
    pass


class ConfigError(WQAPIError):
    """配置错误"""
    pass 