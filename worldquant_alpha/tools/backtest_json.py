"""
回测 JSON 文件中的 Alpha 并保存结果

用法:
    python -m worldquant_alpha.tools.backtest_json <json_file> [--output OUTPUT_FILE]

示例:
    python -m worldquant_alpha.tools.backtest_json simulatable_alphas.json
    python -m worldquant_alpha.tools.backtest_json my_alphas.json -o results.json
"""

import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

from worldquant_alpha.wd_lib.backtest.executor import Backtester
from worldquant_alpha.wd_lib import WorldQuantClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backtest_json_file(json_file: str, output_file: str = None, max_parallel: int = 4):
    """
    回测 JSON 文件中的所有 Alpha

    参数:
        json_file: JSON 文件路径
        output_file: 输出结果文件路径 (默认: {原文件名}_results_{timestamp}.json)
        max_parallel: 最大并行回测数
    """
    json_path = Path(json_file)
    if not json_path.exists():
        raise FileNotFoundError(f"文件不存在: {json_file}")

    with open(json_path, 'r', encoding='utf-8') as f:
        alphas = json.load(f)

    if not alphas:
        logger.warning("JSON 文件中没有 Alpha")
        return

    logger.info(f"加载了 {len(alphas)} 个 Alpha from {json_file}")

    client = WorldQuantClient()
    client.login()

    executor = Backtester(session=client.session)

    results = []
    for i, alpha in enumerate(alphas):
        expr = alpha.get('regular', '')
        settings = alpha.get('settings', {})
        alpha_type = alpha.get('type', 'REGULAR')

        logger.info(f"[{i+1}/{len(alphas)}] 回测: {expr[:60]}...")

        result = executor.run_backtest(alpha_expression=expr, settings=settings)

        if result:
            result_entry = {
                'index': i + 1,
                'alpha_type': alpha_type,
                'settings': settings,
                'expression': expr,
                'alpha_id': result.get('alpha_id'),
                'status': result.get('status'),
                'sharpe': result.get('sharpe'),
                'fitness': result.get('fitness'),
                'turnover': result.get('turnover'),
                'pnl': result.get('pnl'),
                'returns': result.get('returns'),
                'drawdown': result.get('drawdown'),
                'color': result.get('color'),
                'grade': result.get('grade'),
                'backtest_url': f"https://worldquant.com/workspace/alphas/{result.get('alpha_id')}",
                'success': True
            }
            logger.info(f"  -> Alpha ID: {result.get('alpha_id')}, Sharpe: {result.get('sharpe')}, Fitness: {result.get('fitness')}")
        else:
            result_entry = {
                'index': i + 1,
                'alpha_type': alpha_type,
                'settings': settings,
                'expression': expr,
                'success': False,
                'error': '回测失败'
            }
            logger.warning(f"  -> 回测失败")

        results.append(result_entry)

    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = str(json_path.parent / f"{json_path.stem}_results_{timestamp}.json")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {
                'total': len(alphas),
                'success': sum(1 for r in results if r['success']),
                'failed': sum(1 for r in results if not r['success']),
                'input_file': str(json_file),
                'timestamp': datetime.now().isoformat()
            },
            'results': results
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'='*60}")
    logger.info(f"回测完成!")
    logger.info(f"成功: {sum(1 for r in results if r['success'])}/{len(alphas)}")
    logger.info(f"结果保存到: {output_file}")
    logger.info(f"{'='*60}")

    successful = [r for r in results if r['success'] and r.get('sharpe')]
    if successful:
        logger.info("\nSharpe 排名 (Top 5):")
        for r in sorted(successful, key=lambda x: abs(x.get('sharpe', 0)), reverse=True)[:5]:
            logger.info(f"  [{r['index']}] Sharpe: {r['sharpe']:.3f}, Fitness: {r['fitness']:.3f}, Alpha: {r['alpha_id']}")

    return results


def main():
    parser = argparse.ArgumentParser(description='回测 JSON 文件中的 Alpha')
    parser.add_argument('json_file', help='JSON 文件路径')
    parser.add_argument('-o', '--output', help='输出结果文件路径')
    parser.add_argument('-p', '--parallel', type=int, default=4, help='最大并行数 (默认: 4)')

    args = parser.parse_args()

    backtest_json_file(
        json_file=args.json_file,
        output_file=args.output,
        max_parallel=args.parallel
    )


if __name__ == '__main__':
    main()
