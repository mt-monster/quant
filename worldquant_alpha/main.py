import logging
import argparse
import json
import pandas as pd
import os
import time
from datetime import datetime
from dotenv import load_dotenv
import click
from database import init_db, get_session, has_successful_submission_today
from alpha_generator import AlphaTemplate, create_default_templates, batch_generate_alphas
from backtest import run_backtest, backtest_from_db, Backtester
from notification import send_email
from wd_lib_wrapper import get_api

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


@click.group()
def cli():
    pass


@cli.command()
def init():
    """初始化系统"""
    logger.info("开始初始化系统")

    # 初始化数据库
    if not init_db():
        logger.error("数据库初始化失败")
        return False

    logger.info("系统初始化完成")
    return True


def fetch_fundamental_data(template_name=None):
    """获取基本面数据字段"""
    logger.info("开始获取基本面数据字段")

    # 定义搜索范围
    searchScope = {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1
    }

    try:
        # 获取API
        api = get_api()

        instrument_type = searchScope['instrumentType']
        region = searchScope['region']
        delay = searchScope['delay']
        universe = searchScope['universe']
        dataset_id = template_name if template_name else 'fundamental6'

        # 获取数据字段
        url_template = "https://api.worldquantbrain.com/data-fields?" + \
                       f"&instrumentType={instrument_type}" + \
                       f"&region={region}&delay={str(delay)}&universe={universe}&dataset.id={dataset_id}&limit=50" + \
                       "&offset={x}"
        count = api.session.get(url_template.format(x=0)).json()['count']
        # https://api.worldquantbrain.com/data-fields?&instrumentType=EQUITY&region=USA&delay=1&universe=TOP3000&dataset.id=fundamental6&limit=50
        datafields_list = []
        for x in range(0, count, 50):
            datafields = api.session.get(url_template.format(x=x))

            if datafields.status_code != 200:
                logger.error(f"获取基本面数据字段失败: {datafields.status_code}")
                return None

            datafields_list.append(datafields.json()['results'])

        datafields_list_flat = [item for sublist in datafields_list for item in sublist]

        fundamental_fields = pd.DataFrame(datafields_list_flat)

        fundamental_df = pd.DataFrame(fundamental_fields)

        # 筛选（这里是type的MATRIX）
        fundamental6 = fundamental_df[fundamental_df['type'] == "MATRIX"]
        fundamental6.head()
        datafields_list_fundamental6 = fundamental6['id'].values
        if template_name:
            filename = f'data/{template_name}_datafields.json'
        else:
            filename = 'data/fundamental_datafields.json'

        # 保存到文件
        os.makedirs('data', exist_ok=True)
        with open(filename, "w") as f:
            json.dump(datafields_list_fundamental6.tolist(), f)
        logger.info(f"成功获取基本面数据字段，共 {len(datafields_list_fundamental6)} 个字段，已保存到 {filename}")
        return datafields_list_fundamental6
    except Exception as e:
        logger.error(f"获取基本面数据字段失败: {str(e)}")
        return None


def generate_alphas_from_template(template_index=0, datafields=None, limit=None):
    """从模板生成Alpha表达式"""
    logger.info(f"开始从模板生成Alpha表达式，模板索引: {template_index}, 限制: {limit}")

    # 如果没有提供数据字段，尝试从文件加载
    if not datafields:
        try:
            # 查找最新的数据字段文件
            data_dir = 'data'
            if os.path.exists(data_dir):
                files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
                if files:
                    latest_file = max(files)
                    with open(os.path.join(data_dir, latest_file), 'r') as f:
                        datafields = json.load(f)
                    logger.info(f"从文件 {latest_file} 加载了 {len(datafields)} 个数据字段")
                else:
                    logger.warning("未找到数据字段文件，尝试获取新数据")
                    datafields = fetch_fundamental_data()
            else:
                logger.warning("未找到数据目录，尝试获取新数据")
                datafields = fetch_fundamental_data()
        except Exception as e:
            logger.error(f"加载数据字段时出错: {e}")
            send_error_notification(f"加载数据字段失败: {str(e)}")
            return None, None

    # 如果还是没有数据字段，返回错误
    if not datafields or len(datafields) == 0:
        logger.error("未能获取到数据字段，无法生成Alpha表达式")
        return None, None

    # 创建默认模板
    templates = create_default_templates()

    # 检查模板索引是否有效
    if template_index < 0 or template_index >= len(templates):
        logger.error(f"无效的模板索引: {template_index}，有效范围: 0-{len(templates) - 1}")
        return None, None

    # 选择模板
    template = templates[template_index]
    logger.info(f"使用模板: {template.name}")

    # 生成Alpha表达式
    _, simulation_data_list = batch_generate_alphas(
        template=template,
        datafields=datafields,
        limit=limit,
        db_save=True
    )

    logger.info(f"生成了 {len(simulation_data_list)} 个模拟请求数据")
    return template.name, simulation_data_list


