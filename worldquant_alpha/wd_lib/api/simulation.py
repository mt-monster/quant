"""
模拟API
提供提交和管理WorldQuant模拟的功能
"""

import time
import logging
from typing import Dict, List, Any, Tuple
from urllib.parse import urljoin

from ..auth import get_session
from ..config.constants import API_BASE_URL, REQUEST_TIMEOUT
from ..utils.retry import with_retry
from ..utils.exceptions import SimulationError, APIError

# 配置日志
logger = logging.getLogger(__name__)

@with_retry()
def submit_simulation(
    simulation_data: Dict[str, Any],
    session=None,
    max_retries: int = 3
) -> Tuple[bool, str]:
    """
    提交模拟请求
    
    参数:
    - simulation_data: 模拟请求数据
    - session: 会话对象，如果为None则使用当前会话
    - max_retries: 最大重试次数
    
    返回:
    - 成功时返回(True, alpha_id)，失败时返回(False, error_message)
    """
    if session is None:
        session = get_session()
    
    if 'regular' in simulation_data:
        logger.info(f"开始提交Alpha模拟: {simulation_data.get('regular', '')[:50]}...")
    else:
        logger.info("开始提交Alpha模拟...")
    
    retries = 0
    while retries < max_retries:
        try:
            sim_resp = session.post(
                urljoin(API_BASE_URL, 'simulations'),
                json=simulation_data,
                timeout=REQUEST_TIMEOUT
            )
            
            # 如果返回4xx或5xx错误
            if sim_resp.status_code >= 400:
                logger.error(f"模拟请求失败: {sim_resp.status_code} - {sim_resp.text}")
                retries += 1
                time.sleep(5)  # 等待5秒后重试
                continue
            
            sim_progress_url = sim_resp.headers.get('Location')
            if not sim_progress_url:
                logger.error("模拟响应中没有进度URL")
                retries += 1
                time.sleep(5)
                continue
                
            logger.info(f"成功提交模拟请求，进度URL: {sim_progress_url}")
            
            # 监控模拟进度
            max_progress_checks = 300  # 最大检查次数
            progress_checks = 0
            
            while progress_checks < max_progress_checks:
                try:
                    sim_progress_resp = session.get(sim_progress_url)
                    
                    if sim_progress_resp.status_code >= 400:
                        logger.error(f"获取模拟进度失败: {sim_progress_resp.status_code} - {sim_progress_resp.text}")
                        time.sleep(5)
                        progress_checks += 1
                        continue

                    retry_after_sec = float(sim_progress_resp.headers.get("Retry-After", 0))
                    sim_progress_data = sim_progress_resp.json()
                    
                    if retry_after_sec == 0:  # 模拟完成
                        logger.info("模拟计算完成!")
                        
                        # 获取结果
                        try:
                            result = sim_progress_resp.json()
                            alpha_id = result.get("alpha")
                            if alpha_id:
                                logger.info(f"模拟成功，获得Alpha ID: {alpha_id}")
                                return True, alpha_id
                            else:
                                logger.error("模拟完成但未获得Alpha ID")
                                return False, "模拟完成但未获得Alpha ID"
                        except Exception as e:
                            logger.error(f"解析模拟结果时出错: {str(e)}")
                            return False, f"解析模拟结果时出错: {str(e)}"
                    
                    # 如果需要等待，则等待指定的时间
                    logger.info(f"模拟进行中，进度 {sim_progress_data.get('progress')} ,已检查 {progress_checks}/{max_progress_checks}...")
                    time.sleep(retry_after_sec+1)
                    progress_checks += 1
                
                except Exception as e:
                    logger.error(f"检查模拟进度时出错: {str(e)}")
                    time.sleep(5)
                    progress_checks += 1
            
            # 如果超过最大检查次数
            logger.error("模拟进度检查超时")
            return False, "模拟进度检查超时"
        
        except Exception as e:
            logger.error(f"提交模拟请求时出错: {str(e)}")
            retries += 1
            time.sleep(5)
    
    # 如果所有重试都失败
    error_msg = f"在{max_retries}次尝试后提交模拟请求失败"
    logger.error(error_msg)
    raise SimulationError(error_msg)

@with_retry()
def get_simulation_status(simulation_id: str, session=None) -> Dict[str, Any]:
    """
    获取模拟状态
    
    参数:
    - simulation_id: 模拟ID
    - session: 会话对象，如果为None则使用当前会话
    
    返回:
    - 模拟状态字典
    """
    if session is None:
        session = get_session()
    
    logger.info(f"获取模拟状态: {simulation_id}")
    
    try:
        response = session.get(urljoin(API_BASE_URL, f"simulations/{simulation_id}"))
        response.raise_for_status()
        
        status = response.json()
        logger.info(f"成功获取模拟状态: {simulation_id}")
        
        return status
    except Exception as e:
        logger.error(f"获取模拟状态失败: {str(e)}")
        raise APIError(f"获取模拟状态失败: {str(e)}") 