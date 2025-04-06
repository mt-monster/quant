#!/usr/bin/env python3
"""
Alpha评估报告生成器
为Alpha因子生成详细的性能评估报告
"""

import os
import json
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.gridspec import GridSpec
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any, Union, Optional

from wd_lib import WorldQuantClient
from wd_lib.utils.exceptions import ValidationError

# 中文字体支持
mpl.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'Microsoft YaHei', 'DejaVu Sans']
mpl.rcParams['axes.unicode_minus'] = False

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 输出目录
REPORTS_DIR = "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)


class AlphaReportGenerator:
    """Alpha评估报告生成器"""
    
    def __init__(self, client: WorldQuantClient):
        """
        初始化报告生成器
        
        参数:
        - client: WorldQuantClient实例
        """
        self.client = client
        self.default_settings = {
            "instrumentType": "EQUITY",
            "region": "USA", 
            "universe": "TOP3000", 
            "delay": 1,
            "decay": 0,
            "neutralization": "INDUSTRY",
            "truncation": 0.08
        }
        logger.info("报告生成器初始化完成")
    
    def generate_alpha_report(self, alpha_id: str) -> Dict[str, Any]:
        """
        为单个Alpha生成评估报告
        
        参数:
        - alpha_id: Alpha ID
        
        返回:
        - 报告数据
        """
        logger.info(f"为Alpha {alpha_id} 生成评估报告...")
        
        # 获取Alpha详情
        alpha_details = self.client.get_alpha_details(alpha_id)
        
        if not alpha_details:
            logger.error(f"无法获取Alpha {alpha_id} 的详情")
            return {
                'success': False,
                'message': f"无法获取Alpha {alpha_id} 的详情",
                'alpha_id': alpha_id
            }
        
        # 提取Alpha表达式和设置
        alpha_expression = alpha_details.get('regular', {}).get('expression', '')
        settings = alpha_details.get('settings', self.default_settings)
        
        # 获取Alpha的检查状态
        status, color = self.client.check_alpha_status(alpha_id)
        
        # 分析Alpha细节
        analysis = self.client.analyze_backtest_result({
            'alpha_id': alpha_id,
            'expression': alpha_expression,
            'sharpe': alpha_details.get('is', {}).get('sharpe'),
            'turnover': alpha_details.get('is', {}).get('turnover'),
            'fitness': alpha_details.get('is', {}).get('fitness'),
            'drawdown': alpha_details.get('is', {}).get('drawdown'),
            'status': alpha_details.get('status'),
            'color': color
        })
        
        # 收集性能指标
        performance = alpha_details.get('is', {})
        
        # 构建报告数据
        report_data = {
            'success': True,
            'alpha_id': alpha_id,
            'alpha_expression': alpha_expression,
            'settings': settings,
            'status': alpha_details.get('status'),
            'color': color,
            'performance': performance,
            'analysis': analysis,
            'date_created': alpha_details.get('dateCreated'),
            'date_modified': alpha_details.get('dateModified'),
            'author': alpha_details.get('author')
        }
        
        return report_data
    
    def generate_comparison_report(self, alpha_ids: List[str]) -> Dict[str, Any]:
        """
        为多个Alpha生成对比报告
        
        参数:
        - alpha_ids: Alpha ID列表
        
        返回:
        - 报告数据
        """
        logger.info(f"为{len(alpha_ids)}个Alpha生成对比报告...")
        
        if not alpha_ids:
            return {
                'success': False,
                'message': "未提供Alpha ID"
            }
        
        # 为每个Alpha生成评估报告
        reports = []
        failed_ids = []
        
        for alpha_id in alpha_ids:
            try:
                report = self.generate_alpha_report(alpha_id)
                if report.get('success', False):
                    reports.append(report)
                else:
                    failed_ids.append(alpha_id)
            except Exception as e:
                logger.error(f"处理Alpha {alpha_id} 时出错: {str(e)}")
                failed_ids.append(alpha_id)
        
        if not reports:
            return {
                'success': False,
                'message': f"所有Alpha处理均失败: {failed_ids}"
            }
        
        # 提取性能指标进行比较
        comparison_data = []
        for report in reports:
            perf = report.get('performance', {})
            analysis = report.get('analysis', {})
            
            comparison_data.append({
                'alpha_id': report.get('alpha_id'),
                'sharpe': perf.get('sharpe', 0),
                'turnover': perf.get('turnover', 0),
                'fitness': perf.get('fitness', 0),
                'drawdown': perf.get('drawdown', 0),
                'quality_score': analysis.get('quality', {}).get('score', 0),
                'quality_rating': analysis.get('quality', {}).get('rating', ''),
                'color': report.get('color'),
                'status': report.get('status'),
                'expression': report.get('alpha_expression', '')[:100]
            })
        
        # 创建对比报告
        comparison_report = {
            'success': True,
            'count': len(reports),
            'failed_count': len(failed_ids),
            'failed_ids': failed_ids,
            'comparison_data': comparison_data,
            'individual_reports': reports
        }
        
        return comparison_report
    
    def save_report(self, report_data: Dict[str, Any], report_type: str = 'single') -> str:
        """
        保存报告数据
        
        参数:
        - report_data: 报告数据
        - report_type: 报告类型，'single' 或 'comparison'
        
        返回:
        - 保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if report_type == 'single':
            alpha_id = report_data.get('alpha_id', 'unknown')
            filename = f"{REPORTS_DIR}/alpha_report_{alpha_id}_{timestamp}.json"
        else:
            filename = f"{REPORTS_DIR}/alpha_comparison_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"报告已保存到: {filename}")
        return filename
    
    def create_visualization(self, report_data: Dict[str, Any], report_type: str = 'single') -> str:
        """
        创建可视化报告
        
        参数:
        - report_data: 报告数据
        - report_type: 报告类型，'single' 或 'comparison'
        
        返回:
        - 保存的图表文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if report_type == 'single':
            return self._visualize_single_alpha(report_data, timestamp)
        else:
            return self._visualize_alpha_comparison(report_data, timestamp)
    
    def _visualize_single_alpha(self, report: Dict[str, Any], timestamp: str) -> str:
        """为单个Alpha创建可视化报告"""
        alpha_id = report.get('alpha_id', 'unknown')
        filename = f"{REPORTS_DIR}/alpha_report_{alpha_id}_{timestamp}.png"
        
        # 创建图表
        plt.figure(figsize=(12, 10))
        
        # 使用GridSpec布局
        gs = GridSpec(3, 2, figure=plt.gcf())
        
        # 1. 基本信息
        ax1 = plt.subplot(gs[0, :])
        ax1.axis('off')
        ax1.set_title(f"Alpha {alpha_id} 评估报告", fontsize=16)
        
        info_text = f"""
        Alpha表达式: {report.get('alpha_expression', '')[:100]}...
        状态: {report.get('status', '')}
        颜色: {report.get('color', '')}
        创建日期: {report.get('date_created', '')}
        
        质量评级: {report.get('analysis', {}).get('quality', {}).get('rating', '')}
        质量得分: {report.get('analysis', {}).get('quality', {}).get('score', '')}
        评论: {report.get('analysis', {}).get('quality', {}).get('comments', '')}
        """
        ax1.text(0.05, 0.5, info_text, fontsize=12, va='center')
        
        # 2. 性能指标
        ax2 = plt.subplot(gs[1, 0])
        perf = report.get('performance', {})
        metrics = ['sharpe', 'turnover', 'fitness', 'drawdown']
        values = [perf.get(m, 0) for m in metrics]
        
        # 给sharpe和fitness标准值
        thresholds = [1.25, 0.3, 0.6, 0.1]  # sharpe, turnover, fitness, drawdown
        colors = []
        
        for i, (val, thresh) in enumerate(zip(values, thresholds)):
            if i == 0:  # Sharpe
                colors.append('green' if val >= thresh else 'red')
            elif i == 1:  # Turnover
                colors.append('green' if val <= thresh else 'orange')
            elif i == 2:  # Fitness
                colors.append('green' if val >= thresh else 'orange')
            else:  # Drawdown
                colors.append('green' if val <= thresh else 'red')
        
        ax2.bar(metrics, values, color=colors)
        ax2.set_title('性能指标')
        ax2.set_ylim(0, max(max(values) * 1.2, 1.5))
        
        # 添加阈值线
        for i, (thresh, metric) in enumerate(zip(thresholds, metrics)):
            if i == 0:  # Sharpe - 最小值线
                ax2.axhline(y=thresh, xmin=i/len(metrics), xmax=(i+1)/len(metrics), 
                           color='green', linestyle='--', alpha=0.7)
            elif i == 1:  # Turnover - 最大值线
                ax2.axhline(y=thresh, xmin=i/len(metrics), xmax=(i+1)/len(metrics), 
                           color='red', linestyle='--', alpha=0.7)
            elif i == 2:  # Fitness - 最小值线
                ax2.axhline(y=thresh, xmin=i/len(metrics), xmax=(i+1)/len(metrics), 
                           color='green', linestyle='--', alpha=0.7)
            else:  # Drawdown - 最大值线
                ax2.axhline(y=thresh, xmin=i/len(metrics), xmax=(i+1)/len(metrics), 
                           color='red', linestyle='--', alpha=0.7)
        
        # 3. 建议
        ax3 = plt.subplot(gs[1, 1])
        ax3.axis('off')
        ax3.set_title('改进建议')
        
        suggestions = report.get('analysis', {}).get('suggestions', [])
        suggestion_text = "\n".join([f"- {s}" for s in suggestions]) if suggestions else "无建议"
        ax3.text(0.05, 0.5, suggestion_text, fontsize=12, va='center')
        
        # 4. 设置信息
        ax4 = plt.subplot(gs[2, :])
        ax4.axis('off')
        ax4.set_title('回测设置')
        
        settings = report.get('settings', {})
        settings_text = "\n".join([f"{k}: {v}" for k, v in settings.items()])
        ax4.text(0.05, 0.5, settings_text, fontsize=12, va='center')
        
        # 保存图表
        plt.tight_layout()
        plt.savefig(filename, dpi=100)
        plt.close()
        
        logger.info(f"Alpha {alpha_id} 可视化报告已保存到: {filename}")
        return filename
    
    def _visualize_alpha_comparison(self, report: Dict[str, Any], timestamp: str) -> str:
        """为多个Alpha创建对比可视化报告"""
        filename = f"{REPORTS_DIR}/alpha_comparison_{timestamp}.png"
        
        # 提取对比数据
        comparison_data = report.get('comparison_data', [])
        if not comparison_data:
            logger.error("没有对比数据可视化")
            return ""
        
        # 创建DataFrame
        df = pd.DataFrame(comparison_data)
        
        # 创建图表
        plt.figure(figsize=(14, 10))
        
        # 1. Sharpe比率对比
        plt.subplot(2, 2, 1)
        sharpe_bars = plt.bar(df['alpha_id'], df['sharpe'])
        plt.axhline(y=1.25, color='r', linestyle='--', alpha=0.7)
        plt.title('Sharpe比率')
        plt.xticks(rotation=45)
        # 为每个柱添加颜色
        for i, bar in enumerate(sharpe_bars):
            if df['sharpe'].iloc[i] >= 1.25:
                bar.set_color('green')
            else:
                bar.set_color('red')
        
        # 2. 换手率对比
        plt.subplot(2, 2, 2)
        turnover_bars = plt.bar(df['alpha_id'], df['turnover'])
        plt.axhline(y=0.3, color='r', linestyle='--', alpha=0.7)
        plt.title('换手率')
        plt.xticks(rotation=45)
        # 为每个柱添加颜色
        for i, bar in enumerate(turnover_bars):
            if df['turnover'].iloc[i] <= 0.3:
                bar.set_color('green')
            else:
                bar.set_color('red')
        
        # 3. 质量评级对比
        plt.subplot(2, 2, 3)
        quality_bars = plt.bar(df['alpha_id'], df['quality_score'])
        plt.title('质量得分')
        plt.xticks(rotation=45)
        
        # 为每个柱添加颜色
        for i, bar in enumerate(quality_bars):
            score = df['quality_score'].iloc[i]
            if score >= 6:
                bar.set_color('green')
            elif score >= 4:
                bar.set_color('blue')
            elif score >= 2:
                bar.set_color('orange')
            else:
                bar.set_color('red')
        
        # 4. 表格汇总
        plt.subplot(2, 2, 4)
        plt.axis('off')
        
        # 创建表格数据
        table_data = [
            ['Alpha ID', 'Sharpe', 'Turnover', '质量评级', '颜色']
        ]
        
        for _, row in df.iterrows():
            table_data.append([
                row['alpha_id'],
                f"{row['sharpe']:.4f}",
                f"{row['turnover']:.4f}",
                row['quality_rating'],
                row['color'] or 'N/A'
            ])
        
        # 创建表格
        table = plt.table(
            cellText=table_data,
            colWidths=[0.2, 0.15, 0.15, 0.15, 0.15],
            loc='center',
            cellLoc='center'
        )
        
        # 设置表格样式
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
        
        # 为表头设置样式
        for i in range(len(table_data[0])):
            table[(0, i)].set_facecolor('#4472C4')
            table[(0, i)].set_text_props(color='white')
        
        plt.title('Alpha对比汇总')
        
        # 保存图表
        plt.tight_layout()
        plt.savefig(filename, dpi=100)
        plt.close()
        
        logger.info(f"Alpha对比可视化报告已保存到: {filename}")
        return filename
    
    def run_and_generate_report(self, alpha_expressions: List[str], settings: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        运行回测并生成报告
        
        参数:
        - alpha_expressions: Alpha表达式列表
        - settings: 回测设置，如果为None则使用默认设置
        
        返回:
        - 报告数据
        """
        logger.info(f"运行{len(alpha_expressions)}个Alpha的回测并生成报告...")
        
        if not settings:
            settings = self.default_settings
        
        # 执行回测
        try:
            results = self.client.run_batch_backtest(alpha_expressions, settings)
        except ValidationError as e:
            logger.error(f"Alpha验证错误: {str(e)}")
            return {
                'success': False,
                'message': f"Alpha验证错误: {str(e)}"
            }
        except Exception as e:
            logger.error(f"回测执行错误: {str(e)}")
            return {
                'success': False,
                'message': f"回测执行错误: {str(e)}"
            }
        
        if not results:
            logger.error("回测未返回结果")
            return {
                'success': False,
                'message': "回测未返回结果"
            }
        
        # 分析结果
        logger.info("分析回测结果...")
        analyses = []
        
        for result in results:
            alpha_id = result.get('alpha_id')
            if alpha_id:
                analysis = self.client.analyze_backtest_result(result)
                analyses.append({
                    'alpha_id': alpha_id,
                    'alpha_expression': result.get('expression', ''),
                    'performance': {
                        'sharpe': result.get('sharpe', 0),
                        'turnover': result.get('turnover', 0),
                        'fitness': result.get('fitness', 0),
                        'drawdown': result.get('drawdown', 0)
                    },
                    'status': result.get('status'),
                    'color': result.get('color'),
                    'analysis': analysis
                })
        
        # 计算整体性能指标
        metrics = self.client.calculate_performance_metrics(results)
        
        # 构建报告
        report_data = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'count': len(results),
            'settings': settings,
            'metrics': metrics,
            'analyses': analyses,
            'results': results
        }
        
        return report_data
    
    def execute_full_workflow(self, alpha_expressions: List[str], settings: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行完整的工作流程：回测、分析、生成报告和可视化
        
        参数:
        - alpha_expressions: Alpha表达式列表
        - settings: 回测设置
        
        返回:
        - 工作流结果
        """
        # 运行回测并生成报告
        report_data = self.run_and_generate_report(alpha_expressions, settings)
        
        if not report_data.get('success', False):
            return report_data
        
        # 保存报告
        report_file = self.save_report(report_data, 'comparison')
        
        # 创建可视化
        chart_file = self.create_visualization(report_data, 'comparison')
        
        # 返回结果
        workflow_result = {
            'success': True,
            'report_file': report_file,
            'chart_file': chart_file,
            'alpha_count': report_data.get('count', 0),
            'report_data': report_data
        }
        
        return workflow_result


def main():
    # 初始化客户端
    print("初始化WorldQuant客户端...")
    client = WorldQuantClient()
    
    # 登录平台
    if not client.login():
        print("登录失败，请检查环境变量中的用户名和密码")
        return
    
    print("登录成功!")
    
    # 初始化报告生成器
    report_generator = AlphaReportGenerator(client)
    
    # 用户选择功能
    print("\n请选择报告类型:")
    print("1. 单个Alpha报告（通过Alpha ID）")
    print("2. Alpha对比报告（多个Alpha ID）")
    print("3. 批量回测并生成报告")
    
    choice = input("请输入选项编号（1-3）: ")
    
    if choice == '1':
        alpha_id = input("请输入Alpha ID: ")
        
        # 生成单个Alpha报告
        report = report_generator.generate_alpha_report(alpha_id)
        
        if report.get('success', False):
            # 保存报告
            report_generator.save_report(report, 'single')
            # 创建可视化
            report_generator.create_visualization(report, 'single')
            print("报告生成完成!")
        else:
            print(f"报告生成失败: {report.get('message', '未知错误')}")
            
    elif choice == '2':
        alpha_ids_input = input("请输入Alpha ID列表，以逗号分隔: ")
        alpha_ids = [aid.strip() for aid in alpha_ids_input.split(',')]
        
        # 生成对比报告
        report = report_generator.generate_comparison_report(alpha_ids)
        
        if report.get('success', False):
            # 保存报告
            report_generator.save_report(report, 'comparison')
            # 创建可视化
            report_generator.create_visualization(report, 'comparison')
            print("对比报告生成完成!")
        else:
            print(f"报告生成失败: {report.get('message', '未知错误')}")
            
    elif choice == '3':
        # 输入Alpha表达式
        print("请输入Alpha表达式，每行一个，空行结束输入:")
        alpha_expressions = []
        while True:
            line = input()
            if not line:
                break
            alpha_expressions.append(line)
        
        if not alpha_expressions:
            print("未输入任何Alpha表达式，操作取消")
            return
        
        # 选择回测设置
        print("\n请选择回测区域:")
        print("1. 美国 (USA)")
        print("2. 中国 (CHN)")
        print("3. 欧洲 (EUR)")
        region_choice = input("请输入选项编号（默认1）: ") or '1'
        
        regions = ['USA', 'CHN', 'EUR']
        region = regions[int(region_choice) - 1] if region_choice in ['1', '2', '3'] else 'USA'
        
        print("\n请选择中性化方式:")
        print("1. 行业 (INDUSTRY)")
        print("2. 市场 (MARKET)")
        print("3. 子行业 (SUBINDUSTRY)")
        neut_choice = input("请输入选项编号（默认1）: ") or '1'
        
        neuts = ['INDUSTRY', 'MARKET', 'SUBINDUSTRY']
        neutralization = neuts[int(neut_choice) - 1] if neut_choice in ['1', '2', '3'] else 'INDUSTRY'
        
        # 设置回测参数
        settings = {
            "instrumentType": "EQUITY",
            "region": region,
            "universe": "TOP3000",
            "delay": 1,
            "decay": 0.2,
            "neutralization": neutralization,
            "truncation": 0.08,
            "pasteurization": "ON",
            "nanHandling": "ON"
        }
        
        # 执行完整工作流
        print("\n开始执行回测和报告生成流程...")
        result = report_generator.execute_full_workflow(alpha_expressions, settings)
        
        if result.get('success', False):
            print(f"工作流完成!")
            print(f"报告文件: {result.get('report_file')}")
            print(f"图表文件: {result.get('chart_file')}")
        else:
            print(f"工作流失败: {result.get('message', '未知错误')}")
    
    else:
        print("无效的选项")


if __name__ == "__main__":
    main() 