def run_backtests(from_db=True, simulation_data_list=None, limit=None, ir_threshold=0.1, sharpe_threshold=1.6):
    """运行回测"""
    logger.info(f"开始运行回测，从数据库: {from_db}, 限制: {limit}, Sharpe阈值: {sharpe_threshold}")

    # 创建回测器
    backtester = Backtester(max_retry=3, batch_size=3, notify=True, sharpe_threshold=sharpe_threshold)

    # 运行回测
    if from_db:
        logger.info("从数据库运行回测")
        result = backtester.backtest_from_database(limit=limit)
    elif simulation_data_list:
        logger.info(f"从提供的模拟请求数据列表运行回测，总数: {len(simulation_data_list)}")
        result = backtester.backtest_simulation_data_list(simulation_data_list, ir_threshold=ir_threshold)
    else:
        logger.error("必须指定从数据库或提供模拟请求数据列表")
        return None

    # 打印结果
    if result and result.get('success'):
        logger.info(f"回测完成，处理: {result.get('total_processed')}, 成功: {result.get('success_count')}, " +
                    f"失败: {result.get('fail_count')}, 优质Alpha: {result.get('good_alpha_count')}")
    else:
        logger.error(f"回测失败: {result}")

    return result


def analyze_results(ir_threshold=0.1, limit=100):
    """分析回测结果，获取优质Alpha"""
    logger.info(f"开始分析回测结果，IR阈值: {ir_threshold}, 限制: {limit}")

    # 获取优质Alpha
    good_alphas = get_session(ir_threshold=ir_threshold, limit=limit)

    if not good_alphas:
        logger.info(f"未找到IR大于{ir_threshold}的Alpha")
        return None

    logger.info(f"找到 {len(good_alphas)} 个IR大于{ir_threshold}的Alpha")

    # 打印前10个优质Alpha
    for i, (alpha, result) in enumerate(good_alphas[:10], 1):
        logger.info(f"优质Alpha {i}: 表达式={alpha.alpha_expression}, IR={result.ir}")

    # 将结果导出到CSV
    results_data = []
    for alpha, result in good_alphas:
        results_data.append({
            'alpha_id': alpha.id,
            'template_name': alpha.template_name,
            'alpha_expression': alpha.alpha_expression,
            'ic': result.ic,
            'ir': result.ir,
            'sharpe': result.sharpe,
            'turnover': result.turnover,
            'fitness': result.fitness,
            'platform_id': result.alpha_platform_id
        })

    # 创建DataFrame并保存到CSV
    if results_data:
        df = pd.DataFrame(results_data)
        os.makedirs('results', exist_ok=True)
        filename = f"results/good_alphas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False)
        logger.info(f"优质Alpha已保存到 {filename}")

    return good_alphas


@cli.command()
@click.option('--from_db', is_flag=True, help='从数据库获取Alpha进行回测')
@click.option('--limit', type=int, help='回测的Alpha数量限制')
@click.option('--sharpe_threshold', type=float, default=1.6, help='Sharpe比率阈值')
def backtest(from_db, limit, sharpe_threshold):
    """运行Alpha回测"""
    logger.info(f"运行回测，从数据库：{from_db}，限制数量：{limit}，Sharpe阈值：{sharpe_threshold}")

    if from_db:
        # 创建回测器并直接调用
        backtester = Backtester(max_retry=3, batch_size=8, notify=True, sharpe_threshold=sharpe_threshold)
        results = backtester.backtest_from_database(limit=limit)
    else:
        # 创建默认模板并生成Alpha
        create_default_templates()
        alphas = batch_generate_alphas(limit=limit)
        if not alphas:
            logger.warning("没有生成新的Alpha")
            return

        # 创建回测器并直接调用
        backtester = Backtester(max_retry=3, batch_size=3, notify=True, sharpe_threshold=sharpe_threshold)
        results = backtester.run_backtest(alphas)

    if results:
        # 兼容新的结果格式
        if isinstance(results, dict):
            success_count = results.get('success_count', 0)
            total_count = results.get('total_processed', 0)
            logger.info(f"回测完成，总数: {total_count}, 成功: {success_count}")
        else:
            logger.info(f"回测完成，共有 {len(results)} 个结果")
            valid_count = sum(1 for r in results if r.get('status') == 'valid')
            logger.info(f"有效Alpha数量：{valid_count}")
    else:
        logger.warning("没有回测结果")


