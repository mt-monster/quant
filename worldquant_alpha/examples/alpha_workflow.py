#!/usr/bin/env python3
"""
WorldQuant Alpha创建、回测和分析工作流程示例
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from typing import List, Dict, Any

from wd_lib import WorldQuantClient
from wd_lib.utils.exceptions import ValidationError

# 加载环境变量（确保.env文件中有WQ_USERNAME和WQ_PASSWORD）
load_dotenv()

def create_alphas(client: WorldQuantClient, field: str) -> List[str]:
    """创建多个不同的Alpha表达式"""
    alphas = []
    
    # 使用构建器API创建Alpha
    alpha1 = client.create_alpha_builder()\
        .field(field)\
        .ts_mean(5)\
        .div(
            client.create_alpha_builder().field(field).ts_mean(22)
        )\
        .rank()\
        .build()
    alphas.append(alpha1)
    
    # 使用工厂方法创建时间序列Alpha
    alphas.extend(client.create_ts_alpha("ts_rank", field, [5, 10, 22]))
    
    # 简单Alpha表达式
    alphas.append(f"rank(correlation({field}, volume, 5))")
    alphas.append(f"rank(ts_zscore({field}, 10))")
    
    return alphas

def main():
    print("初始化WorldQuant客户端...")
    client = WorldQuantClient()
    
    # 登录平台
    if not client.login():
        print("登录失败，请检查环境变量中的用户名和密码")
        return
    
    print("登录成功!")
    
    # 获取数据字段
    print("\n获取数据字段...")
    search_scope = {
        'instrumentType': 'EQUITY',
        'region': 'USA',
        'delay': 1,
        'universe': 'TOP3000'
    }
    
    datafields_df = client.get_datafields(
        search_scope=search_scope,
        search="close"
    )
    
    if datafields_df.empty:
        print("未找到数据字段")
        return
    
    print(f"找到 {len(datafields_df)} 个数据字段")
    
    # 处理数据字段，生成Alpha友好的格式
    processed_fields = client.process_datafields(datafields_df)
    print(f"生成 {len(processed_fields)} 个预处理字段")
    
    # 创建Alpha表达式
    print("\n创建Alpha表达式...")
    alphas = create_alphas(client, "close")
    print(f"创建了 {len(alphas)} 个Alpha表达式")
    
    for i, alpha in enumerate(alphas[:3]):  # 只显示前3个
        print(f"Alpha {i+1}: {alpha[:100]}...")
    
    # 执行单个回测
    print("\n执行单个回测...")
    settings = {
        "instrumentType": "EQUITY",
        "region": "USA", 
        "universe": "TOP3000", 
        "delay": 1,
        "decay": 0.5,  # 添加衰减因子
        "neutralization": "INDUSTRY",
        "truncation": 0.08
    }
    
    try:
        result = client.run_backtest(alphas[0], settings)
        
        if result:
            print("\n回测结果:")
            print(f"Alpha ID: {result.get('alpha_id')}")
            print(f"Sharpe比率: {result.get('sharpe')}")
            print(f"换手率: {result.get('turnover')}")
            print(f"状态: {result.get('status')}")
            print(f"颜色: {result.get('color')}")
            
            # 分析结果
            print("\n分析回测结果...")
            analysis = client.analyze_backtest_result(result)
            
            print(f"质量评级: {analysis.get('quality', {}).get('rating')}")
            print(f"质量得分: {analysis.get('quality', {}).get('score')}")
            print(f"评论: {analysis.get('quality', {}).get('comments')}")
            
            if analysis.get('suggestions'):
                print("\n改进建议:")
                for suggestion in analysis.get('suggestions'):
                    print(f"- {suggestion}")
        else:
            print("回测失败")
        
        # 批量回测
        print("\n执行批量回测...")
        batch_results = client.run_batch_backtest(
            alphas[1:4],  # 使用另外3个Alpha表达式
            settings=settings,
            max_parallel=2
        )
        
        if batch_results:
            print(f"批量回测完成，成功 {len(batch_results)} 个")
            
            # 计算性能指标
            metrics = client.calculate_performance_metrics(batch_results)
            
            print("\n整体性能指标:")
            print(f"平均Sharpe比率: {metrics.get('sharpe', {}).get('mean'):.4f}")
            print(f"平均换手率: {metrics.get('turnover', {}).get('mean'):.4f}")
            print(f"颜色分布: {metrics.get('color_distribution')}")
            print(f"成功率: {metrics.get('success_rate', 0):.2%}")
        else:
            print("批量回测未返回结果")
        
    except ValidationError as e:
        print(f"Alpha验证错误: {str(e)}")
    except Exception as e:
        print(f"发生错误: {str(e)}")
    
    print("\n示例运行完成")


if __name__ == "__main__":
    main() 