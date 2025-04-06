#!/usr/bin/env python3
"""
Alpha自动优化脚本
对已有Alpha进行参数调整和操作符变换，以提高性能
"""

import os
import re
import json
import time
import logging
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from typing import List, Dict, Any, Tuple
from datetime import datetime

from wd_lib import WorldQuantClient
from wd_lib.alpha.validator import AlphaValidator
from wd_lib.utils.exceptions import ValidationError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='alpha_optimizer.log'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 输出目录
OUTPUT_DIR = "results/optimized"
os.makedirs(OUTPUT_DIR, exist_ok=True)


class AlphaOptimizer:
    """Alpha优化器类"""
    
    def __init__(self, client: WorldQuantClient):
        """
        初始化优化器
        
        参数:
        - client: WorldQuantClient实例
        """
        self.client = client
        self.base_settings = {
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
        logger.info("Alpha优化器初始化完成")
    
    def _extract_parameters(self, alpha: str) -> Dict[str, Any]:
        """
        从Alpha表达式中提取参数
        
        参数:
        - alpha: Alpha表达式
        
        返回:
        - 参数字典
        """
        params = {}
        
        # 提取时间窗口参数
        time_windows = re.findall(r'ts_\w+\([^,]+,\s*(\d+)', alpha)
        if time_windows:
            params['time_windows'] = [int(w) for w in time_windows]
        
        # 提取相关系数窗口
        corr_windows = re.findall(r'correlation\([^,]+,[^,]+,\s*(\d+)', alpha)
        if corr_windows:
            params['correlation_windows'] = [int(w) for w in corr_windows]
        
        # 提取量化参数
        quantile_params = re.findall(r'quantile\([^,]+,\s*(\d+)', alpha)
        if quantile_params:
            params['quantile_bins'] = [int(q) for q in quantile_params]
        
        logger.debug(f"从Alpha中提取的参数: {params}")
        return params
    
    def _create_parameter_variations(self, alpha: str, params: Dict[str, Any]) -> List[str]:
        """
        创建参数变种
        
        参数:
        - alpha: 原始Alpha表达式
        - params: 原始参数字典
        
        返回:
        - 变种Alpha表达式列表
        """
        variations = []
        
        # 时间窗口变化
        if 'time_windows' in params:
            for old_window in params['time_windows']:
                # 创建±30%的窗口变化
                new_windows = [
                    max(2, int(old_window * 0.7)),  # 缩小30%
                    int(old_window * 1.3)           # 扩大30%
                ]
                
                for new_window in new_windows:
                    if new_window != old_window:
                        # 替换时间窗口
                        new_alpha = re.sub(
                            rf'(ts_\w+\([^,]+,\s*){old_window}', 
                            rf'\g<1>{new_window}', 
                            alpha
                        )
                        variations.append(new_alpha)
        
        # 相关系数窗口变化
        if 'correlation_windows' in params:
            for old_window in params['correlation_windows']:
                new_windows = [
                    max(2, int(old_window * 0.7)),
                    int(old_window * 1.3)
                ]
                
                for new_window in new_windows:
                    if new_window != old_window:
                        new_alpha = re.sub(
                            rf'(correlation\([^,]+,[^,]+,\s*){old_window}', 
                            rf'\g<1>{new_window}', 
                            alpha
                        )
                        variations.append(new_alpha)
        
        # 量化参数变化
        if 'quantile_bins' in params:
            for old_bin in params['quantile_bins']:
                new_bins = [
                    max(2, int(old_bin * 0.5)),
                    int(old_bin * 1.5)
                ]
                
                for new_bin in new_bins:
                    if new_bin != old_bin and 2 <= new_bin <= 100:
                        new_alpha = re.sub(
                            rf'(quantile\([^,]+,\s*){old_bin}', 
                            rf'\g<1>{new_bin}', 
                            alpha
                        )
                        variations.append(new_alpha)
        
        logger.info(f"为Alpha创建了{len(variations)}个参数变种")
        return variations
    
    def _create_operation_variations(self, alpha: str) -> List[str]:
        """
        创建操作符变种
        
        参数:
        - alpha: 原始Alpha表达式
        
        返回:
        - 变种Alpha表达式列表
        """
        variations = []
        
        # 外层操作符变换
        if alpha.startswith("rank("):
            variations.append(alpha.replace("rank(", "zscore(", 1))
        elif alpha.startswith("zscore("):
            variations.append(alpha.replace("zscore(", "rank(", 1))
        
        # 时间序列操作符变换
        ts_ops = {
            "ts_mean": ["ts_median", "ts_sum"],
            "ts_rank": ["ts_zscore"],
            "ts_zscore": ["ts_rank"],
            "ts_delta": ["ts_mean"],
            "ts_sum": ["ts_mean"]
        }
        
        for old_op, new_ops in ts_ops.items():
            if old_op in alpha:
                for new_op in new_ops:
                    new_alpha = alpha.replace(old_op, new_op)
                    variations.append(new_alpha)
        
        # 添加转置操作
        if not alpha.startswith("reverse("):
            variations.append(f"reverse({alpha})")
        
        logger.info(f"为Alpha创建了{len(variations)}个操作符变种")
        return variations
    
    def _create_combinations(self, alpha: str) -> List[str]:
        """
        创建与其他Alpha组合的变种
        
        参数:
        - alpha: 原始Alpha表达式
        
        返回:
        - 变种Alpha表达式列表
        """
        variations = []
        
        # 基础字段
        base_fields = ["close", "volume", "returns"]
        
        # 创建alpha与基础字段的组合
        for field in base_fields:
            # 加权平均
            weighted_avg = f"(0.7 * ({alpha}) + 0.3 * rank({field}))"
            variations.append(weighted_avg)
            
            # 相关性
            correlation = f"rank(correlation({alpha}, {field}, 10))"
            variations.append(correlation)
        
        logger.info(f"为Alpha创建了{len(variations)}个组合变种")
        return variations
    
    def generate_variations(self, alpha: str, include_combinations: bool = True) -> List[str]:
        """
        为Alpha生成所有可能的变种
        
        参数:
        - alpha: 原始Alpha表达式
        - include_combinations: 是否包含组合变种
        
        返回:
        - 变种Alpha表达式列表
        """
        logger.info(f"为Alpha生成变种: {alpha[:100]}...")
        
        # 验证Alpha表达式
        is_valid, error_msg = AlphaValidator.validate(alpha)
        if not is_valid:
            logger.error(f"Alpha表达式无效: {error_msg}")
            return []
        
        variations = [alpha]  # 包含原始Alpha
        
        # 提取参数
        params = self._extract_parameters(alpha)
        
        # 创建参数变种
        param_variations = self._create_parameter_variations(alpha, params)
        variations.extend(param_variations)
        
        # 创建操作符变种
        op_variations = self._create_operation_variations(alpha)
        variations.extend(op_variations)
        
        # 创建组合变种
        if include_combinations:
            combo_variations = self._create_combinations(alpha)
            variations.extend(combo_variations)
        
        # 过滤掉无效的Alpha表达式
        valid_variations = []
        for var in variations:
            is_valid, _ = AlphaValidator.validate(var)
            if is_valid:
                valid_variations.append(var)
            else:
                logger.debug(f"过滤掉无效变种: {var[:100]}...")
        
        # 去除重复项
        unique_variations = list(set(valid_variations))
        
        logger.info(f"生成了{len(unique_variations)}个有效变种")
        return unique_variations
    
    def optimize(self, alpha: str, max_variations: int = 10) -> Dict[str, Any]:
        """
        优化Alpha
        
        参数:
        - alpha: 原始Alpha表达式
        - max_variations: 最大测试变种数
        
        返回:
        - 优化结果
        """
        logger.info(f"开始优化Alpha: {alpha[:100]}...")
        
        # 生成变种
        variations = self.generate_variations(alpha)
        
        # 限制变种数量
        if len(variations) > max_variations:
            logger.info(f"变种过多，只选择{max_variations}个")
            variations = variations[:max_variations]
        
        # 回测原始Alpha
        logger.info("回测原始Alpha...")
        base_result = self.client.run_backtest(alpha, self.base_settings)
        
        if not base_result:
            logger.error("原始Alpha回测失败")
            return {
                'success': False,
                'message': "原始Alpha回测失败",
                'original_alpha': alpha,
                'original_result': None,
                'variations': [],
                'best_variation': None
            }
        
        logger.info(f"原始Alpha回测结果: Sharpe={base_result.get('sharpe', 0):.4f}, "
                   f"Turnover={base_result.get('turnover', 0):.4f}")
        
        # 回测变种
        logger.info(f"回测{len(variations)-1}个Alpha变种...")
        results = []
        
        # 添加原始Alpha结果
        results.append({
            'alpha': alpha,
            'is_original': True,
            'result': base_result
        })
        
        # 回测其他变种
        for i, var_alpha in enumerate(variations):
            if var_alpha == alpha:
                continue  # 跳过原始Alpha
                
            logger.info(f"回测变种 {i+1}/{len(variations)-1}: {var_alpha[:100]}...")
            try:
                result = self.client.run_backtest(var_alpha, self.base_settings)
                if result:
                    results.append({
                        'alpha': var_alpha,
                        'is_original': False,
                        'result': result
                    })
                    logger.info(f"变种回测结果: Sharpe={result.get('sharpe', 0):.4f}, "
                               f"Turnover={result.get('turnover', 0):.4f}")
                else:
                    logger.warning(f"变种回测失败: {var_alpha[:100]}...")
            except Exception as e:
                logger.error(f"变种回测出错: {str(e)}")
            
            # 暂停以避免API限制
            time.sleep(2)
        
        # 分析结果，寻找最佳变种
        logger.info("分析所有回测结果...")
        best_variation = self._find_best_variation(results, base_result)
        
        optimization_result = {
            'success': True,
            'message': "优化完成",
            'original_alpha': alpha,
            'original_result': base_result,
            'variations': results,
            'best_variation': best_variation
        }
        
        return optimization_result
    
    def _find_best_variation(self, results: List[Dict[str, Any]], base_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        找出最佳变种
        
        参数:
        - results: 所有回测结果
        - base_result: 原始Alpha回测结果
        
        返回:
        - 最佳变种信息
        """
        if not results:
            return None
        
        # 计算各种指标的改进情况
        improvements = []
        base_sharpe = base_result.get('sharpe', 0)
        base_turnover = base_result.get('turnover', 0) or 1.0  # 避免除零
        
        for item in results:
            if item.get('is_original', False):
                continue  # 跳过原始Alpha
                
            result = item.get('result', {})
            sharpe = result.get('sharpe', 0)
            turnover = result.get('turnover', 0) or 1.0
            
            # 计算综合改进分数
            sharpe_improvement = (sharpe - base_sharpe) / max(0.01, abs(base_sharpe))
            turnover_improvement = (base_turnover - turnover) / base_turnover
            
            # 综合得分 = Sharpe提升 * 0.7 + 换手率改善 * 0.3
            score = sharpe_improvement * 0.7 + turnover_improvement * 0.3
            
            improvements.append({
                'alpha': item.get('alpha'),
                'result': result,
                'sharpe': sharpe,
                'turnover': turnover,
                'sharpe_improvement': sharpe_improvement,
                'turnover_improvement': turnover_improvement,
                'score': score
            })
        
        # 按综合得分排序
        improvements.sort(key=lambda x: x.get('score', -float('inf')), reverse=True)
        
        if not improvements:
            return None
            
        best = improvements[0]
        
        # 如果最佳变种的Sharpe比率不足1.0或者综合得分没有提升，则不建议替换
        if best.get('sharpe', 0) < 1.0 or best.get('score', 0) <= 0:
            return {
                'alpha': None,
                'result': None,
                'improvements': improvements,
                'recommendation': "保持原始Alpha"
            }
        
        return {
            'alpha': best.get('alpha'),
            'result': best.get('result'),
            'improvements': improvements,
            'recommendation': "替换为优化Alpha"
        }
    
    def save_optimization_result(self, result: Dict[str, Any]) -> str:
        """
        保存优化结果
        
        参数:
        - result: 优化结果
        
        返回:
        - 保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{OUTPUT_DIR}/optimization_{timestamp}.json"
        
        # 简化变种结果以减小文件大小
        simplified_results = []
        for var in result.get('variations', []):
            simplified_results.append({
                'alpha': var.get('alpha'),
                'is_original': var.get('is_original', False),
                'sharpe': var.get('result', {}).get('sharpe'),
                'turnover': var.get('result', {}).get('turnover'),
                'alpha_id': var.get('result', {}).get('alpha_id')
            })
        
        # 简化最佳变种
        best_variation = result.get('best_variation', {})
        simplified_best = None
        if best_variation:
            best_result = best_variation.get('result', {})
            simplified_best = {
                'alpha': best_variation.get('alpha'),
                'sharpe': best_result.get('sharpe'),
                'turnover': best_result.get('turnover'),
                'alpha_id': best_result.get('alpha_id'),
                'recommendation': best_variation.get('recommendation')
            }
            
            # 只保留前3个改进
            if 'improvements' in best_variation:
                simplified_best['top_improvements'] = best_variation['improvements'][:3]
        
        # 创建要保存的数据
        save_data = {
            'timestamp': timestamp,
            'success': result.get('success', False),
            'message': result.get('message', ''),
            'original_alpha': result.get('original_alpha', ''),
            'original_sharpe': result.get('original_result', {}).get('sharpe'),
            'original_turnover': result.get('original_result', {}).get('turnover'),
            'original_alpha_id': result.get('original_result', {}).get('alpha_id'),
            'variations_count': len(simplified_results),
            'best_variation': simplified_best,
            'variations': simplified_results
        }
        
        # 保存到文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"优化结果已保存到: {filename}")
        return filename


def main():
    # 初始化客户端
    logger.info("初始化WorldQuant客户端...")
    client = WorldQuantClient()
    
    # 登录平台
    if not client.login():
        logger.error("登录失败")
        print("登录失败，请检查环境变量或配置文件")
        return
    
    logger.info("登录成功")
    
    # 初始化优化器
    optimizer = AlphaOptimizer(client)
    
    # 要优化的Alpha表达式
    alphas_to_optimize = [
        "rank(ts_mean(close, 5) / ts_mean(close, 22))",
        "rank(correlation(close, volume, 10))",
        "zscore(ts_rank(volume, 10))"
    ]
    
    # 循环优化每个Alpha
    for i, alpha in enumerate(alphas_to_optimize):
        print(f"\n开始优化Alpha {i+1}/{len(alphas_to_optimize)}: {alpha}")
        logger.info(f"开始优化Alpha: {alpha}")
        
        # 执行优化
        try:
            optimization_result = optimizer.optimize(alpha, max_variations=8)
            
            # 打印结果摘要
            if optimization_result.get('success', False):
                original_sharpe = optimization_result.get('original_result', {}).get('sharpe', 0)
                best_variation = optimization_result.get('best_variation', {})
                
                if best_variation and best_variation.get('alpha'):
                    best_sharpe = best_variation.get('result', {}).get('sharpe', 0)
                    improvement = ((best_sharpe - original_sharpe) / max(0.01, abs(original_sharpe))) * 100
                    
                    print(f"优化结果:")
                    print(f"原始Alpha Sharpe比率: {original_sharpe:.4f}")
                    print(f"最佳变种 Sharpe比率: {best_sharpe:.4f} (提升 {improvement:.2f}%)")
                    print(f"建议: {best_variation.get('recommendation', '')}")
                    print(f"最佳变种: {best_variation.get('alpha', '')[:100]}...")
                else:
                    print("未找到更好的变种")
                
                # 保存结果
                optimizer.save_optimization_result(optimization_result)
            else:
                print(f"优化失败: {optimization_result.get('message', '未知错误')}")
        
        except Exception as e:
            logger.error(f"优化过程出错: {str(e)}")
            print(f"优化过程出错: {str(e)}")
    
    print("\nAlpha优化完成!")


if __name__ == "__main__":
    main() 