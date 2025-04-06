"""
WorldQuant Brain API辅助函数模块
提供各种工具函数
"""

import time
import random
import logging
from typing import List, Dict, Any, Tuple

# 配置日志
logger = logging.getLogger(__name__)

def safe_sleep(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """
    安全延迟函数，防止API限制
    
    参数:
    - min_seconds: 最小延迟秒数
    - max_seconds: 最大延迟秒数
    """
    # 随机延迟避免请求过于规律
    delay = min_seconds + random.random() * (max_seconds - min_seconds)
    time.sleep(delay)


def load_task_pool(
    alpha_list: List[Tuple[str, int]], 
    limit_of_children_simulations: int, 
    limit_of_multi_simulations: int
) -> List[List[List[Tuple[str, int]]]]:
    """
    将Alpha列表分组用于批量回测
    
    参数:
    - alpha_list: Alpha列表，每项为(alpha, decay)元组
    - limit_of_children_simulations: 每个多重模拟中的子模拟数量
    - limit_of_multi_simulations: 同时运行的多重模拟数量
    
    返回:
    - 分组后的Alpha列表
    """
    # 将alpha_list按limit_of_children_simulations分组
    tasks = [alpha_list[i:i + limit_of_children_simulations] 
             for i in range(0, len(alpha_list), limit_of_children_simulations)]
    
    # 将tasks按limit_of_multi_simulations分组
    pools = [tasks[i:i + limit_of_multi_simulations] 
             for i in range(0, len(tasks), limit_of_multi_simulations)]
    
    logger.info(f"将{len(alpha_list)}个Alpha分成{len(pools)}个池，每个池包含最多{limit_of_multi_simulations}个任务组")
    
    return pools


def generate_sim_data(
    alpha_list: List[Tuple[str, int]], 
    region: str, 
    universe: str, 
    neutralization: str
) -> List[Dict[str, Any]]:
    """
    为Alpha列表生成模拟数据
    
    参数:
    - alpha_list: Alpha列表，每项为(alpha_expression, decay)元组
    - region: 地区代码
    - universe: 宇宙名称
    - neutralization: 中性化参数
    
    返回:
    - 模拟数据字典列表
    """
    sim_data_list = []
    
    for alpha, decay in alpha_list:
        simulation_data = {
            'type': 'REGULAR',
            'settings': {
                'instrumentType': 'EQUITY',
                'region': region,
                'universe': universe,
                'delay': 1,
                'decay': decay,
                'neutralization': neutralization,
                'truncation': 0.08,
                'pasteurization': 'ON',
                'testPeriod': 'P0Y',
                'unitHandling': 'VERIFY',
                'nanHandling': 'ON',
                'language': 'FASTEXPR',
                'visualization': False,
            },
            'regular': alpha
        }
        
        sim_data_list.append(simulation_data)
    
    logger.info(f"为{len(alpha_list)}个Alpha生成模拟参数，地区: {region}, 宇宙: {universe}, 中性化: {neutralization}")
    return sim_data_list 