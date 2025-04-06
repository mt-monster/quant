"""
WorldQuant配置管理模块
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from .constants import DEFAULT_BACKTEST_SETTINGS, API_BASE_URL

# 配置日志
logger = logging.getLogger(__name__)

class WQConfig:
    """WorldQuant配置管理类，提供对配置的集中管理"""
    
    _instance = None
    
    def __new__(cls, config_file=None):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(WQConfig, cls).__new__(cls)
            cls._instance._initialize(config_file)
        return cls._instance
    
    def _initialize(self, config_file=None):
        """初始化配置"""
        self.config = {}
        
        # 从环境变量加载配置
        load_dotenv()
        
        # 基础配置
        self.config['api_base_url'] = os.getenv('WQ_API_BASE_URL', API_BASE_URL)
        self.config['username'] = os.getenv('WQ_USERNAME', '')
        self.config['password'] = os.getenv('WQ_PASSWORD', '')
        
        # 从配置文件加载
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    self.config.update(file_config)
                logger.info(f"从配置文件加载成功: {config_file}")
            except Exception as e:
                logger.error(f"加载配置文件失败: {str(e)}")
        
        # 设置默认参数
        if 'default_settings' not in self.config:
            self.config['default_settings'] = DEFAULT_BACKTEST_SETTINGS.copy()
    
    def get(self, key: str, default=None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        self.config[key] = value
    
    def get_api_base_url(self) -> str:
        """获取API基础URL"""
        return self.config.get('api_base_url', API_BASE_URL)
    
    def get_credentials(self) -> tuple:
        """获取认证凭据"""
        return self.config.get('username', ''), self.config.get('password', '')
    
    def get_default_settings(self, simulation_type: str = 'REGULAR') -> Dict[str, Any]:
        """
        获取默认回测设置
        
        参数:
        - simulation_type: 模拟类型，如 'REGULAR', 'COMBO'
        
        返回:
        - 默认设置字典
        """
        default_settings = self.config.get('default_settings', {})
        
        if simulation_type == 'COMBO' and 'combo_settings' in self.config:
            # 如果是组合Alpha并且有专门的配置，则使用组合配置
            return self.config['combo_settings'].copy()
        
        # 使用常规配置
        if not default_settings:
            default_settings = DEFAULT_BACKTEST_SETTINGS.copy()
            
        return default_settings.copy()
    
    def save_to_file(self, config_file: str) -> bool:
        """
        保存配置到文件
        
        参数:
        - config_file: 配置文件路径
        
        返回:
        - 是否保存成功
        """
        try:
            # 创建目录
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            
            # 过滤敏感信息
            save_config = self.config.copy()
            save_config.pop('password', None)
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(save_config, f, indent=2, ensure_ascii=False)
                
            logger.info(f"配置保存成功: {config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
            return False 