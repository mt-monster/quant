"""WorldQuant API简化封装模块"""
import logging
import os
import time
import random
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logger = logging.getLogger(__name__)

# API基础URL
API_BASE_URL = "https://api.worldquantbrain.com/"

class WqApiSimple:
    """WorldQuant API的简化封装类"""
    
    # 添加类变量
    API_BASE_URL = API_BASE_URL
    
    def __init__(self, max_retry=3):
        """初始化API客户端"""
        self.session = None
        self.max_retry = max_retry
        self.initialize()
    
    def initialize(self):
        """初始化会话"""
        username = os.environ.get('WQ_USERNAME')
        password = os.environ.get('WQ_PASSWORD')
        
        if not username or not password:
            logger.error("环境变量中缺少WorldQuant凭据")
            raise ValueError("请在环境变量中设置WQ_USERNAME和WQ_PASSWORD")
        
        try:
            # 创建会话
            self.session = requests.Session()
            self.session.auth = (username, password)
            
            # 登录
            response = self.session.post(f"{API_BASE_URL}authentication")
            if response.status_code != 201:
                raise Exception(f"登录失败: {response.status_code}")
                
            logger.info("WorldQuant API会话初始化成功")
        except Exception as e:
            logger.error(f"初始化WorldQuant API会话失败: {e}")
            raise
    
    def refresh_session(self):
        """刷新会话"""
        try:
            self.initialize()
            logger.info("WorldQuant API会话刷新成功")
            return True
        except Exception as e:
            logger.error(f"刷新会话失败: {e}")
            return False
    
    def _retry_operation(self, func, *args, **kwargs):
        """带重试机制的操作执行"""
        retry_count = 0
        
        while retry_count <= self.max_retry:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                retry_count += 1
                if retry_count <= self.max_retry:
                    logger.warning(f"操作失败，尝试刷新会话并重试 ({retry_count}/{self.max_retry}): {e}")
                    self.refresh_session()
                    time.sleep(2)  # 等待2秒后重试
                else:
                    logger.error(f"操作失败，已达到最大重试次数: {e}")
                    raise
    
    def get_alphas(self, limit=100, offset=0, filters=None):
        """获取Alpha列表"""
        url = f"{API_BASE_URL}users/self/alphas"
        
        params = {
            "limit": limit,
            "offset": offset,
        }
        
        # 添加过滤条件
        if filters:
            params.update(filters)
        
        try:
            response = self._retry_operation(
                lambda: self.session.get(url, params=params)
            )
            
            if response.status_code != 200:
                logger.error(f"获取Alpha列表失败: {response.status_code}")
                return []
                
            data = response.json()
            return data.get("results", [])
        except Exception as e:
            logger.error(f"获取Alpha列表时出错: {e}")
            return []
    
    def submit_simulation(self, alpha_expression, settings=None):
        """提交Alpha回测"""
        if settings is None:
            settings = {
                "instrumentType": "EQUITY",
                "region": "USA",
                "universe": "TOP3000",
                "delay": 1,
                "decay": 0,
                "neutralization": "SUBINDUSTRY",
                "truncation": 0.08,
                "pasteurization": "ON",
                "unitHandling": "VERIFY",
                "nanHandling": "ON",
                "language": "FASTEXPR",
                "visualization": True,
            }
        
        url = f"{API_BASE_URL}simulations"
        
        simulation_data = {
            'type': 'REGULAR',
            'settings': settings,
            'regular': alpha_expression
        }

        try:
            response = self._retry_operation(
                lambda: self.session.post(url, json=simulation_data)
            )
            
            if response.status_code != 201:
                logger.error(f"提交回测失败: {response.status_code}")
                return False, None

            sim_progress_url = response.headers.get('Location')
            if not sim_progress_url:
                logger.error("回测请求没有返回Location头")
                return False, None

            # 等待回测结果
            wait_count = 0
            total_wait_time = 0
            while True:
                sim_progress_resp = self._retry_operation(
                    lambda: self.session.get(sim_progress_url)
                )

                if sim_progress_resp.status_code == 200:
                    retry_after_sec = float(sim_progress_resp.headers.get("Retry-After", 0))
                    if retry_after_sec > 0:
                        time.sleep(retry_after_sec)
                    else:
                        logger.error("回测结束")
                        break
                    data = sim_progress_resp.json()
                    progress = data.get('progress', 0)
                    if progress >= 100:
                        break

                    logger.info(f"回测中 ({total_wait_time}s): {progress}%")
                    wait_count += 1
                    total_wait_time += 5
                    time.sleep(10)  # 5秒后检查进度
                else:
                    logger.error(f"检查回测进度失败: {sim_progress_resp.status_code}")
                    return False, None

            # 提取Alpha ID
            result_data = sim_progress_resp.json()
            alpha_id = result_data.get("alpha")
            if not alpha_id:
                logger.error("未能获取Alpha ID")
                return False, None
                
            return True, alpha_id
        except Exception as e:
            logger.error(f"提交回测时出错: {e}")
            return False, None
    
    def get_alpha_details(self, alpha_id):
        """获取Alpha详情"""
        url = f"{API_BASE_URL}alphas/{alpha_id}"
        
        try:
            response = self._retry_operation(
                lambda: self.session.get(url)
            )
            
            if response.status_code != 200:
                logger.error(f"获取Alpha详情失败: {response.status_code}")
                return {}
                
            return response.json()
        except Exception as e:
            logger.error(f"获取Alpha详情时出错: {e}")
            return {}
    
    def get_alpha_check(self, alpha_id):
        """获取Alpha检查结果"""
        url = f"{API_BASE_URL}alphas/{alpha_id}/check"
        
        try:
            response = self._retry_operation(
                lambda: self.session.get(url)
            )
            
            if response.status_code != 200:
                logger.error(f"获取Alpha检查结果失败: {response.status_code}")
                return {}
                
            return response.json()
        except Exception as e:
            logger.error(f"获取Alpha检查结果时出错: {e}")
            return {}
    
    def set_alpha_color(self, alpha_id, color):
        """设置Alpha颜色"""
        url = f"{API_BASE_URL}alphas/{alpha_id}"
        
        try:
            response = self._retry_operation(
                lambda: self.session.patch(url, json={"color": color})
            )
            
            if response.status_code != 200:
                logger.error(f"设置Alpha颜色失败: {response.status_code}")
                return False
                
            logger.info(f"成功将Alpha {alpha_id} 的颜色设置为 {color}")
            return True
        except Exception as e:
            logger.error(f"设置Alpha颜色时出错: {e}")
            return False
    
    def check_alpha_status(self, alpha_id):
        """检查Alpha状态并设置颜色"""
        try:
            # 获取检查结果
            check_result = self.get_alpha_check(alpha_id)
            
            # 检查是否有失败项
            checks = check_result.get("is", {}).get("checks", [])
            for check in checks:
                if check.get("result") == "FAIL":
                    logger.info(f"Alpha {alpha_id} 检查失败: {check.get('name')}")
                    self.set_alpha_color(alpha_id, "YELLOW")
                    return False, "YELLOW"
            
            # 设置为蓝色
            self.set_alpha_color(alpha_id, "BLUE")
            logger.info(f"Alpha {alpha_id} 已设置为蓝色")
            
            # 获取自相关性
            self_corr = None
            for check in checks:
                if check.get("name") == "SELF_CORRELATION":
                    self_corr = check.get("value")
                    break
            
            # 根据自相关性设置颜色
            color = "BLUE"  # 默认蓝色
            if self_corr is not None and self_corr <= 0.7:
                self.set_alpha_color(alpha_id, "GREEN")
                logger.info(f"Alpha {alpha_id} 自相关性为 {self_corr}，设置为绿色")
                color = "GREEN"
            
            return True, color
        except Exception as e:
            logger.error(f"检查Alpha状态时出错: {e}")
            return False, None
    
    def run_backtest(self, alpha_expression, settings=None):
        """运行Alpha回测并等待完成"""
        try:
            logger.info(f"开始对Alpha进行回测: {alpha_expression[:50]}...")
            
            # 提交回测请求
            success, alpha_id = self.submit_simulation(alpha_expression, settings)
            if not success or not alpha_id:
                return None
            
            details = self.get_alpha_details(alpha_id)
            status = details.get('status')


            # 检查颜色
            color = None
            is_data = details.get('is', {})
            sharpe = is_data.get('sharpe', 0)
            
            if sharpe >= 1.25:
                checks_ok, color = self.check_alpha_status(alpha_id)
            
            # 处理结果
            result = {
                'id': alpha_id,
                'expression': alpha_expression,
                'status': status,
                'sharpe': is_data.get('sharpe'),
                'turnover': is_data.get('turnover'),
                'fitness': is_data.get('fitness'),
                'drawdown': is_data.get('drawdown'),
                'color': color
            }
            
            logger.info(f"处理完成，Alpha状态: {status}, 颜色: {color}")
            return result
            
        except Exception as e:
            logger.error(f"回测过程中出错: {e}")
            return None

def get_api():
    """获取API封装实例"""
    return WqApiSimple() 