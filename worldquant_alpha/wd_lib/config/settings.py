"""
WorldQuant Brain API配置管理
"""

import os
from dotenv import load_dotenv

load_dotenv()


class WQConfig:
    """WorldQuant Brain API配置类"""

    def __init__(self, config_file: str = None):
        """
        初始化配置
        
        参数:
        - config_file: 配置文件路径（可选）
        """
        self.config_file = config_file
        self._config = {}
        if config_file and os.path.exists(config_file):
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                self._config = json.load(f)

    def get_credentials(self):
        """
        获取认证凭据
        
        返回:
        - (username, password) 元组
        """
        username = self._config.get('username') or os.environ.get('WQ_USERNAME')
        password = self._config.get('password') or os.environ.get('WQ_PASSWORD')
        if not username or not password:
            raise ValueError("请设置 WQ_USERNAME 和 WQ_PASSWORD 环境变量，或提供配置文件")
        return username, password

    def get(self, key, default=None):
        """获取配置项"""
        return self._config.get(key, default)
