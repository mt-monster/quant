#!/usr/bin/env python3
"""
批量Alpha生成和回测脚本
自动从多个数据字段和参数组合生成Alpha，执行回测并选出最优Alpha
"""

import os
import time
import json
import pandas as pd
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv
from typing import List, Dict, Any
from datetime import datetime

from wd_lib import WorldQuantClient
from wd_lib.config.constants import NEUTRALIZATIONS, UNIVERSES

# 加载环境变量
load_dotenv()

# 输出目录
OUTPUT_DIR = "results"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def search_fields(client: WorldQuantClient, keywords: List[str], field_type: str = None) -> pd.DataFrame:
    """
    搜索匹配关键词的数据字段
    
    参数:
    - client: WorldQuantClient实例
    - keywords: 关键词列表
    - field_type: 字段类型过滤
    
    返回:
    - 匹配的数据字段DataFrame
    """
    print(f"搜索匹配关键词的数据字段: {keywords}...")
    
    search_scope = {
        'instrumentType': 'EQUITY',
        'region': 'USA',
        'delay': 1,
        'universe': 'TOP3000'
    }
    
    all_fields = pd.DataFrame()
    
    for keyword in keywords:
        fields_df = client.get_datafields(
            search_scope=search_scope,
            search=keyword,
            field_type=field_type
        )
        
        if not fields_df.empty:
            all_fields = pd.concat([all_fields, fields_df]).drop_duplicates()
    
    print(f"找到 {len(all_fields)} 个匹配的数据字段")
    return all_fields


def generate_alphas(client: WorldQuantClient, datafields_df: pd.DataFrame) -> List[str]:
    """
    从数据字段生成Alpha表达式
    
    参数:
    - client: WorldQuantClient实例
    - datafields_df: 数据字段DataFrame
    
    返回:
    - Alpha表达式列表
    """
    print("从数据字段生成Alpha表达式...")
    
    # 第一步：处理字段
    processed_fields = client.process_datafields(datafields_df)
    
    # 限制字段数量以避免生成过多Alpha
    selected_fields = processed_fields[:10] if len(processed_fields) > 10 else processed_fields
    
    # 为每个字段生成多个Alpha表达式
    alphas = []
    
    for field in selected_fields:
        # 基本Alpha
        alphas.append(f"rank({field})")
        alphas.append(f"zscore({field})")
        
        # 时间序列Alpha
        alphas.extend(client.create_ts_alpha("ts_mean", field, [5, 10, 22]))
        alphas.extend(client.create_ts_alpha("ts_rank", field, [5, 10, 22]))
        
        # 相关性Alpha
        alphas.append(f"rank(correlation({field}, volume, 10))")
        
        # 更复杂的Alpha
        alpha_builder = client.create_alpha_builder()
        alpha_builder.field(field).ts_mean(5).div(
            client.create_alpha_builder().field(field).ts_mean(22)
        ).rank()
        alphas.append(alpha_builder.build())
    
    # 去除重复项
    unique_alphas = list(set(alphas))
    
    print(f"生成了 {len(unique_alphas)} 个Alpha表达式")
    return unique_alphas


