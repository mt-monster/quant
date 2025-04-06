#!/usr/bin/env python3
"""
批量Alpha回测示例脚本
展示如何简单地批量运行多个Alpha回测
"""
import logging
import os
import sys
import time
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from dotenv import load_dotenv

# 将项目根目录添加到模块搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from wd_lib_wrapper import get_api

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建结果目录
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

def backtest_alpha(api, alpha_expression, settings=None):
    """运行单个Alpha回测"""
    try:
        logger.info(f"开始回测Alpha: {alpha_expression[:50]}...")
        result = api.run_backtest(alpha_expression, settings)
        
        if result:
            logger.info(f"回测成功，Alpha ID: {result.get('id')}, 夏普: {result.get('sharpe')}")
            return result
        else:
            logger.warning(f"回测失败: {alpha_expression[:50]}...")
            return None
    except Exception as e:
        logger.error(f"回测过程中出错: {str(e)}")
        return None

def batch_backtest(alpha_expressions, max_workers=3):
    """批量回测多个Alpha表达式"""
    logger.info(f"开始批量回测 {len(alpha_expressions)} 个Alpha...")
    
    # 初始化API
    api = get_api()
    
    # 回测设置
    settings = {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "decay": 0,
        "neutralization": "SUBINDUSTRY",
        "truncation": 0.08,
        "pasteurization": "ON"
    }
    
    # 使用线程池进行并行回测
    results = []
    successful = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(backtest_alpha, api, expr, settings) for expr in alpha_expressions]
        
        for future in futures:
            result = future.result()
            if result:
                results.append(result)
                successful += 1
            else:
                failed += 1
    
    logger.info(f"批量回测完成，成功: {successful}, 失败: {failed}")
    
    # 保存结果
    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(RESULTS_DIR, f"batch_backtest_{timestamp}.json")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"结果已保存到: {filename}")
    
    return results

def main():
    """主函数"""
    print("开始批量Alpha回测示例...")
    
    # 示例Alpha表达式列表
    alpha_expressions = [
        "rank(close)",
        "rank(volume)",
        "rank(correlation(close, volume, 5))",
        "rank(ts_mean(close, 5) / ts_mean(close, 22))",
        "rank(ts_min(close, 5) / close)"
    ]
    
    try:
        # 执行批量回测
        results = batch_backtest(alpha_expressions, max_workers=1)
        
        # 打印结果摘要
        if results:
            print("\n回测结果摘要:")
            for i, result in enumerate(results, 1):
                print(f"{i}. Alpha ID: {result.get('id')}")
                print(f"   夏普比率: {result.get('sharpe')}")
                print(f"   状态: {result.get('status')}")
                print(f"   颜色: {result.get('color')}")
                print()
        else:
            print("所有回测均失败")
    
    except Exception as e:
        print(f"批量回测过程中出错: {str(e)}")
    
    print("\n示例运行完成")

if __name__ == "__main__":
    main() 