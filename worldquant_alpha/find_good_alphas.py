#!/usr/bin/env python3
"""
查找优质Alpha的脚本
条件：
1. Sharpe比率 >= 1.25
2. 自相关性 <= 0.7，设置为绿色
3. 如果check失败，将颜色标注为黄色
"""
import os
import logging
import json
from datetime import datetime
from dotenv import load_dotenv

try:
    from wd_lib_wrapper import get_api
except ImportError:
    from worldquant_alpha.wd_lib_wrapper import get_api

# 加载环境变量
load_dotenv()

# 配置日志
log_level_str = os.getenv('LOG_LEVEL', 'INFO')
log_level = getattr(logging, log_level_str.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def find_good_alphas(api, sharpe_threshold=1.25):
    """查找符合条件的Alpha"""
    good_alphas = []
    offset = 0
    limit = 100
    
    while True:
        # 获取Alpha列表
        filters = {
            "is.sharpe>": sharpe_threshold,
            "order": "-is.sharpe",
            "hidden": "false"
        }
        
        alphas = api.get_alphas(limit=limit, offset=offset, filters=filters)
        
        if not alphas:
            break
            
        for alpha in alphas:
            alpha_id = alpha.get("id")
            # 检查Alpha状态
            is_valid, color = api.check_alpha_status(alpha_id)
            if is_valid:
                alpha_info = {
                    "id": alpha_id,
                    "name": alpha.get("name"),
                    "sharpe": alpha.get("is", {}).get("sharpe"),
                    "fitness": alpha.get("is", {}).get("fitness"),
                    "turnover": alpha.get("is", {}).get("turnover"),
                    "expression": alpha.get("regular", {}).get("code"),
                    "created_at": alpha.get("dateCreated"),
                    "color": color
                }
                good_alphas.append(alpha_info)
                logger.info(f"找到符合条件的Alpha: {alpha_id}, 颜色: {color}")
        
        offset += limit
        logger.info(f"已处理 {offset} 个Alpha")
    
    return good_alphas

def save_results(alphas):
    """保存结果到文件"""
    if not alphas:
        logger.info("没有找到符合条件的Alpha")
        return
    
    # 创建results目录
    os.makedirs("results", exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results/good_alphas_{timestamp}.json"
    
    # 保存结果
    with open(filename, "w") as f:
        json.dump(alphas, f, indent=2)
    
    logger.info(f"结果已保存到 {filename}")

def main():
    """主函数"""
    logger.info("开始查找优质Alpha")
    
    try:
        # 初始化API
        api = get_api()
        
        # 查找符合条件的Alpha
        good_alphas = find_good_alphas(api)
        
        # 打印结果
        if good_alphas:
            logger.info(f"找到 {len(good_alphas)} 个符合条件的Alpha")
            for i, alpha in enumerate(good_alphas, 1):
                logger.info(f"\nAlpha {i}:")
                logger.info(f"ID: {alpha['id']}")
                logger.info(f"名称: {alpha['name']}")
                logger.info(f"Sharpe比率: {alpha['sharpe']}")
                logger.info(f"颜色: {alpha['color']}")
                logger.info(f"表达式: {alpha['expression']}")
                logger.info(f"创建时间: {alpha['created_at']}")
        else:
            logger.info("没有找到符合条件的Alpha")
        
        # 保存结果
        save_results(good_alphas)
        
    except Exception as e:
        logger.error(f"程序运行时发生错误: {e}")

if __name__ == "__main__":
    main() 