def batch_backtest(client: WorldQuantClient, alphas: List[str], settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    批量执行回测
    
    参数:
    - client: WorldQuantClient实例
    - alphas: Alpha表达式列表
    - settings: 回测设置
    
    返回:
    - 回测结果列表
    """
    print(f"开始批量回测 {len(alphas)} 个Alpha...")
    
    max_parallel = 5  # 最大并行数
    chunk_size = 10   # 每次处理的Alpha数量
    
    results = []
    
    # 按块处理，避免一次处理太多Alpha
    for i in range(0, len(alphas), chunk_size):
        chunk = alphas[i:i+chunk_size]
        print(f"处理第 {i//chunk_size + 1} 批，共 {len(chunk)} 个Alpha")
        
        try:
            chunk_results = client.run_batch_backtest(chunk, settings, max_parallel)
            results.extend(chunk_results)
            
            # 显示进度
            print(f"批次完成，当前已处理 {len(results)}/{len(alphas)} 个Alpha")
            
            # 暂停一下，避免API限制
            time.sleep(5)
            
        except Exception as e:
            print(f"批次处理出错: {str(e)}")
    
    print(f"批量回测完成，成功 {len(results)}/{len(alphas)} 个")
    return results


def analyze_and_select(client: WorldQuantClient, results: List[Dict[str, Any]], top_n: int = 5) -> pd.DataFrame:
    """
    分析回测结果并选择最优Alpha
    
    参数:
    - client: WorldQuantClient实例
    - results: 回测结果列表
    - top_n: 返回的最优Alpha数量
    
    返回:
    - 最优Alpha的DataFrame
    """
    print("分析回测结果...")
    
    if not results:
        print("没有回测结果可分析")
        return pd.DataFrame()
    
    # 获取整体性能指标
    metrics = client.calculate_performance_metrics(results)
    print("\n整体性能指标:")
    print(f"总计 {metrics.get('count')} 个Alpha")
    print(f"平均Sharpe比率: {metrics.get('sharpe', {}).get('mean'):.4f}")
    print(f"平均换手率: {metrics.get('turnover', {}).get('mean'):.4f}")
    print(f"最大Sharpe比率: {metrics.get('sharpe', {}).get('max'):.4f}")
    
    # 对每个结果进行分析
    analyses = []
    for result in results:
        analysis = client.analyze_backtest_result(result)
        analyses.append({
            'alpha_id': result.get('alpha_id'),
            'expression': result.get('expression'),
            'sharpe': result.get('sharpe', 0),
            'turnover': result.get('turnover', 0),
            'fitness': result.get('fitness', 0),
            'color': result.get('color'),
            'status': result.get('status'),
            'quality_score': analysis.get('quality', {}).get('score', 0),
            'quality_rating': analysis.get('quality', {}).get('rating', ''),
            'comments': analysis.get('quality', {}).get('comments', '')
        })
    
    # 转换为DataFrame
    df = pd.DataFrame(analyses)
    
    # 按质量得分和Sharpe比率排序
    if 'quality_score' in df.columns and 'sharpe' in df.columns:
        df['combined_score'] = df['quality_score'] + df['sharpe']
        df = df.sort_values('combined_score', ascending=False)
    else:
        df = df.sort_values('sharpe', ascending=False)
    
    # 选出最优的top_n个Alpha
    top_alphas = df.head(top_n)
    
    print(f"\n选出的前 {top_n} 个Alpha:")
    for i, row in top_alphas.iterrows():
        print(f"{i+1}. Alpha ID: {row.get('alpha_id')}")
        print(f"   Sharpe比率: {row.get('sharpe'):.4f}")
        print(f"   质量得分: {row.get('quality_score')}")
        print(f"   评级: {row.get('quality_rating')}")
        print(f"   表达式: {row.get('expression')[:100]}...")
        print()
    
    return top_alphas


def save_results(results: List[Dict[str, Any]], top_alphas: pd.DataFrame, settings: Dict[str, Any]) -> str:
    """
    保存回测结果和最优Alpha
    
    参数:
    - results: 回测结果列表
    - top_alphas: 最优Alpha的DataFrame
    - settings: 回测设置
    
    返回:
    - 保存的文件路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OUTPUT_DIR}/alpha_results_{timestamp}.json"
    
    output = {
        'timestamp': timestamp,
        'settings': settings,
        'results_count': len(results),
        'top_alphas': top_alphas.to_dict(orient='records'),
        'all_results': results
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"结果已保存到: {filename}")
    
    # 同时保存最优Alpha到CSV
    csv_file = f"{OUTPUT_DIR}/top_alphas_{timestamp}.csv"
    top_alphas.to_csv(csv_file, index=False)
    print(f"最优Alpha已保存到: {csv_file}")
    
    return filename


def main():
    print("初始化WorldQuant客户端...")
    client = WorldQuantClient()
    
    # 登录平台
    if not client.login():
        print("登录失败，请检查环境变量中的用户名和密码")
        return
    
    print("登录成功!")
    
    # 1. 搜索数据字段
    keywords = ["close", "volume", "returns", "price", "earnings"]
    datafields_df = search_fields(client, keywords, field_type="MATRIX")
    
    if datafields_df.empty:
        print("未找到数据字段，无法继续")
        return
    
    # 2. 生成Alpha表达式
    alphas = generate_alphas(client, datafields_df)
    
    if not alphas:
        print("未生成Alpha表达式，无法继续")
        return
    
    # 3. 执行批量回测
    settings = {
        "instrumentType": "EQUITY",
        "region": "USA", 
        "universe": "TOP3000", 
        "delay": 1,
        "decay": 0.2,
        "neutralization": "INDUSTRY",
        "truncation": 0.08,
        "pasteurization": "ON",
        "nanHandling": "ON"
    }
    
    results = batch_backtest(client, alphas, settings)
    
    if not results:
        print("回测未返回结果，无法继续")
        return
    
    # 4. 分析结果并选择最优Alpha
    top_alphas = analyze_and_select(client, results, top_n=5)
    
    # 5. 保存结果
    save_results(results, top_alphas, settings)
    
    print("\n批量Alpha生成和回测流程完成!")


if __name__ == "__main__":
    main() 