@cli.command()
@click.option('--template', type=int, default=0, help='模板索引（0-4）')
@click.option('--limit', type=int, default=10, help='生成的Alpha数量限制')
def generate(template, limit):
    """从模板生成Alpha表达式"""
    logger.info(f"从模板生成Alpha表达式，模板索引：{template}，限制数量：{limit}")

    # 获取数据字段
    datafields = None
    try:
        # 查找最新的数据字段文件
        data_dir = 'data'
        if os.path.exists(data_dir):
            files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
            if files:
                latest_file = max(files)
                with open(os.path.join(data_dir, latest_file), 'r') as f:
                    datafields = json.load(f)
                logger.info(f"从文件 {latest_file} 加载了数据字段")
            else:
                logger.warning("未找到数据字段文件")
                return
        else:
            logger.warning("未找到数据目录")
            return
    except Exception as e:
        logger.error(f"加载数据字段时出错: {e}")
        return

    # 创建模板
    templates = create_default_templates()

    if template < 0 or template >= len(templates):
        logger.error(f"无效的模板索引：{template}，有效范围：0-{len(templates) - 1}")
        return

    selected_template = templates[template]
    logger.info(f"使用模板：{selected_template.name}")

    # 生成Alpha表达式
    template_name, simulation_data_list = batch_generate_alphas(
        template=selected_template,
        datafields=datafields,
      #  limit=limit,
        db_save=True
    )

    if simulation_data_list:
        logger.info(f"成功生成了 {len(simulation_data_list)} 个Alpha表达式")

        # 显示前5个生成的表达式
        for i, data in enumerate(simulation_data_list[:5]):
            logger.info(f"Alpha {i + 1}: {data.get('regular', 'unknown')}")
    else:
        logger.warning("未能生成Alpha表达式")


@cli.command()
def run():
    """运行Alpha生成和回测"""
    # 检查今天是否已经提交了有效的alpha
    if has_successful_submission_today():
        logger.info("今天已经成功提交了有效的alpha，不再运行")
        return

    # 创建默认模板
    create_default_templates()

    # 批量生成Alpha
    alphas = batch_generate_alphas()
    if not alphas:
        logger.warning("没有生成新的Alpha")
        return

    # 运行回测
    results = run_backtest(alphas)

    # 发送邮件通知
    if results:
        send_email(results)


@cli.command()
@click.option('--start_template', type=int, default=5, help='起始模板索引（5-10）')
@click.option('--end_template', type=int, default=10, help='结束模板索引（5-10）')
@click.option('--limit_per_template', type=int, default=5, help='每个模板生成的Alpha数量限制')
def generate_batch(start_template, end_template, limit_per_template):
    """批量从多个模板生成Alpha表达式"""
    logger.info(f"批量生成Alpha表达式，模板范围：{start_template}-{end_template}，每个模板限制数量：{limit_per_template}")

    # 获取数据字段
    datafields = None
    try:
        # 查找最新的数据字段文件
        data_dir = 'data'
        if os.path.exists(data_dir):
            files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
            if files:
                latest_file = max(files)
                with open(os.path.join(data_dir, latest_file), 'r') as f:
                    datafields = json.load(f)
                logger.info(f"从文件 {latest_file} 加载了数据字段")
            else:
                logger.warning("未找到数据字段文件")
                return
        else:
            logger.warning("未找到数据目录")
            return
    except Exception as e:
        logger.error(f"加载数据字段时出错: {e}")
        return

    # 创建所有模板
    templates = create_default_templates()

    # 验证模板范围
    if start_template < 0 or start_template >= len(templates) or end_template < 0 or end_template >= len(templates):
        logger.error(f"无效的模板范围：{start_template}-{end_template}，有效范围：0-{len(templates) - 1}")
        return

    if start_template > end_template:
        start_template, end_template = end_template, start_template

    total_alphas = 0
    total_saved = 0

    # 循环处理每个模板
    for template_idx in range(start_template, end_template + 1):
        selected_template = templates[template_idx]
        logger.info(f"使用模板（{template_idx}）：{selected_template.name}")

        # 生成Alpha表达式
        template_name, simulation_data_list = batch_generate_alphas(
            template=selected_template,
            datafields=datafields,
            limit=limit_per_template,
            db_save=True
        )

        # 统计生成和保存的数量
        total_alphas += len(simulation_data_list)

        # 显示生成的表达式（最多5个）
        for i, data in enumerate(simulation_data_list[:5]):
            logger.info(f"Alpha {i + 1}: {data.get('regular', 'unknown')}")

    logger.info(f"批量生成完成，共生成 {total_alphas} 个Alpha表达式")

    # 可以选择立即进行回测
    if total_alphas > 0 and click.confirm('是否要立即对新生成的Alpha进行回测？'):
        logger.info("开始对新生成的Alpha进行回测")
        backtest_from_db(limit=total_alphas)


