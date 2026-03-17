"""
WorldQuant Brain API回测分析模块
提供对回测结果的分析功能
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union

# 配置日志
logger = logging.getLogger(__name__)

def analyze_backtest_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析单个回测结果
    
    参数:
    - result: 回测结果字典
    
    返回:
    - 分析报告字典
    """
    if not result:
        logger.warning("回测结果为空，无法分析")
        return {}
    
    try:
        # 提取关键指标
        alpha_id = result.get('alpha_id')
        expression = result.get('expression', '')
        
        # 确保 sharpe, fitness, turnover 是数字类型
        try:
            sharpe = float(result.get('sharpe', 0)) if result.get('sharpe') is not None else 0
            turnover = float(result.get('turnover', 0)) if result.get('turnover') is not None else 0
            fitness = float(result.get('fitness', 0)) if result.get('fitness') is not None else 0
            drawdown = float(result.get('drawdown', 0)) if result.get('drawdown') is not None else 0
        except (ValueError, TypeError):
            sharpe = 0
            turnover = 0
            fitness = 0
            drawdown = 0
        
        status = result.get('status', 'UNKNOWN')
        color = result.get('color')
        
        # 评估Alpha质量
        quality_score = 0
        quality_comment = ""
        
        if sharpe >= 2.0:
            quality_score += 3
            quality_comment += "Sharpe比率出色 (>= 2.0); "
        elif sharpe >= 1.5:
            quality_score += 2
            quality_comment += "Sharpe比率良好 (>= 1.5); "
        elif sharpe >= 1.25:
            quality_score += 1
            quality_comment += "Sharpe比率合格 (>= 1.25); "
        else:
            quality_comment += "Sharpe比率不足 (< 1.25); "
        
        if turnover <= 0.2:
            quality_score += 2
            quality_comment += "换手率极低，非常理想; "
        elif turnover <= 0.5:
            quality_score += 1
            quality_comment += "换手率适中; "
        else:
            quality_comment += "换手率偏高; "
        
        if drawdown is not None and drawdown <= 0.05:
            quality_score += 2
            quality_comment += "最大回撤较小，风险控制良好; "
        elif drawdown is not None and drawdown <= 0.1:
            quality_score += 1
            quality_comment += "最大回撤可接受; "
        elif drawdown is not None:
            quality_comment += f"最大回撤为 {drawdown:.2%}; "
        
        if color == "GREEN":
            quality_score += 2
            quality_comment += "已标记为绿色，自相关性低; "
        elif color == "BLUE":
            quality_comment += "已标记为蓝色，需进一步评估; "
        elif color == "YELLOW":
            quality_score -= 1
            quality_comment += "已标记为黄色，检查存在问题; "
        
        # 确定整体评级
        if quality_score >= 6:
            rating = "优秀"
        elif quality_score >= 4:
            rating = "良好"
        elif quality_score >= 2:
            rating = "合格"
        else:
            rating = "待改进"
        
        # 生成建议
        suggestions = []
        
        if sharpe < 1.25:
            suggestions.append("尝试优化Alpha以提高Sharpe比率至少达到1.25")
            
        if turnover > 0.5:
            suggestions.append("考虑降低Alpha的换手率，可通过增加时间周期或添加平滑函数")
            
        if color == "YELLOW":
            suggestions.append("检查Alpha的检验未通过，需要修正相关问题")
            
        if status != "ACCEPTED":
            suggestions.append(f"Alpha状态为 {status}，不是已接受状态，可能需要重新提交")
        
        # 构建分析报告
        report = {
            'alpha_id': alpha_id,
            'expression': expression[:100] + ('...' if len(expression) > 100 else ''),
            'key_metrics': {
                'sharpe': sharpe,
                'turnover': turnover,
                'fitness': fitness,
                'drawdown': drawdown,
                'status': status,
                'color': color
            },
            'quality': {
                'score': quality_score,
                'rating': rating,
                'comments': quality_comment.strip()
            },
            'suggestions': suggestions
        }
        
        logger.info(f"完成Alpha {alpha_id} 的分析，评级: {rating}")
        return report
        
    except Exception as e:
        logger.error(f"分析回测结果时出错: {str(e)}")
        return {'error': str(e)}


def calculate_performance_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算多个Alpha的整体性能指标
    
    参数:
    - results: 回测结果字典列表
    
    返回:
    - 整体性能指标字典
    """
    if not results:
        logger.warning("结果列表为空，无法计算性能指标")
        return {}
    
    try:
        # 提取数据
        sharpes = [r.get('sharpe', 0) for r in results if r.get('sharpe') is not None]
        turnovers = [r.get('turnover', 0) for r in results if r.get('turnover') is not None]
        
        # 统计颜色分布
        colors = [r.get('color') for r in results if r.get('color') is not None]
        color_counts = {
            'GREEN': colors.count('GREEN'),
            'BLUE': colors.count('BLUE'),
            'YELLOW': colors.count('YELLOW'),
            'RED': colors.count('RED'),
            'None': len(results) - len(colors)
        }
        
        # 统计状态分布
        statuses = [r.get('status') for r in results]
        status_counts = {}
        for status in statuses:
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1
        
        # 计算指标
        metrics = {
            'count': len(results),
            'sharpe': {
                'mean': np.mean(sharpes) if sharpes else None,
                'median': np.median(sharpes) if sharpes else None,
                'max': max(sharpes) if sharpes else None,
                'min': min(sharpes) if sharpes else None,
                'std': np.std(sharpes) if len(sharpes) > 1 else 0
            },
            'turnover': {
                'mean': np.mean(turnovers) if turnovers else None,
                'median': np.median(turnovers) if turnovers else None,
                'max': max(turnovers) if turnovers else None,
                'min': min(turnovers) if turnovers else None
            },
            'color_distribution': color_counts,
            'status_distribution': status_counts,
            'success_rate': sum(1 for r in results if r.get('status') == 'ACCEPTED') / len(results) if results else 0
        }
        
        logger.info(f"计算了{len(results)}个Alpha的整体性能指标")
        return metrics
        
    except Exception as e:
        logger.error(f"计算性能指标时出错: {str(e)}")
        return {'error': str(e)} 