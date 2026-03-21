#!/usr/bin/env python3
"""
Alpha回测工具 - 用于回测260321文件夹中的Alpha策略
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from itertools import product

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worldquant_alpha.wd_lib_wrapper import get_api
from worldquant_alpha.database import init_db, save_alpha, save_alpha_result, get_alpha_id_by_expression

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('alpha_backtest.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class AlphaBacktestTool:
    """Alpha回测工具"""
    
    def __init__(self, data_dir: str = "."):
        self.data_dir = data_dir
        self.api = None
        self.candidates_file = os.path.join(data_dir, "Alpha_candidates.json")
        self.expressions_file = os.path.join(data_dir, "Alpha_generated_expressions_success.json")
        
        self.candidates = self._load_json(self.candidates_file)
        self.expressions = self._load_json(self.expressions_file)
        
        logger.info(f"加载了 {len(self.candidates)} 个Alpha模板")
        logger.info(f"加载了 {len(self.expressions)} 个已生成的表达式")
    
    def _load_json(self, filepath: str) -> Any:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载文件失败 {filepath}: {e}")
            return None
    
    def init_api(self):
        if self.api is None:
            logger.info("正在连接WorldQuant API...")
            self.api = get_api()
            logger.info("API连接成功")
        return self.api
    
    def generate_expressions_from_template(self, template_key: str, max_count: int = 10) -> List[Dict]:
        if self.candidates is None or template_key not in self.candidates:
            logger.error(f"模板不存在: {template_key}")
            return []
        
        template = self.candidates[template_key]
        template_expr = template_key
        settings = template.get('seed_alpha_settings', {})
        placeholders = template.get('placeholder_candidates', {})
        
        placeholder_options = {}
        for placeholder, info in placeholders.items():
            candidates = info.get('candidates', [])
            if candidates:
                placeholder_options[placeholder] = [c['id'] for c in candidates[:5]]
        
        if not placeholder_options:
            logger.warning(f"模板没有占位符候选: {template_key}")
            return []
        
        expressions = []
        placeholder_names = list(placeholder_options.keys())
        
        for values in product(*placeholder_options.values()):
            if len(expressions) >= max_count:
                break
            
            expr = template_expr
            for placeholder, value in zip(placeholder_names, values):
                expr = expr.replace(placeholder, value)
            
            expressions.append({
                'expression': expr,
                'settings': settings.copy(),
                'template': template_key,
                'placeholders': dict(zip(placeholder_names, values))
            })
        
        logger.info(f"从模板生成了 {len(expressions)} 个表达式")
        return expressions
    
    def run_backtest(self, expression: str, settings: Dict) -> Optional[Dict]:
        try:
            api = self.init_api()
            logger.info(f"开始回测: {expression[:80]}...")
            result = api.run_backtest(expression, settings)
            
            if result:
                logger.info(f"回测完成 - Sharpe: {result.get('sharpe')}, "
                          f"Fitness: {result.get('fitness')}, "
                          f"Color: {result.get('color')}")
            return result
        except Exception as e:
            logger.error(f"回测异常: {e}")
            return None
    
    def backtest_generated_expressions(self, limit: int = None, save_to_db: bool = True) -> List[Dict]:
        if not self.expressions:
            logger.error("没有已生成的表达式")
            return []
        
        if save_to_db:
            init_db()
        
        results = []
        expressions_to_test = self.expressions[:limit] if limit else self.expressions
        logger.info(f"开始回测 {len(expressions_to_test)} 个表达式（共 {len(self.expressions)} 个可用）")
        
        default_settings = {
            "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
            "delay": 1, "decay": 0, "neutralization": "SUBINDUSTRY",
            "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
            "nanHandling": "ON", "language": "FASTEXPR", "visualization": False
        }
        
        for i, expr in enumerate(expressions_to_test, 1):
            logger.info(f"\n[{i}/{len(expressions_to_test)}] 回测进度")
            
            # 保存或获取Alpha ID
            alpha_id = None
            if save_to_db:
                alpha_id = save_alpha(expr, "generated", default_settings)
                # 如果Alpha已存在，查询其ID
                if alpha_id is None:
                    from worldquant_alpha.database import get_alpha_id_by_expression
                    alpha_id = get_alpha_id_by_expression(expr)
                    if alpha_id:
                        logger.info(f"Alpha已存在，ID: {alpha_id}")
            
            result = self.run_backtest(expr, default_settings)
            
            if result:
                results.append({'expression': expr, 'result': result, 'alpha_id': alpha_id})
                if save_to_db and alpha_id:
                    logger.info(f"[{i}/{len(expressions_to_test)}] >>> 回测完成，立即更新数据库...")
                    logger.info(f"    Alpha ID: {alpha_id}")
                    logger.info(f"    Sharpe: {result.get('sharpe')}")
                    logger.info(f"    Fitness: {result.get('fitness')}")
                    logger.info(f"    Turnover: {result.get('turnover')}")
                    logger.info(f"    Color: {result.get('color')}")
                    save_alpha_result(alpha_id=alpha_id, platform_id=result.get('platform_id'),
                                    sharpe=result.get('sharpe'), fitness=result.get('fitness'),
                                    turnover=result.get('turnover'), color=result.get('color'),
                                    self_corr=result.get('self_corr'), raw_result=result)
                    logger.info(f"[{i}/{len(expressions_to_test)}] ✓ 数据库已更新 - Alpha ID: {alpha_id}")
                else:
                    logger.warning(f"[{i}/{len(expressions_to_test)}] ⚠ 无法更新数据库 - alpha_id: {alpha_id}, save_to_db: {save_to_db}")
            
            # 每个因子回测完就立即更新，不等待整体完成
            time.sleep(2)
        
        logger.info(f"\n回测完成，共 {len(results)} 个结果")
        return results
    
    def backtest_from_template(self, template_key: str, count: int = 10, save_to_db: bool = True) -> List[Dict]:
        expressions = self.generate_expressions_from_template(template_key, count)
        if not expressions:
            return []
        
        if save_to_db:
            init_db()
        
        results = []
        for i, expr_info in enumerate(expressions, 1):
            expr = expr_info['expression']
            settings = expr_info['settings']
            logger.info(f"\n[{i}/{len(expressions)}] 回测: {expr[:100]}...")
            
            alpha_id = save_alpha(expr, template_key, settings) if save_to_db else None
            result = self.run_backtest(expr, settings)
            
            if result:
                results.append({'expression': expr, 'settings': settings, 'result': result,
                              'alpha_id': alpha_id, 'placeholders': expr_info.get('placeholders', {})})
                if save_to_db and alpha_id:
                    save_alpha_result(alpha_id=alpha_id, platform_id=result.get('platform_id'),
                                    sharpe=result.get('sharpe'), fitness=result.get('fitness'),
                                    turnover=result.get('turnover'), color=result.get('color'),
                                    self_corr=result.get('self_corr'), raw_result=result)
            time.sleep(2)
        
        logger.info(f"\n回测完成，共 {len(results)} 个结果")
        return results
    
    def analyze_results(self, results: List[Dict], sharpe_threshold: float = 1.5) -> Dict:
        if not results:
            return {'total': 0, 'valid': 0, 'good': 0}
        
        total = len(results)
        valid = sum(1 for r in results if r.get('result') is not None)
        good_alphas = []
        
        for item in results:
            result = item.get('result', {})
            if result:
                try:
                    sharpe = float(result.get('sharpe', 0) or 0)
                    fitness = float(result.get('fitness', 0) or 0)
                except (ValueError, TypeError):
                    sharpe = 0
                    fitness = 0
                
                if sharpe >= sharpe_threshold:
                    good_alphas.append({
                        'expression': item.get('expression', ''),
                        'sharpe': sharpe,
                        'fitness': fitness,
                        'turnover': result.get('turnover'),
                        'color': result.get('color')
                    })
        
        good_alphas.sort(key=lambda x: x.get('sharpe', 0), reverse=True)
        
        return {'total': total, 'valid': valid, 'good': len(good_alphas),
                'good_alphas': good_alphas[:10],
                'success_rate': valid / total if total > 0 else 0}
    
    def print_analysis(self, analysis: Dict):
        print("\n" + "="*60)
        print("回测结果分析")
        print("="*60)
        print(f"总回测数: {analysis['total']}")
        print(f"有效回测: {analysis['valid']}")
        print(f"优质Alpha (Sharpe>=1.5): {analysis['good']}")
        print(f"成功率: {analysis['success_rate']:.2%}")
        
        if analysis['good_alphas']:
            print("\n" + "-"*60)
            print("Top 10 优质Alpha:")
            print("-"*60)
            for i, alpha in enumerate(analysis['good_alphas'], 1):
                print(f"\n{i}. Sharpe: {alpha['sharpe']:.4f}, "
                      f"Fitness: {alpha['fitness']:.4f}, Color: {alpha['color']}")
                print(f"   表达式: {alpha['expression'][:100]}...")
    
    def export_results(self, results: List[Dict], filename: str = None):
        if filename is None:
            filename = f"backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.data_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"结果已导出到: {filepath}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Alpha回测工具')
    parser.add_argument('--data-dir', default='.', help='数据文件目录')
    parser.add_argument('--mode', choices=['generated', 'template'], default='generated',
                       help='回测模式: generated=已生成的表达式, template=从模板生成')
    parser.add_argument('--template', type=str, help='模板键名（template模式必填）')
    parser.add_argument('--limit', type=int, default=None, help='回测数量限制（不指定则回测所有表达式）')
    parser.add_argument('--no-db', action='store_true', help='不保存到数据库')
    parser.add_argument('--list-templates', action='store_true', help='列出所有模板')
    
    args = parser.parse_args()
    tool = AlphaBacktestTool(args.data_dir)
    
    if args.list_templates:
        print("\n可用的Alpha模板:")
        print("-"*60)
        for i, key in enumerate(tool.candidates.keys(), 1):
            template = tool.candidates[key]
            explanation = template.get('template_explanation', 'N/A')
            print(f"\n{i}. {key[:80]}...")
            print(f"   说明: {explanation[:100]}...")
        return
    
    save_to_db = not args.no_db
    
    if args.mode == 'generated':
        results = tool.backtest_generated_expressions(limit=args.limit, save_to_db=save_to_db)
    elif args.mode == 'template':
        if not args.template:
            print("错误: template模式需要指定--template参数")
            print("使用 --list-templates 查看可用模板")
            return
        results = tool.backtest_from_template(args.template, count=args.limit, save_to_db=save_to_db)
    else:
        return
    
    analysis = tool.analyze_results(results)
    tool.print_analysis(analysis)
    tool.export_results(results)
    print("\n回测完成！")


if __name__ == "__main__":
    main()