@cli.command()
@click.option('--dataset', type=str, default='fundamental6', help='数据集名称')
def fetch(dataset):
    """获取数据字段"""
    logger.info(f"获取 {dataset} 数据字段")
    datafields = fetch_fundamental_data(dataset)
    if datafields is not None:
        logger.info(f"成功获取 {len(datafields)} 个数据字段")
    else:
        logger.error("获取数据字段失败")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="WorldQuant Alpha策略生成和回测工具")
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 初始化命令
    init_parser = subparsers.add_parser('init', help='初始化系统')

    # 获取数据命令
    fetch_parser = subparsers.add_parser('fetch', help='获取基本面数据字段')
    fetch_parser.add_argument('--dataset', type=str, default='fundamental6', help='数据集名称')

    # 生成Alpha命令
    generate_parser = subparsers.add_parser('generate', help='生成Alpha表达式')
    generate_parser.add_argument('--template', type=int, default=0, help='模板索引（0-3）')
    generate_parser.add_argument('--limit', type=int, default=None, help='生成的Alpha数量限制')

    # 回测命令
    backtest_parser = subparsers.add_parser('backtest', help='运行回测')
    backtest_parser.add_argument('--from_db', action='store_true', help='从数据库获取Alpha')
    backtest_parser.add_argument('--limit', type=int, default=None, help='回测的Alpha数量限制')
    backtest_parser.add_argument('--ir_threshold', type=float, default=0.1, help='IR阈值')
    backtest_parser.add_argument('--sharpe_threshold', type=float, default=0, help='Sharpe比率阈值')

    # 分析命令
    analyze_parser = subparsers.add_parser('analyze', help='分析回测结果')
    analyze_parser.add_argument('--ir_threshold', type=float, default=0.1, help='IR阈值')
    analyze_parser.add_argument('--limit', type=int, default=100, help='分析的Alpha数量限制')

    # 全流程命令
    pipeline_parser = subparsers.add_parser('pipeline', help='运行完整流程')
    pipeline_parser.add_argument('--template', type=int, default=0, help='模板索引（0-3）')
    pipeline_parser.add_argument('--limit', type=int, default=None, help='生成的Alpha数量限制')
    pipeline_parser.add_argument('--ir_threshold', type=float, default=0.1, help='IR阈值')
    pipeline_parser.add_argument('--sharpe_threshold', type=float, default=0, help='Sharpe比率阈值')

    # 批量生成命令
    generate_batch_parser = subparsers.add_parser('generate_batch', help='批量从多个模板生成Alpha表达式')
    generate_batch_parser.add_argument('--start_template', type=int, default=5, help='起始模板索引（5-10）')
    generate_batch_parser.add_argument('--end_template', type=int, default=10, help='结束模板索引（5-10）')
    generate_batch_parser.add_argument('--limit_per_template', type=int, default=5, help='每个模板生成的Alpha数量限制')

    args = parser.parse_args()

    # 处理命令
    if args.command == 'init':
        init()

    elif args.command == 'fetch':
        datafields = fetch_fundamental_data(args.dataset)
        if datafields is not None:
            logger.info(f"获取到 {len(datafields)} 个数据字段")

    elif args.command == 'generate':
        template_name, simulation_data_list = generate_alphas_from_template(
            template_index=args.template,
            limit=args.limit
        )
        if simulation_data_list:
            logger.info(f"使用模板 '{template_name}' 生成了 {len(simulation_data_list)} 个模拟请求数据")

    elif args.command == 'backtest':
        if args.from_db:
            backtest(from_db=True, limit=args.limit)
        else:
            logger.error("必须指定--from_db参数")

    elif args.command == 'analyze':
        analyze_results(ir_threshold=args.ir_threshold, limit=args.limit)

    elif args.command == 'pipeline':
        # 初始化
        if not init():
            return

        # 获取数据字段
        datafields = fetch_fundamental_data()
        if not datafields:
            return

        # 生成Alpha
        template_name, simulation_data_list = generate_alphas_from_template(
            template_index=args.template,
            datafields=datafields,
            limit=args.limit
        )
        if not simulation_data_list:
            return

        # 运行回测
        result = run_backtests(
            from_db=False,
            simulation_data_list=simulation_data_list,
            ir_threshold=args.ir_threshold,
            sharpe_threshold=args.sharpe_threshold if hasattr(args, 'sharpe_threshold') else 0
        )
        if not result or not result.get('success'):
            return

        # 分析结果
        analyze_results(ir_threshold=args.ir_threshold)

    elif args.command == 'generate_batch':
        generate_batch(args.start_template, args.end_template, args.limit_per_template)

    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        cli()
    except Exception as e:
        logger.exception(f"程序运行时发生错误: {e}")
        from notification import send_error_notification

        send_error_notification(f"程序运行时发生错误: {str(e)}")
