import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import pandas as pd
import os
import time
from datetime import datetime
from dotenv import load_dotenv
import click
import sys

# 支持两种运行方式：
# 1. 直接运行: python main.py (在 worldquant_alpha 目录下)
# 2. 模块运行: python -m worldquant_alpha.main (在项目根目录下)
try:
    from database import (
        init_db, get_session, get_good_alphas, has_successful_submission_today, close_database,
        save_alpha, save_alpha_result, update_alpha_status, save_pipeline_alphas,
        update_pipeline_alpha_backtest,
    )
    from alpha_generator import AlphaTemplate, create_default_templates, batch_generate_alphas
    from backtest import run_backtest, backtest_from_db, Backtester
    from notification import send_email
    from wd_lib_wrapper import get_api
    from graceful_shutdown import add_cleanup_callback
    from pipeline.engine import PipelineEngine
    from pipeline.config.loader import ConfigLoader
    from pipeline.submittable import run_submittable_candidate_pipeline
    from pipeline.services import fetch_dataset_fields, get_search_scope
    from wd_lib import WorldQuantClient
except ImportError:
    from worldquant_alpha.database import (
        init_db, get_session, get_good_alphas, has_successful_submission_today, close_database,
        save_alpha, save_alpha_result, update_alpha_status, save_pipeline_alphas,
        update_pipeline_alpha_backtest,
    )
    from worldquant_alpha.alpha_generator import AlphaTemplate, create_default_templates, batch_generate_alphas
    from worldquant_alpha.backtest import run_backtest, backtest_from_db, Backtester
    from worldquant_alpha.notification import send_email
    from worldquant_alpha.wd_lib_wrapper import get_api
    from worldquant_alpha.graceful_shutdown import add_cleanup_callback
    from worldquant_alpha.pipeline.engine import PipelineEngine
    from worldquant_alpha.pipeline.config.loader import ConfigLoader
    from worldquant_alpha.pipeline.submittable import run_submittable_candidate_pipeline
    from worldquant_alpha.pipeline.services import fetch_dataset_fields, get_search_scope
    from worldquant_alpha.wd_lib import WorldQuantClient

# 加载环境变量
load_dotenv()

# 配置日志
log_level_str = os.getenv('LOG_LEVEL', 'INFO')
log_level = getattr(logging, log_level_str.upper(), logging.INFO)

# 确保日志输出到 stdout 并立即刷新
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(log_level)
handler.flush = sys.stdout.flush  # 强制立即刷新
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 清除现有 handlers 并添加新的
root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.addHandler(handler)
root_logger.setLevel(log_level)

logger = logging.getLogger(__name__)

LEGACY_COMMAND_MAPPING = {
    "fetch": "submittable-candidates / pipeline",
    "generate": "pipeline",
    "backtest": "pipeline",
    "full-pipeline": "submittable-candidates",
}


def log_legacy_command_mapping(command_name: str):
    mapped_entry = LEGACY_COMMAND_MAPPING.get(command_name)
    if mapped_entry:
        logger.info("旧入口 `%s` 已收敛到推荐主入口 `%s`", command_name, mapped_entry)


def backtest_payload_file(payload_file: str, output_file: str = None, limit: int = 0,
                          dry_run: bool = False, submit_delay: float = 0.0,
                          retry_limit: int = 2, retry_backoff: float = 15.0,
                          max_workers: int = 4):
    """读取 payload JSON 并并发提交回测。"""
    if not os.path.exists(payload_file):
        raise click.ClickException(f"文件不存在: {payload_file}")

    with open(payload_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    settings = payload.get("settings", {}) or {}
    expressions = payload.get("expressions", []) or []
    if not expressions:
        raise click.ClickException("payload 中未找到 expressions")

    normalized = []
    for idx, item in enumerate(expressions, start=1):
        if isinstance(item, str):
            expr = item.strip()
            item_index = idx
        else:
            expr = str(item.get("expression", "")).strip()
            item_index = item.get("index", idx)

        if not expr:
            logger.warning("跳过空表达式: index=%s", item_index)
            continue

        normalized.append({
            "index": item_index,
            "expression": expr,
        })

    if not normalized:
        raise click.ClickException("没有可提交回测的有效表达式")

    if limit and limit > 0:
        normalized = normalized[:limit]

    logger.info("读取 payload 成功: expressions=%s, 使用=%s", len(expressions), len(normalized))
    logger.info("共享 settings: %s", settings)

    if dry_run:
        logger.info("[DRY_RUN] 干运行模式，不实际提交回测")
        for item in normalized[:5]:
            logger.info("  [%s] %s", item["index"], item["expression"][:160])
        summary = {
            "input_file": payload_file,
            "total": len(normalized),
            "success": 0,
            "failed": 0,
            "timestamp": datetime.now().isoformat(),
            "settings": settings,
        }
        return {
            "summary": summary,
            "results": [],
        }

    template_name = f"payload_json:{os.path.basename(payload_file)}"
    pipeline_stage = "payload_json"
    payload_dataset_id = f"payload:{os.path.basename(payload_file)}"

    pipeline_session = get_session()
    try:
        save_pipeline_alphas(
            pipeline_session,
            [item["expression"] for item in normalized],
            order=0,
            stage=pipeline_stage,
            settings=settings,
            dataset_id=payload_dataset_id,
        )
    finally:
        pipeline_session.close()

    logger.info("payload 并发回测开始: total=%s, max_workers=%s", len(normalized), max_workers)

    def _run_single_payload_backtest(pos: int, item: dict):
        import hashlib

        expr = item["expression"]
        alpha_db_id = save_alpha(expr, template_name=template_name, settings=settings)
        if alpha_db_id:
            update_alpha_status(alpha_db_id, 'running')

        # 按 worker 槽位做轻度错峰，避免并发提交瞬时撞到同一秒。
        if submit_delay > 0:
            slot_delay = submit_delay * ((pos - 1) % max_workers)
            if slot_delay > 0:
                logger.info("[%s/%s] 提交前错峰等待 %.1f 秒: [%s]", pos, len(normalized), slot_delay, item["index"])
                time.sleep(slot_delay)

        logger.info("[%s/%s] 提交回测: [%s] %s", pos, len(normalized), item["index"], expr[:120])

        client = WorldQuantClient()
        if not client.login():
            error_message = "WorldQuant 登录失败"
            if alpha_db_id:
                update_alpha_status(alpha_db_id, 'failed')
            pipeline_session = get_session()
            try:
                update_pipeline_alpha_backtest(
                    pipeline_session,
                    hashlib.sha256(expr.encode()).hexdigest(),
                    is_tested=True,
                    backtest_status='failed',
                    error_message=error_message,
                    candidate_status='tested',
                    backtested_at=datetime.now(),
                )
            finally:
                pipeline_session.close()

            return {
                "_order": pos,
                "index": item["index"],
                "expression": expr,
                "success": False,
                "db_alpha_id": alpha_db_id,
                "error": error_message,
                "settings": settings,
            }

        result = None
        error_message = "回测失败"

        for attempt in range(retry_limit + 1):
            result = client.run_backtest(alpha_expression=expr, settings=settings, update_pipeline_db=False)
            if result:
                break

            if attempt < retry_limit:
                wait_seconds = retry_backoff * (2 ** attempt)
                logger.warning(
                    "  -> 回测失败，准备重试: index=%s, attempt=%s/%s, wait=%ss",
                    item["index"],
                    attempt + 1,
                    retry_limit + 1,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
            else:
                error_message = f"回测失败，已重试 {retry_limit + 1} 次"

        if result:
            if alpha_db_id:
                save_alpha_result(
                    alpha_id=alpha_db_id,
                    platform_id=result.get("alpha_id"),
                    sharpe=result.get("sharpe"),
                    turnover=result.get("turnover"),
                    fitness=result.get("fitness"),
                    color=result.get("color"),
                    raw_result=result,
                )
                update_alpha_status(alpha_db_id, 'completed')

            pipeline_session = get_session()
            try:
                update_pipeline_alpha_backtest(
                    pipeline_session,
                    hashlib.sha256(expr.encode()).hexdigest(),
                    is_tested=True,
                    backtest_status='completed',
                    platform_alpha_id=result.get("alpha_id"),
                    sharpe=result.get("sharpe"),
                    fitness=result.get("fitness"),
                    turnover=result.get("turnover"),
                    color=result.get("color"),
                    candidate_status='tested',
                    backtested_at=datetime.now(),
                )
            finally:
                pipeline_session.close()

            logger.info(
                "  -> 成功: alpha_id=%s, db_alpha_id=%s, sharpe=%s, fitness=%s",
                result.get("alpha_id"),
                alpha_db_id,
                result.get("sharpe"),
                result.get("fitness"),
            )
            return {
                "_order": pos,
                "index": item["index"],
                "expression": expr,
                "success": True,
                "db_alpha_id": alpha_db_id,
                "alpha_id": result.get("alpha_id"),
                "status": result.get("status"),
                "sharpe": result.get("sharpe"),
                "fitness": result.get("fitness"),
                "turnover": result.get("turnover"),
                "returns": result.get("returns"),
                "drawdown": result.get("drawdown"),
                "grade": result.get("grade"),
                "color": result.get("color"),
                "settings": settings,
            }

        if alpha_db_id:
            update_alpha_status(alpha_db_id, 'failed')

        pipeline_session = get_session()
        try:
            update_pipeline_alpha_backtest(
                pipeline_session,
                hashlib.sha256(expr.encode()).hexdigest(),
                is_tested=True,
                backtest_status='failed',
                error_message=error_message,
                candidate_status='tested',
                backtested_at=datetime.now(),
            )
        finally:
            pipeline_session.close()

        logger.warning("  -> 回测失败: index=%s", item["index"])
        return {
            "_order": pos,
            "index": item["index"],
            "expression": expr,
            "success": False,
            "db_alpha_id": alpha_db_id,
            "error": error_message,
            "settings": settings,
        }

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single_payload_backtest, pos, item): (pos, item["index"])
            for pos, item in enumerate(normalized, start=1)
        }

        for future in as_completed(futures):
            pos, item_index = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                logger.exception("payload 并发任务异常: pos=%s, index=%s", pos, item_index)
                results.append({
                    "_order": pos,
                    "index": item_index,
                    "expression": normalized[pos - 1]["expression"],
                    "success": False,
                    "db_alpha_id": None,
                    "error": str(exc),
                    "settings": settings,
                })

    results.sort(key=lambda item: item["_order"])
    for item in results:
        item.pop("_order", None)

    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(payload_file))[0]
        output_file = os.path.join(os.path.dirname(payload_file), f"{base_name}_backtest_results_{timestamp}.json")

    summary = {
        "input_file": payload_file,
        "total": len(normalized),
        "success": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "timestamp": datetime.now().isoformat(),
        "settings": settings,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": summary,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    logger.info("payload 回测完成: success=%s, failed=%s, output=%s", summary["success"], summary["failed"], output_file)
    return {
        "output_file": output_file,
        "summary": summary,
        "results": results,
    }

# 显式设置控制台输出编码，避免 Windows 终端日志出现乱码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

# 注册清理回调
add_cleanup_callback(close_database)
logger.info("已注册数据库关闭回调")


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


def fetch_fundamental_data(template_name=None, instrumentType="EQUITY", region="USA", universe="TOP3000", delay=1):
    """获取基本面数据字段"""
    logger.info(f"开始获取基本面数据字段，instrumentType: {instrumentType}, region: {region}, universe: {universe}, delay: {delay}")

    try:
        dataset_id = template_name if template_name else 'fundamental6'
        client = WorldQuantClient()
        if not client.login():
            logger.error("WorldQuant 登录失败，无法获取数据字段")
            return None

        search_scope = get_search_scope(
            instrument_type=instrumentType,
            region=region,
            delay=delay,
            universe=universe,
        )
        datafields = fetch_dataset_fields(
            client=client,
            datasets=[dataset_id],
            search_scope=search_scope,
        )
        if not datafields:
            logger.error("未获取到任何数据字段")
            return None

        os.makedirs('data', exist_ok=True)
        if template_name:
            filename = f'data/{template_name}_datafields.json'
        else:
            filename = 'data/fundamental_datafields.json'
        with open(filename, "w") as f:
            json.dump(datafields, f)
        logger.info(f"成功获取基本面数据字段，共 {len(datafields)} 个字段，已保存到 {filename}")
        return datafields
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

    # 根据模板索引决定生成方式和阶数
    # 当template_index为0时，使用默认模板生成
    # 当template_index为1-3时，使用对应阶数的工厂函数生成
    order = None
    if template_index == 0:
        # 使用默认模板生成
        logger.info("使用默认模板生成Alpha表达式")
        order = 0
        # 确保模板索引有效
        if template_index < 0 or template_index >= len(templates):
            logger.error(f"无效的模板索引: {template_index}，有效范围: 0-{len(templates) - 1}")
            return None, None
    elif template_index in [1, 2, 3]:
        # 使用对应阶数的工厂函数生成
        order = template_index
        logger.info(f"使用{order}阶工厂函数生成Alpha表达式")
        # 强制使用第一个模板，因为阶数生成不依赖于模板
        template_index = 0
    else:
        logger.error(f"无效的模板索引: {template_index}，有效范围: 0-3")
        return None, None

    # 选择模板
    template = templates[template_index]
    logger.info(f"使用模板: {template.name}")

    # 生成Alpha表达式
    _, simulation_data_list = batch_generate_alphas(
        template=template,
        datafields=datafields,
        limit=limit,
        db_save=True,
        order=order
    )

    logger.info(f"生成了 {len(simulation_data_list)} 个模拟请求数据")
    return template.name, simulation_data_list


def run_backtests(from_db=True, simulation_data_list=None, limit=None, ir_threshold=0.1, 
                  sharpe_threshold=1.6, max_workers=4):
    """
    运行回测
    
    参数:
    - from_db: 是否从数据库获取Alpha
    - simulation_data_list: 模拟请求数据列表
    - limit: 限制数量
    - ir_threshold: IR阈值
    - sharpe_threshold: Sharpe阈值
    - max_workers: 并发线程数，默认4个
    """
    logger.info(f"开始运行回测，从数据库: {from_db}, 限制: {limit}, Sharpe阈值: {sharpe_threshold}, "
               f"并发数: {max_workers}")

    # 创建回测器
    backtester = Backtester(max_retry=3, batch_size=max_workers, notify=True, sharpe_threshold=sharpe_threshold)

    # 运行回测
    if from_db:
        logger.info("从数据库运行回测")
        result = backtester.backtest_from_database(limit=limit)
    elif simulation_data_list:
        logger.info(f"从提供的模拟请求数据列表运行回测，总数: {len(simulation_data_list)}, 并发: {max_workers}")
        result = backtester.backtest_simulation_data_list(
            simulation_data_list, 
            ir_threshold=ir_threshold,
            max_workers=max_workers
        )
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
@click.option('--template_name', type=str, help='模板名称筛选（如"模板1"）')
def backtest(from_db, limit, sharpe_threshold, template_name):
    """运行Alpha回测"""
    log_legacy_command_mapping("backtest")
    logger.info(f"运行回测，从数据库：{from_db}，限制数量：{limit}，Sharpe阈值：{sharpe_threshold}，模板名称：{template_name}")

    if from_db:
        # 创建回测器并直接调用
        backtester = Backtester(max_retry=3, batch_size=8, notify=True, sharpe_threshold=sharpe_threshold)
        results = backtester.backtest_from_database(limit=limit, template_name=template_name)
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


@cli.command('backtest-db')
@click.option('--status', type=click.Choice(['pending', 'failed', 'all', 'running']),
              default='pending', show_default=True,
              help='筛选Alpha状态: pending=待测试, failed=失败的, all=全部未测试, running=卡住的')
@click.option('--template_name', type=str, default=None,
              help='按模板名称筛选（逗号分隔，如: "行业中性化残差动量,创新性修正动量"）')
@click.option('--limit', type=int, default=100, show_default=True,
              help='最多回测的Alpha数量')
@click.option('--sharpe_threshold', type=float, default=1.6, show_default=True,
              help='Sharpe比率阈值，达到此阈值才保存结果')
@click.option('--max_workers', type=int, default=4, show_default=True,
              help='并发回测线程数（1-10）')
@click.option('--no_email', is_flag=True, help='禁用邮件通知')
@click.option('--reset_failed', is_flag=True,
              help='回测前将 failed 状态的Alpha重置为 pending')
@click.option('--reset_running', is_flag=True,
              help='回测前将卡住的 running 状态重置为 pending')
@click.option('--list_only', is_flag=True,
              help='只列出待回测的Alpha，不执行回测')
@click.option('--date_from', type=str, default=None,
              help='筛选创建日期起始（格式: YYYY-MM-DD，如: 2026-03-17）')
@click.option('--date_to', type=str, default=None,
              help='筛选创建日期结束（格式: YYYY-MM-DD，如: 2026-03-18）')
@click.option('--expr_contains', type=str, default=None,
              help='按表达式内容筛选（子字符串匹配，如: "anl10_netfy1"）')
@click.option('--export_csv', is_flag=True,
              help='回测完成后将结果导出为CSV文件')
def backtest_db(status, template_name, limit, sharpe_threshold, max_workers,
                no_email, reset_failed, reset_running, list_only,
                date_from, date_to, expr_contains, export_csv):
    """
    从数据库读取Alpha进行回测
    
    示例命令:
    
    \b
    # 回测所有 pending 状态的Alpha（默认）
    python -m worldquant_alpha.main backtest-db
    
    \b
    # 回测所有失败的Alpha（重新测试）
    python -m worldquant_alpha.main backtest-db --status failed
    
    \b
    # 重置并重测失败Alpha，8并发
    python -m worldquant_alpha.main backtest-db --status failed --reset_failed --max_workers 8
    
    \b
    # 只测某个模板的Alpha
    python -m worldquant_alpha.main backtest-db --template_name "行业中性化残差动量"
    
    \b
    # 按日期筛选，今日生成的Alpha
    python -m worldquant_alpha.main backtest-db --date_from 2026-03-17 --limit 200
    
    \b
    # 先列出待测Alpha，不执行回测
    python -m worldquant_alpha.main backtest-db --list_only
    
    \b
    # 回测并导出CSV结果
    python -m worldquant_alpha.main backtest-db --limit 500 --export_csv --no_email
    """
    try:
        from worldquant_alpha.database import get_session as _gs, Alpha as _A
        from worldquant_alpha.alpha_generator import create_simulation_data as _csd
    except ImportError:
        from database import get_session as _gs, Alpha as _A
        from alpha_generator import create_simulation_data as _csd

    session = _gs()

    # ========== Step 0: 重置状态 ==========
    if reset_failed:
        reset_count = session.query(_A).filter(_A.status == 'failed').update({'status': 'pending', 'is_tested': False})
        session.commit()
        logger.info(f"[RESET] 已将 {reset_count} 个 failed Alpha 重置为 pending")

    if reset_running:
        reset_count = session.query(_A).filter(_A.status == 'running').update({'status': 'pending'})
        session.commit()
        logger.info(f"[RESET] 已将 {reset_count} 个 running Alpha 重置为 pending")

    # ========== Step 1: 构建查询 ==========
    query = session.query(_A)

    # 状态过滤
    if status == 'pending':
        query = query.filter(_A.status == 'pending')
    elif status == 'failed':
        query = query.filter(_A.status == 'failed')
    elif status == 'running':
        query = query.filter(_A.status == 'running')
    elif status == 'all':
        query = query.filter(_A.is_tested == False)

    # 模板名称过滤
    if template_name:
        names = [n.strip() for n in template_name.split(',')]
        if len(names) == 1:
            query = query.filter(_A.template_name == names[0])
        else:
            from sqlalchemy import or_
            query = query.filter(or_(*[_A.template_name == n for n in names]))
        logger.info(f"按模板名称筛选: {names}")

    # 日期过滤
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(_A.created_at >= dt_from)
            logger.info(f"日期起始筛选: {date_from}")
        except ValueError:
            logger.warning(f"日期格式错误: {date_from}，应为 YYYY-MM-DD，忽略此过滤器")

    if date_to:
        try:
            from datetime import timedelta
            dt_to = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(_A.created_at < dt_to)
            logger.info(f"日期结束筛选: {date_to}")
        except ValueError:
            logger.warning(f"日期格式错误: {date_to}，应为 YYYY-MM-DD，忽略此过滤器")

    # 表达式内容过滤
    if expr_contains:
        query = query.filter(_A.alpha_expression.contains(expr_contains))
        logger.info(f"表达式内容筛选: {expr_contains}")

    # 排序 + 限制
    query = query.order_by(_A.created_at.desc()).limit(limit)

    alphas = query.all()
    session.close()

    total = len(alphas)
    logger.info(f"========== 数据库回测 ==========")
    logger.info(f"筛选条件: status={status}, template={template_name or '全部'}, limit={limit}")
    logger.info(f"找到 {total} 个待回测的 Alpha")

    if total == 0:
        logger.warning("没有找到符合条件的Alpha，退出")
        click.echo("\n提示: 使用 --status all 或 --reset_failed 来扩大筛选范围")
        return

    # ========== Step 2: list_only 模式 ==========
    if list_only:
        click.echo(f"\n=== 待回测 Alpha 列表（共 {total} 个）===")
        # 统计按模板分组
        from collections import Counter
        tmpl_counts = Counter(a.template_name for a in alphas)
        click.echo("\n按模板统计:")
        for tmpl, cnt in sorted(tmpl_counts.items(), key=lambda x: -x[1]):
            click.echo(f"  {tmpl}: {cnt} 个")

        click.echo(f"\n前10条 Alpha:")
        for i, a in enumerate(alphas[:10], 1):
            click.echo(f"  [{i}] ID={a.id} status={a.status} template={a.template_name}")
            click.echo(f"       {a.alpha_expression[:100]}...")
        click.echo()
        return

    # ========== Step 3: 转换为 simulation_data_list ==========
    simulation_data_list = []
    for a in alphas:
        sim_data = _csd(a.alpha_expression, a.settings)
        sim_data['id'] = a.id  # 附加数据库ID，方便更新状态
        simulation_data_list.append(sim_data)

    logger.info(f"准备回测 {len(simulation_data_list)} 个 Alpha，并发: {max_workers}，Sharpe阈值: {sharpe_threshold}")

    # ========== Step 4: 执行回测 ==========
    print(">>> 开始回测，请稍候...", flush=True)
    backtester = Backtester(
        max_retry=3,
        batch_size=max_workers,
        notify=not no_email,
        sharpe_threshold=sharpe_threshold
    )
    results = backtester.backtest_simulation_data_list(
        simulation_data_list,
        max_workers=max_workers
    )

    # ========== Step 5: 汇总 ==========
    if results:
        logger.info(f"========== 回测完成 ==========")
        logger.info(f"总处理: {results.get('total_processed', 0)}")
        logger.info(f"成功:   {results.get('success_count', 0)}")
        logger.info(f"失败:   {results.get('fail_count', 0)}")
        logger.info(f"优质:   {results.get('good_alpha_count', 0)} (GREEN)")

        # 导出CSV
        if export_csv and results.get('results'):
            os.makedirs('results', exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_file = f"results/backtest_db_{ts}.csv"
            rows = []
            for r in results['results']:
                is_data = r.get('is', {})
                rows.append({
                    'platform_id': r.get('id'),
                    'status': r.get('status'),
                    'color': r.get('color'),
                    'sharpe': is_data.get('sharpe'),
                    'fitness': is_data.get('fitness'),
                    'turnover': is_data.get('turnover'),
                })
            if rows:
                pd.DataFrame(rows).to_csv(csv_file, index=False)
                logger.info(f"[SAVE] 结果已导出到: {csv_file}")

    # 发送邮件
    if not no_email and results:
        send_email(results)


@cli.command()
@click.option('--template', type=int, default=0, help='模板索引（0-4）')
@click.option('--limit', type=int, default=10, help='生成的Alpha数量限制')
def generate(template, limit):
    """从模板生成Alpha表达式"""
    log_legacy_command_mapping("generate")
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

    # 检查模板索引是否有效
    if template < 0:
        logger.error(f"无效的模板索引：{template}")
        return

    # 处理模板索引为0的情况，使用模板生成
    # 处理模板索引为1-3的情况，使用对应阶数的工厂函数生成
    if template == 0:
        # 使用默认模板生成
        order = 0
        logger.info("使用默认模板生成Alpha表达式")
        # 检查模板索引是否在有效范围内
        if template >= len(templates):
            logger.error(f"无效的模板索引：{template}，有效范围：0-{len(templates) - 1}")
            return
        selected_template = templates[template]
    elif template in [1, 2, 3]:
        # 使用对应阶数的工厂函数生成
        order = template
        logger.info(f"使用{order}阶工厂函数生成Alpha表达式")
        # 强制使用第一个模板，因为阶数生成不依赖于模板
        selected_template = templates[0]
        # 修改模板名称为模板序号，以便在数据库中区分
        selected_template.name = f"模板{template}"
    else:
        # 检查模板索引是否在有效范围内
        if template >= len(templates):
            logger.error(f"无效的模板索引：{template}，有效范围：0-{len(templates) - 1}")
            return
        selected_template = templates[template]
        order = None

    logger.info(f"使用模板：{selected_template.name}")

    # 生成Alpha表达式
    template_name, simulation_data_list = batch_generate_alphas(
        template=selected_template,
        datafields=datafields,
        limit=limit,
        db_save=True,
        order=order
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
@click.option('--config', type=str, default=None,
              help='预设配置名称，可选: analyst10_eur, analyst10_usa, analyst10_eur_d1, analyst10_usa_market, '
                   'sal_eur, sal_usa, ebi_eur, ebi_usa, revise_eur, revise_usa, '
                   'innovation_eur, innovation_usa, high_turnover_eur, low_turnover_usa')
@click.option('--region', type=str, default='EUR', help='地区: USA/EUR/CHN/HKG/JPN/KOR/GLB等')
@click.option('--universe', type=str, default='TOP2500', help='股票池: TOP3000/TOP2500/TOP1200/TOP500等')
@click.option('--delay', type=int, default=1, help='延迟天数: 1 或 0')
@click.option('--decay', type=int, default=0, help='衰减天数: 0表示不衰减，正整数表示指数衰减天数')
@click.option('--neutralization', type=str, default='SUBINDUSTRY',
              help='中性化方式: MARKET/SECTOR/INDUSTRY/SUBINDUSTRY/NONE')
@click.option('--truncation', type=float, default=0.08, help='截断比例: 0.0-1.0，通常0.01-0.10')
@click.option('--pasteurization', type=str, default='ON', help='数据净化: ON/OFF')
@click.option('--nan_handling', type=str, default='ON', help='NaN处理: ON/OFF')
@click.option('--unit_handling', type=str, default='VERIFY', help='单位处理: VERIFY/CASH')
@click.option('--instrument_type', type=str, default='EQUITY', help='工具类型: EQUITY/FUTURES')
@click.option('--start_template', type=int, default=0, help='起始模板索引（0-9）')
@click.option('--end_template', type=int, default=5, help='结束模板索引（0-9，不含）')
@click.option('--template_names', type=str, default=None,
              help='指定模板名称（逗号分隔），如: "行业中性化残差动量,分析师预期修正陡度"，优先于start/end_template')
@click.option('--limit_per_template', type=int, default=50, help='每个模板生成的Alpha数量限制')
@click.option('--sharpe_threshold', type=float, default=1.6, help='Sharpe比率阈值，低于此值不保存到数据库')
@click.option('--ir_threshold', type=float, default=0.1, help='信息比率阈值')
@click.option('--order', type=int, default=0, help='Alpha生成阶数: 0=模板直接生成, 1=一阶工厂, 2=二阶, 3=三阶')
@click.option('--max_workers', type=int, default=4, help='回测并发线程数（1-10）')
@click.option('--skip_check', is_flag=True, help='跳过今日提交检查')
@click.option('--no_email', is_flag=True, help='禁用邮件通知')
@click.option('--dry_run', is_flag=True, help='干运行：只生成Alpha不回测，用于测试')
@click.option('--list_templates', is_flag=True, help='列出所有可用模板名称')
@click.option('--list_configs', is_flag=True, help='列出所有预设配置')
# ========== 新增参数：支持从数据库读取Alpha ==========
@click.option('--input_order', type=int, default=None,
              help='从数据库读取指定阶数的未回测Alpha (1=一阶, 2=二阶, 3=三阶)')
@click.option('--input_stage', type=str, default=None,
              help='从数据库读取指定阶段的Alpha (first_order/second_order/third_order)')
@click.option('--skip_generation', is_flag=True,
              help='跳过生成阶段，直接使用数据库中的Alpha')
@click.option('--only_backtest', is_flag=True,
              help='只执行回测，不生成新Alpha')
@click.option('--start_stage', type=str, default=None,
              help='从指定阶段开始执行 (first_order/second_order/third_order)')
@click.option('--end_stage', type=str, default=None,
              help='执行到指定阶段结束')
def pipeline(config, region, universe, delay, decay, neutralization, truncation,
             pasteurization, nan_handling, unit_handling, instrument_type,
             start_template, end_template, template_names, limit_per_template,
             sharpe_threshold, ir_threshold, order, max_workers,
             skip_check, no_email, dry_run, list_templates, list_configs,
             input_order, input_stage, skip_generation, only_backtest,
             start_stage, end_stage):
    """
    完整回测流程：生成Alpha -> 回测 -> 筛选
    
    示例命令:
    
    \b
    # 使用预设配置
    python -m worldquant_alpha.main pipeline --config analyst10_eur
    
    \b
    # 自定义settings
    python -m worldquant_alpha.main pipeline --region EUR --universe TOP2500 --delay 1 \\
        --neutralization SUBINDUSTRY --decay 0 --truncation 0.08
    
    \b
    # 指定模板名称
    python -m worldquant_alpha.main pipeline --config analyst10_eur \\
        --template_names "行业中性化残差动量,分析师预期修正陡度,创新性修正动量"
    
    \b
    # 指定模板索引范围
    python -m worldquant_alpha.main pipeline --config analyst10_eur \\
        --start_template 0 --end_template 3 --limit_per_template 10
    
    \b
    # 高并发回测（USA TOP3000，市场中性化）
    python -m worldquant_alpha.main pipeline --region USA --universe TOP3000 \\
        --neutralization MARKET --sharpe_threshold 1.5 --max_workers 6
    
    \b
    # 低换手率策略（长周期）
    python -m worldquant_alpha.main pipeline --config revise_eur \\
        --decay 10 --truncation 0.05 --limit_per_template 30
        
    \b
    ========== 从数据库读取Alpha进行回测 ==========
    
    \b
    # 从数据库读取一阶Alpha进行回测
    python -m worldquant_alpha.main pipeline --input_order 1 --input_stage first_order
    
    \b
    # 从数据库读取二阶Alpha，只执行回测
    python -m worldquant_alpha.main pipeline --input_order 2 --input_stage second_order --only_backtest
    
    \b
    # 跳过生成阶段，使用数据库中的Alpha回测
    python -m worldquant_alpha.main pipeline --skip_generation --input_order 1 --limit_per_template 100
    
    \b
    # 从数据库读取三阶Alpha，限制50个
    python -m worldquant_alpha.main pipeline --input_order 3 --input_stage third_order --limit_per_template 50
    """

    # ==================== 预设配置 ====================
    config_presets = {
        # analyst10 EUR TOPCS1600
        'analyst10_eur_topcs1600': {
            'region': 'EUR', 'universe': 'TOPCS1600', 'delay': 1, 'decay': 0,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.6, 'ir_threshold': 0.1,
            'start_template': 0, 'end_template': 10,
        },
        # analyst10 EUR系列
        'analyst10_eur': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 0,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.6, 'ir_threshold': 0.1,
            'start_template': 0, 'end_template': 10,
        },
        'analyst10_eur_market': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 0,
            'neutralization': 'MARKET', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.1,
            'start_template': 0, 'end_template': 10,
        },
        'analyst10_eur_industry': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 5,
            'neutralization': 'INDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.1,
            'start_template': 0, 'end_template': 10,
        },
        # analyst10 USA系列
        'analyst10_usa': {
            'region': 'USA', 'universe': 'TOP3000', 'delay': 1, 'decay': 0,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.6, 'ir_threshold': 0.1,
            'start_template': 0, 'end_template': 10,
        },
        'analyst10_usa_market': {
            'region': 'USA', 'universe': 'TOP3000', 'delay': 1, 'decay': 0,
            'neutralization': 'MARKET', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.1,
            'start_template': 0, 'end_template': 10,
        },
        # 销售额类模板
        'sal_eur': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 0,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.09,
            'start_template': 0, 'end_template': 5,
            'template_names': '分析师预期修正陡度,模型残差横截面挖掘,创新性修正动量',
        },
        'sal_usa': {
            'region': 'USA', 'universe': 'TOP3000', 'delay': 1, 'decay': 0,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.09,
            'start_template': 0, 'end_template': 5,
            'template_names': '分析师预期修正陡度,模型残差横截面挖掘,创新性修正动量',
        },
        # EBIT类模板
        'ebi_eur': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 0,
            'neutralization': 'INDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.08,
            'start_template': 0, 'end_template': 5,
            'template_names': '行业中性化残差动量,预期惊喜复合强度,修正幅度-广度协同',
        },
        'ebi_usa': {
            'region': 'USA', 'universe': 'TOP3000', 'delay': 1, 'decay': 0,
            'neutralization': 'INDUSTRY', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.08,
            'start_template': 0, 'end_template': 5,
            'template_names': '行业中性化残差动量,预期惊喜复合强度,修正幅度-广度协同',
        },
        # 修正类模板（低换手率）
        'revise_eur': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 10,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.05,
            'sharpe_threshold': 1.4, 'ir_threshold': 0.08,
            'start_template': 7, 'end_template': 10,
            'template_names': '修正时效性加权,修正幅度-广度协同',
        },
        'revise_usa': {
            'region': 'USA', 'universe': 'TOP3000', 'delay': 1, 'decay': 10,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.05,
            'sharpe_threshold': 1.4, 'ir_threshold': 0.08,
            'start_template': 7, 'end_template': 10,
            'template_names': '修正时效性加权,修正幅度-广度协同',
        },
        # 创新修正类（高信息量）
        'innovation_eur': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 0,
            'neutralization': 'SECTOR', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.1,
            'start_template': 5, 'end_template': 10,
            'template_names': '智能预期分歧度,创新性修正动量,预期惊喜复合强度',
        },
        'innovation_usa': {
            'region': 'USA', 'universe': 'TOP3000', 'delay': 1, 'decay': 0,
            'neutralization': 'SECTOR', 'truncation': 0.08,
            'sharpe_threshold': 1.5, 'ir_threshold': 0.1,
            'start_template': 5, 'end_template': 10,
            'template_names': '智能预期分歧度,创新性修正动量,预期惊喜复合强度',
        },
        # 高换手率策略
        'high_turnover_eur': {
            'region': 'EUR', 'universe': 'TOP2500', 'delay': 1, 'decay': 0,
            'neutralization': 'MARKET', 'truncation': 0.10,
            'sharpe_threshold': 1.3, 'ir_threshold': 0.07,
            'start_template': 0, 'end_template': 5,
            'template_names': '价量背离隐性强度,期权隐含偏度比较',
        },
        # 低换手率策略
        'low_turnover_usa': {
            'region': 'USA', 'universe': 'TOP3000', 'delay': 1, 'decay': 20,
            'neutralization': 'SUBINDUSTRY', 'truncation': 0.04,
            'sharpe_threshold': 1.6, 'ir_threshold': 0.12,
            'start_template': 0, 'end_template': 10,
        },
    }

    # 列出所有可用模板
    if list_templates:
        templates = create_default_templates()
        click.echo("\n=== 可用模板列表 ===")
        for i, t in enumerate(templates):
            click.echo(f"  [{i}] {t.name} (组合数: {t.total_combinations})")
        click.echo()
        return

    # 列出所有预设配置
    if list_configs:
        click.echo("\n=== 可用预设配置 ===")
        for name, cfg in config_presets.items():
            click.echo(f"\n  --config {name}")
            click.echo(f"    region={cfg['region']}, universe={cfg['universe']}, delay={cfg['delay']}")
            click.echo(f"    neutralization={cfg['neutralization']}, decay={cfg['decay']}, truncation={cfg['truncation']}")
            click.echo(f"    sharpe_threshold={cfg['sharpe_threshold']}, ir_threshold={cfg['ir_threshold']}")
            if cfg.get('template_names'):
                click.echo(f"    templates={cfg['template_names']}")
        click.echo()
        return

    # 应用预设配置
    effective_template_names = template_names
    if config:
        if config not in config_presets:
            click.echo(f"[ERROR] 未知的预设配置: {config}")
            click.echo(f"可用预设: {', '.join(config_presets.keys())}")
            return
        preset = config_presets[config]
        region = preset.get('region', region)
        universe = preset.get('universe', universe)
        delay = preset.get('delay', delay)
        decay = preset.get('decay', decay)
        neutralization = preset.get('neutralization', neutralization)
        truncation = preset.get('truncation', truncation)
        sharpe_threshold = preset.get('sharpe_threshold', sharpe_threshold)
        ir_threshold = preset.get('ir_threshold', ir_threshold)
        start_template = preset.get('start_template', start_template)
        end_template = preset.get('end_template', end_template)
        if preset.get('template_names') and not template_names:
            effective_template_names = preset.get('template_names')
        logger.info(f"应用预设配置: {config}")

    # 构建settings
    settings = {
        "instrumentType": instrument_type,
        "region": region,
        "universe": universe,
        "delay": delay,
        "decay": decay,
        "neutralization": neutralization,
        "truncation": truncation,
        "pasteurization": pasteurization,
        "unitHandling": unit_handling,
        "nanHandling": nan_handling,
        "language": "FASTEXPR",
        "visualization": False
    }

    logger.info(f"========== 启动完整流程 ==========")
    logger.info(f"Settings: region={region}, universe={universe}, delay={delay}, "
                f"decay={decay}, neutralization={neutralization}, truncation={truncation}")
    logger.info(f"Sharpe阈值: {sharpe_threshold}, IR阈值: {ir_threshold}, 阶数: {order}")
    logger.info(f"并发数: {max_workers}, dry_run: {dry_run}")

    # 检查今天是否已经提交了有效的alpha
    if not skip_check and has_successful_submission_today():
        logger.info("今天已经成功提交了有效的alpha，不再运行")
        return

    # 解析模板名称筛选
    all_templates = create_default_templates()
    selected_templates = []

    if effective_template_names:
        # 按名称选择模板
        name_list = [n.strip() for n in effective_template_names.split(',')]
        for name in name_list:
            matched = [t for t in all_templates if t.name == name]
            if matched:
                selected_templates.extend(matched)
                logger.info(f"按名称选择模板: {name}")
            else:
                logger.warning(f"未找到名称为 '{name}' 的模板，跳过")
    else:
        # 按索引范围选择模板
        for i in range(start_template, min(end_template, len(all_templates))):
            selected_templates.append(all_templates[i])

    if not selected_templates:
        logger.error("没有找到可用的模板，退出")
        return

    logger.info(f"选中 {len(selected_templates)} 个模板: {[t.name for t in selected_templates]}")

    # ========== 新增：从数据库读取指定阶数的Alpha ==========
    all_simulation_data = []
    
    if input_order or input_stage or skip_generation or only_backtest:
        # 从数据库读取Alpha
        logger.info("========== 从数据库读取Alpha ==========")
        try:
            from worldquant_alpha.database import get_session as _gs, get_untested_pipeline_alphas
        except ImportError:
            from database import get_session as _gs, get_untested_pipeline_alphas
        
        session = _gs()
        try:
            # 确定读取的order和stage
            db_order = input_order if input_order else 1
            db_stage = input_stage if input_stage else 'first_order'
            
            logger.info(f"从数据库读取 order={db_order}, stage={db_stage} 的未回测Alpha")
            db_alphas = get_untested_pipeline_alphas(session, order=db_order, stage=db_stage)
            
            if limit_per_template:
                db_alphas = db_alphas[:limit_per_template]
            
            if not db_alphas:
                logger.warning(f"数据库中没有找到 order={db_order}, stage={db_stage} 的未回测Alpha")
                if only_backtest:
                    return
            else:
                logger.info(f"从数据库读取了 {len(db_alphas)} 个未回测的Alpha")
                
                try:
                    from worldquant_alpha.alpha_generator import create_simulation_data as _csd
                except ImportError:
                    from alpha_generator import create_simulation_data as _csd
                
                for a in db_alphas:
                    sim_data = _csd(a.alpha_expression, a.settings)
                    sim_data['id'] = a.id
                    all_simulation_data.append(sim_data)
                
                logger.info(f"准备回测 {len(all_simulation_data)} 个Alpha")
        finally:
            session.close()
        
        # 如果是only_backtest模式，直接跳到回测
        if only_backtest and all_simulation_data:
            logger.info("========== 仅回测模式，跳过生成阶段 ==========")
        elif skip_generation and all_simulation_data:
            logger.info("========== 跳过生成阶段，使用数据库中的Alpha ==========")
    else:
        # ========== 原有逻辑：批量生成Alpha ==========
        logger.info("========== 开始生成Alpha ==========")

        for tmpl in selected_templates:
            logger.info(f"使用模板: {tmpl.name}")
            _, sim_list = batch_generate_alphas(
                template=tmpl,
                limit=limit_per_template,
                order=order,
                settings=settings
            )
            if sim_list:
                all_simulation_data.extend(sim_list)
                logger.info(f"模板 '{tmpl.name}' 生成了 {len(sim_list)} 个Alpha")

        if not all_simulation_data:
            logger.warning("没有生成新的Alpha，从数据库读取待回测的Alpha...")
            try:
                from worldquant_alpha.database import get_session as _gs, Alpha as _A
            except ImportError:
                from database import get_session as _gs, Alpha as _A
            session = _gs()
            db_alphas = session.query(_A).filter(
                _A.is_tested == False,
                _A.status != 'running'
            ).limit(limit_per_template * len(selected_templates)).all()
            session.close()

            if not db_alphas:
                logger.warning("数据库中也没有待回测的Alpha，退出")
                return

            try:
                from worldquant_alpha.alpha_generator import create_simulation_data as _csd
            except ImportError:
                from alpha_generator import create_simulation_data as _csd
            all_simulation_data = []
            for a in db_alphas:
                sim_data = _csd(a.alpha_expression, a.settings)
                sim_data['id'] = a.id  # 附加数据库ID，确保回测后能更新两张表
                all_simulation_data.append(sim_data)
            logger.info(f"从数据库读取了 {len(all_simulation_data)} 个待回测的Alpha")

    logger.info(f"共 {len(all_simulation_data)} 个Alpha表达式进入回测")

    if dry_run:
        logger.info("[DRY_RUN] 干运行模式，不执行实际回测")
        logger.info("生成的Alpha示例（前5个）:")
        for i, d in enumerate(all_simulation_data[:5]):
            logger.info(f"  [{i+1}] {d.get('regular','')[:120]}")
            logger.info(f"       settings: {d.get('settings',{})}")
        return

    # 运行回测
    logger.info("========== 开始回测 ==========")
    import sys
    print(">>> 开始回测，请稍候...", flush=True)
    sys.stdout.flush()
    results = run_backtests(
        from_db=False,
        simulation_data_list=all_simulation_data,
        limit=None,
        ir_threshold=ir_threshold,
        sharpe_threshold=sharpe_threshold,
        max_workers=max_workers
    )

    if results:
        logger.info(f"========== 回测完成 ==========")
        logger.info(f"总处理: {results.get('total_processed',0)}, "
                    f"成功: {results.get('success_count',0)}, "
                    f"失败: {results.get('fail_count',0)}, "
                    f"优质: {results.get('good_alpha_count',0)}")

    # 发送邮件通知
    if not no_email and results:
        logger.info("========== 发送邮件通知 ==========")
        send_email(results)

    logger.info(f"========== 流程完成 ==========")


@cli.command('submittable-candidates')
@click.option('--config', type=str, default=None, help='可选 pipeline 配置文件')
@click.option('--datasets', type=str, default='fundamental6', help='数据集列表，逗号分隔')
@click.option('--region', type=str, default='USA', help='地区')
@click.option('--universe', type=str, default='TOP3000', help='股票池')
@click.option('--delay', type=int, default=1, help='延迟')
@click.option('--instrument_type', type=str, default='EQUITY', help='工具类型')
@click.option('--first_order_limit', type=int, default=200, help='一阶生成数量限制')
@click.option('--template_names', type=str, default='', help='模板名称，逗号分隔')
@click.option('--state_file', type=str, default='.submittable_candidates_state.json', help='状态文件')
@click.option('--force', is_flag=True, help='强制重跑已完成阶段')
def submittable_candidates(config, datasets, region, universe, delay, instrument_type,
                           first_order_limit, template_names, state_file, force):
    """运行可提交候选主链：拉数 -> 一阶生成 -> 回测 -> 候选筛选"""
    dataset_list = [item.strip() for item in datasets.split(',') if item.strip()]
    template_name_list = [item.strip() for item in template_names.split(',') if item.strip()] or None

    summary = run_submittable_candidate_pipeline(
        config_path=config,
        datasets=dataset_list,
        region=region,
        universe=universe,
        delay=delay,
        instrument_type=instrument_type,
        first_order_limit=first_order_limit,
        template_names=template_name_list,
        state_file=state_file,
        force=force,
    )
    logger.info(
        "submittable-candidates 完成: candidate=%s, tested=%s",
        summary.get("candidate_count", 0),
        summary.get("tested_count", 0),
    )


@cli.command('pipeline-backtest-json')
@click.argument('payload_file', type=click.Path(exists=True))
@click.option('--output', type=str, default=None, help='结果输出文件路径')
@click.option('--limit', type=int, default=0, help='只提交前 N 条表达式，0 表示不限制')
@click.option('--dry-run', is_flag=True, help='只读取和打印，不实际提交回测')
@click.option('--submit-delay', type=float, default=3.0, show_default=True, help='每条表达式提交后的节流等待秒数')
@click.option('--retry-limit', type=int, default=2, show_default=True, help='单条表达式失败后的重试次数')
@click.option('--retry-backoff', type=float, default=15.0, show_default=True, help='失败重试基础退避秒数，后续按指数退避')
@click.option('--max-workers', type=int, default=4, show_default=True, help='并发提交回测线程数，默认4个')
def pipeline_backtest_json(payload_file, output, limit, dry_run, submit_delay, retry_limit, retry_backoff, max_workers):
    """读取指定 JSON payload 文件并提交回测。"""
    result = backtest_payload_file(
        payload_file=payload_file,
        output_file=output,
        limit=limit,
        dry_run=dry_run,
        submit_delay=submit_delay,
        retry_limit=retry_limit,
        retry_backoff=retry_backoff,
        max_workers=max_workers,
    )
    if result:
        summary = result.get("summary", {})
        logger.info(
            "pipeline-backtest-json 完成: total=%s, success=%s, failed=%s",
            summary.get("total", 0),
            summary.get("success", 0),
            summary.get("failed", 0),
        )


@cli.command()
@click.option('--dataset', type=str, default='anl14', help='数据集名称 (anl14/mdl110/opt30/fundamental6)')
@click.option('--instrument_type', type=str, default='EQUITY', help='工具类型')
@click.option('--region', type=str, default='USA', help='地区')
@click.option('--universe', type=str, default='TOP3000', help='股票池')
@click.option('--delay', type=int, default=1, help='延迟')
@click.option('--start_template', type=int, default=0, help='起始模板索引（0-10）')
@click.option('--end_template', type=int, default=11, help='结束模板索引（0-10）')
@click.option('--limit_per_template', type=int, default=50, help='每个模板生成的Alpha数量限制')
@click.option('--sharpe_threshold', type=float, default=1.58, help='Sharpe比率阈值')
@click.option('--ir_threshold', type=float, default=0.1, help='信息比率阈值')
@click.option('--order', type=int, default=0, help='Alpha阶数（0-3），0表示使用模板生成，1-3使用工厂函数生成对应阶数')
@click.option('--skip_check', is_flag=True, help='跳过今日提交检查')
@click.option('--no_email', is_flag=True, help='禁用邮件通知')
@click.option('--save_datafields', is_flag=True, default=True, help='保存数据字段到本地')
@click.option('--dry_run', is_flag=True, help='干运行模式，不实际调用API')
@click.option('--max_workers', type=int, default=4, help='回测并发线程数，默认4个')
@click.option('--force_fetch', is_flag=True, help='强制从API拉取数据，忽略本地缓存')
@click.option('--datasets', type=str, default='anl14,mdl110,opt30,fundamental6', 
              help='要获取的数据集列表，逗号分隔，如: anl10,mdl110,opt30,fundamental6')
def full_pipeline(dataset, instrument_type, region, universe, delay, start_template, end_template,
                  limit_per_template, sharpe_threshold, ir_threshold, order, skip_check, no_email, 
                  save_datafields, dry_run, max_workers, force_fetch, datasets):
    """
    完整四步流程：
    
    1. 数据集拉取 - 从WorldQuant API获取数据字段
    2. 模板生成 - 基于数据字段生成Alpha表达式
    3. 回测 - 对生成的Alpha进行回测
    4. 检查结果 - 检查回测结果并生成报告
    """
    log_legacy_command_mapping("full-pipeline")
    import json
    from datetime import datetime
    
    # ========== 初始化 ==========
    logger.info("=" * 60)
    logger.info("           WorldQuant Alpha 完整流水线启动")
    logger.info("=" * 60)
    
    pipeline_start_time = time.time()
    
    # 记录配置信息
    logger.info("【配置参数】")
    logger.info(f"  数据集: {datasets}")
    logger.info(f"  工具类型: {instrument_type}")
    logger.info(f"  地区: {region}")
    logger.info(f"  股票池: {universe}")
    logger.info(f"  延迟: {delay}")
    logger.info(f"  模板范围: {start_template} - {end_template}")
    logger.info(f"  每模板数量: {limit_per_template}")
    logger.info(f"  Sharpe阈值: {sharpe_threshold}")
    logger.info(f"  IR阈值: {ir_threshold}")
    logger.info(f"  Alpha阶数: {order if order is not None else '模板生成'}")
    logger.info(f"  干运行模式: {dry_run}")
    logger.info(f"  回测并发数: {max_workers}")
    logger.info(f"  强制拉取数据: {force_fetch}")
    
    # 检查今天是否已经提交了有效的alpha
    if not skip_check and has_successful_submission_today():
        logger.info("[WARN] 今天已经成功提交了有效的alpha，不再运行")
        return
    
    # 初始化数据库
    logger.info("【初始化】检查数据库连接...")
    if not init_db():
        logger.error("[ERROR] 数据库初始化失败，流水线终止")
        return
    logger.info("[OK] 数据库初始化成功")
    
    # ========== 步骤1: 数据集拉取 ==========
    logger.info("")
    logger.info("=" * 60)
    logger.info("  步骤 1/4: 数据集拉取")
    logger.info("=" * 60)
    
    step1_start = time.time()
    datafields = None
    
    # 解析数据集列表（支持用户自定义）
    required_datasets = [ds.strip() for ds in datasets.split(',') if ds.strip()]
    all_datafields = []
    cached_count = 0
    fetched_count = 0
    
    # 检查本地缓存（除非强制拉取）
    if not dry_run and not force_fetch:
        for ds in required_datasets:
            local_file = f'data/{ds}_{region}_datafields.json'
            if os.path.exists(local_file):
                try:
                    with open(local_file, 'r', encoding='utf-8') as f:
                        ds_fields = json.load(f)
                    if ds_fields and len(ds_fields) > 0:
                        all_datafields.extend(ds_fields)
                        cached_count += 1
                        logger.info(f"[CACHE] {ds}: {len(ds_fields)} 个字段")
                except Exception as e:
                    logger.warning(f"[WARN] 读取 {ds} 缓存失败: {str(e)}")
        
        if cached_count == len(required_datasets):
            logger.info(f"[OK] 所有数据集已从本地缓存加载，共 {len(all_datafields)} 个字段，跳过API拉取")
            datafields = all_datafields
            step1_time = time.time() - step1_start
            logger.info(f"[TIME] 步骤1耗时: {step1_time:.2f}秒")
            goto_step2 = True
        elif cached_count > 0:
            logger.info(f"[INFO] 部分数据集从缓存加载 ({cached_count}/{len(required_datasets)})，将获取剩余数据")
            goto_step2 = False
        else:
            logger.info(f"[INFO] 无本地缓存，将从API获取所有数据集")
            goto_step2 = False
    else:
        if dry_run:
            logger.info("[DRY-RUN] 干运行模式")
        elif force_fetch:
            logger.info(f"[FORCE] 强制从API拉取数据，忽略本地缓存")
        goto_step2 = False
        step1_time = 0  # 初始化，避免后续引用错误
    
    # 如果需要从API拉取（本地不存在或为空）
    if not goto_step2:
        try:
            if dry_run:
                # 干运行模式：使用本地数据或模拟数据
                logger.info("[DRY-RUN] 使用模拟数据")
                
                # 尝试从本地文件加载（任意JSON文件）
                data_dir = 'data'
                if os.path.exists(data_dir):
                    files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
                    if files:
                        latest_file = max(files)
                        with open(os.path.join(data_dir, latest_file), 'r') as f:
                            datafields = json.load(f)
                        logger.info(f"[OK] 从本地文件加载了 {len(datafields)} 个数据字段")
                    else:
                        logger.info("[INFO] 使用默认模拟数据字段")
                        datafields = ["close", "open", "high", "low", "volume", "returns", "vwap", "market_cap"]
                else:
                    logger.info("[INFO] 使用默认模拟数据字段")
                    datafields = ["close", "open", "high", "low", "volume", "returns", "vwap", "market_cap"]
            else:
                # 获取API
                logger.info("正在连接WorldQuant API...")
                api = get_api()
                logger.info("[OK] API连接成功")
                
                # 获取多个数据集的数据字段
                all_datafields = []
                
                for ds in required_datasets:
                    # 跳过已缓存的数据集
                    if not force_fetch:
                        local_file = f'data/{ds}_{region}_datafields.json'
                        if os.path.exists(local_file):
                            try:
                                with open(local_file, 'r', encoding='utf-8') as f:
                                    ds_fields = json.load(f)
                                if ds_fields and len(ds_fields) > 0:
                                    all_datafields.extend(ds_fields)
                                    logger.info(f"[SKIP] {ds}: 使用本地缓存")
                                    continue
                            except:
                                pass
                    
                    # 从API获取
                    logger.info(f"[FETCH] 正在获取数据集: {ds}...")
                    
                    url_template = "https://api.worldquantbrain.com/data-fields?" + \
                                   f"&instrumentType={instrument_type}" + \
                                   f"&region={region}&delay={str(delay)}&universe={universe}&dataset.id={ds}&limit=50" + \
                                   "&offset={x}"
                    
                    try:
                        # 获取总数
                        response = api._retry_operation(
                            lambda: api.session.get(url_template.format(x=0))
                        )
                        
                        if response.status_code != 200:
                            logger.warning(f"[WARN] 获取 {ds} 失败: {response.status_code}")
                            continue
                        
                        count = response.json()['count']
                        logger.info(f"  {ds} 数据字段总数: {count}")
                        
                        # 获取所有数据字段
                        datafields_list = []
                        for x in range(0, count, 50):
                            datafields_response = api._retry_operation(
                                lambda: api.session.get(url_template.format(x=x))
                            )
                            
                            if datafields_response.status_code == 200:
                                datafields_list.extend(datafields_response.json()['results'])
                            else:
                                logger.warning(f"  获取 {ds} 偏移量 {x} 失败")
                            
                            # 增加延迟
                            time.sleep(0.5)
                        
                        # 处理数据字段
                        import pandas as pd
                        df = pd.DataFrame(datafields_list)
                        if not df.empty and 'type' in df.columns:
                            matrix_fields = df[df['type'] == "MATRIX"]['id'].values.tolist()
                            all_datafields.extend(matrix_fields)
                            logger.info(f"  [OK] {ds}: 获取 {len(matrix_fields)} 个MATRIX字段")
                        
                        # 保存到文件
                        if save_datafields and datafields_list:
                            os.makedirs('data', exist_ok=True)
                            filename = f'data/{ds}_{region}_datafields.json'
                            with open(filename, "w") as f:
                                json.dump(matrix_fields, f)
                            logger.info(f"  [SAVE] {ds} 已保存到: {filename}")
                            
                    except Exception as e:
                        logger.error(f"[ERROR] 获取 {ds} 失败: {str(e)}")
                
                datafields = all_datafields
                logger.info(f"[OK] 总共获取 {len(datafields)} 个数据字段")
                
                if not datafields:
                    logger.warning("[WARN] 未获取到任何数据字段，将使用默认数据")
                    datafields = fetch_fundamental_data(dataset, instrument_type, region, universe, delay)
                
                step1_time = time.time() - step1_start
                logger.info(f"[TIME] 步骤1耗时: {step1_time:.2f}秒")
                
        except Exception as e:
            logger.error(f"[ERROR] 数据集拉取失败: {str(e)}")
            logger.warning("尝试使用默认数据字段...")
            datafields = fetch_fundamental_data(dataset, instrument_type, region, universe, delay)
            if not datafields:
                logger.error("[ERROR] 无法获取数据字段，流水线终止")
                return
    
    # ========== 步骤2: 模板生成 ==========
    logger.info("")
    logger.info("=" * 60)
    logger.info("  步骤 2/4: 模板生成")
    logger.info("=" * 60)
    
    step2_start = time.time()
    
    try:
        # 创建默认模板
        logger.info("正在创建Alpha模板...")
        templates = create_default_templates()
        logger.info(f"[OK] 创建了 {len(templates)} 个Alpha模板")
        
        # 验证模板范围
        if start_template < 0 or start_template >= len(templates):
            logger.error(f"[ERROR] 无效的起始模板索引: {start_template}")
            return
        if end_template < 0 or end_template >= len(templates):
            end_template = len(templates) - 1
            logger.warning(f"[WARN] 调整结束模板索引为: {end_template}")
        
        # 批量生成Alpha
        logger.info(f"开始批量生成Alpha（模板 {start_template} 到 {end_template}）...")
        template_name, simulation_data_list = batch_generate_alphas(
            start_template=start_template,
            end_template=end_template + 1,  # +1 因为 range 是左闭右开的
            limit=limit_per_template,
            datafields=datafields,
            order=order
        )
        
        if not simulation_data_list:
            logger.warning("[WARN] 没有生成新的Alpha，流水线终止")
            return
        
        step2_time = time.time() - step2_start
        logger.info(f"[OK] 生成了 {len(simulation_data_list)} 个Alpha表达式")
        logger.info(f"[TIME] 步骤2耗时: {step2_time:.2f}秒")
        
        # 显示前5个生成的表达式
        logger.info("【生成的Alpha示例】")
        for i, data in enumerate(simulation_data_list[:5]):
            expr = data.get('regular', 'unknown')
            logger.info(f"  {i+1}. {expr[:80]}..." if len(expr) > 80 else f"  {i+1}. {expr}")
        
    except Exception as e:
        logger.error(f"[ERROR] 模板生成失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return
    
    # ========== 步骤3: 回测 ==========
    logger.info("")
    logger.info("=" * 60)
    logger.info("  步骤 3/4: 回测")
    logger.info("=" * 60)
    
    step3_start = time.time()
    backtest_results = None
    
    try:
        if dry_run:
            # 干运行模式：模拟回测结果
            logger.info("[DRY-RUN] 干运行模式：模拟回测结果")
            backtest_results = {
                'success': True,
                'total_processed': len(simulation_data_list),
                'success_count': len(simulation_data_list),
                'fail_count': 0,
                'good_alpha_count': min(5, len(simulation_data_list)),
                'results': []
            }
            logger.info(f"[OK] 模拟回测完成")
            logger.info(f"  总处理: {backtest_results['total_processed']}")
            logger.info(f"  成功: {backtest_results['success_count']}")
            logger.info(f"  优质Alpha: {backtest_results['good_alpha_count']}")
        else:
            logger.info(f"开始对 {len(simulation_data_list)} 个Alpha进行回测...")
            logger.info(f"Sharpe阈值: {sharpe_threshold}, IR阈值: {ir_threshold}")
            
            backtest_results = run_backtests(
                from_db=False,
                simulation_data_list=simulation_data_list,
                limit=None,
                ir_threshold=ir_threshold,
                sharpe_threshold=sharpe_threshold,
                max_workers=max_workers
            )
            
            if backtest_results:
                logger.info(f"[OK] 回测完成")
                logger.info(f"  总处理: {backtest_results.get('total_processed', 0)}")
                logger.info(f"  成功: {backtest_results.get('success_count', 0)}")
                logger.info(f"  失败: {backtest_results.get('fail_count', 0)}")
                logger.info(f"  优质Alpha: {backtest_results.get('good_alpha_count', 0)}")
            else:
                logger.warning("[WARN] 回测返回空结果")
        
        step3_time = time.time() - step3_start
        logger.info(f"[TIME] 步骤3耗时: {step3_time:.2f}秒")
        
    except Exception as e:
        logger.error(f"[ERROR] 回测失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    
    # ========== 步骤4: 检查结果 ==========
    logger.info("")
    logger.info("=" * 60)
    logger.info("  步骤 4/4: 检查结果与生成报告")
    logger.info("=" * 60)
    
    step4_start = time.time()
    
    try:
        # 分析回测结果
        logger.info("正在分析回测结果...")
        good_alphas = get_good_alphas(ir_threshold=ir_threshold, limit=1000)
        
        if good_alphas:
            logger.info(f"[OK] 找到 {len(good_alphas)} 个IR大于{ir_threshold}的优质Alpha")
            
            # 统计信息
            total_sharpe = sum(r.sharpe for _, r in good_alphas if r.sharpe)
            total_fitness = sum(r.fitness for _, r in good_alphas if r.fitness)
            avg_sharpe = total_sharpe / len(good_alphas) if good_alphas else 0
            avg_fitness = total_fitness / len(good_alphas) if good_alphas else 0
            
            logger.info("【优质Alpha统计】")
            logger.info(f"  平均Sharpe: {avg_sharpe:.4f}")
            logger.info(f"  平均Fitness: {avg_fitness:.4f}")
            
            # 显示前10个优质Alpha
            logger.info("【Top 10 优质Alpha】")
            for i, (alpha, result) in enumerate(good_alphas[:10], 1):
                logger.info(f"  {i}. Sharpe={result.sharpe:.4f}, IR={result.ir:.4f}, "
                          f"Turnover={result.turnover:.4f}, Fitness={result.fitness:.4f}")
                logger.info(f"     表达式: {alpha.alpha_expression[:100]}...")
            
            # 导出结果到CSV
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
            
            if results_data:
                df = pd.DataFrame(results_data)
                os.makedirs('results', exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"results/pipeline_good_alphas_{timestamp}.csv"
                df.to_csv(filename, index=False)
                logger.info(f"[SAVE] 优质Alpha结果已保存到: {filename}")
        else:
            logger.info(f"[INFO] 未找到IR大于{ir_threshold}的Alpha")
        
        step4_time = time.time() - step4_start
        logger.info(f"[TIME] 步骤4耗时: {step4_time:.2f}秒")
        
    except Exception as e:
        logger.error(f"[ERROR] 结果检查失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    
    # ========== 流水线总结 ==========
    logger.info("")
    logger.info("=" * 60)
    logger.info("                    流水线执行总结")
    logger.info("=" * 60)
    
    total_time = time.time() - pipeline_start_time
    
    logger.info("【各步骤耗时】")
    logger.info(f"  步骤1 (数据集拉取): {step1_time:.2f}秒")
    logger.info(f"  步骤2 (模板生成):   {step2_time:.2f}秒")
    logger.info(f"  步骤3 (回测):       {step3_time:.2f}秒")
    logger.info(f"  步骤4 (结果检查):   {step4_time:.2f}秒")
    logger.info(f"  总计:              {total_time:.2f}秒 ({total_time/60:.2f}分钟)")
    
    logger.info("【执行结果】")
    logger.info(f"  数据字段数: {len(datafields) if datafields else 0}")
    logger.info(f"  生成Alpha数: {len(simulation_data_list) if simulation_data_list else 0}")
    if backtest_results:
        logger.info(f"  回测成功: {backtest_results.get('success_count', 0)}")
        logger.info(f"  优质Alpha: {backtest_results.get('good_alpha_count', 0)}")
    
    # 发送邮件通知
    if not no_email and backtest_results:
        logger.info("【发送邮件通知】")
        try:
            send_email(backtest_results)
            logger.info("[OK] 邮件发送成功")
        except Exception as e:
            logger.error(f"[ERROR] 邮件发送失败: {str(e)}")
    
    logger.info("")
    logger.info("*** 流水线执行完成 ***")
    
    return backtest_results


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
@click.option('--instrumentType', type=str, default='EQUITY', help='工具类型')
@click.option('--region', type=str, default='USA', help='地区')
@click.option('--universe', type=str, default='TOP3000', help='股票池')
@click.option('--delay', type=int, default=1, help='延迟')
def fetch(dataset, instrumenttype, region, universe, delay):
    """获取数据字段"""
    log_legacy_command_mapping("fetch")
    # 转换为驼峰命名法
    instrumentType = instrumenttype
    logger.info(f"获取 {dataset} 数据字段，instrumentType: {instrumentType}, region: {region}, universe: {universe}, delay: {delay}")
    datafields = fetch_fundamental_data(dataset, instrumentType, region, universe, delay)
    if datafields is not None:
        logger.info(f"成功获取 {len(datafields)} 个数据字段")
    else:
        logger.error("获取数据字段失败")


@cli.group()
def third_order():
    """三阶Alpha生成Pipeline"""
    pass


@third_order.command(name='run')
@click.option('--config', '-c', default=None, help='配置文件名(默认使用third_order_default.yaml)')
@click.option('--from-stage', default=None, help='从指定阶段开始(first_order/backtest_first/filter_first/second_order/...)')
@click.option('--to-stage', default=None, help='执行到指定阶段结束')
@click.option('--force', is_flag=True, help='强制重新运行已完成的阶段')
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
@click.option('--first-order-limit', type=int, default=0, help='第一阶段生成Alpha数量限制，0表示不限制')
@click.option('--first-order-to-second-count', type=int, default=500, help='第一阶段到第二阶段的数量，默认500，0表示不限制')
@click.option('--first-order-to-second-ids', type=str, default='', help='第一阶段到第二阶段的指定Alpha ID（逗号分隔）')
@click.option('--second-order-to-third-count', type=int, default=0, help='第二阶段到第三阶段的数量，0表示不限制')
@click.option('--second-order-to-third-ids', type=str, default='', help='第二阶段到第三阶段的指定Alpha ID（逗号分隔）')
@click.option('--third-order-test-ids', type=str, default='', help='第三阶段测试的指定Alpha ID（逗号分隔）')
@click.option('--dataset', '-d', type=str, default=None, help='数据集ID（如 analyst10, fundamental6）')
@click.option('--region', '-r', type=str, default=None, help='地区（如 USA, EUR, CHN）')
@click.option('--universe', '-u', type=str, default=None, help='股票池（如 TOP3000, TOP2500, TOPCS1600）')
@click.option('--delay', type=int, default=None, help='延迟天数（1 或 0）')
@click.option('--instrument-type', type=str, default=None, help='工具类型（如 EQUITY, FUTURES）')
@click.option('--template-names', type=str, default='', help='模板名称（逗号分隔，如 "行业中性化残差动量,分析师预期修正陡度"）')
@click.option('--operations', type=str, default='', help='操作符列表（逗号分隔，如 "ts_rank,ts_zscore,ts_delta"）')
@click.option('--time-windows', type=str, default='', help='时间窗口（逗号分隔，如 "5,22,66,120"）')
def third_order_run(config, from_stage, to_stage, force, state_file,
                    first_order_limit, first_order_to_second_count,
                    first_order_to_second_ids, second_order_to_third_count,
                    second_order_to_third_ids, third_order_test_ids,
                    dataset, region, universe, delay, instrument_type,
                    template_names, operations, time_windows):
    """运行三阶Alpha生成Pipeline
    
    示例:
    
    \b
    # 使用指定数据集和地区
    python -m worldquant_alpha.main third-order run --dataset analyst10 --region EUR --universe TOPCS1600
    
    \b
    # 指定模板
    python -m worldquant_alpha.main third-order run --dataset analyst10 --template-names "行业中性化残差动量,分析师预期修正陡度"
    
    \b
    # 指定操作符和时间窗口
    python -m worldquant_alpha.main third-order run --dataset analyst10 --operations "ts_rank,ts_zscore,ts_delta" --time-windows "5,22,66"
    
    \b
    # 限制第一阶段生成300个Alpha
    python -m worldquant_alpha.main third-order run --first-order-limit 300
    
    \b
    # 完整示例：使用 analyst10 数据集，EUR 地区，生成后取200个进二阶
    python -m worldquant_alpha.main third-order run --dataset analyst10 --region EUR --universe TOPCS1600 --delay 1 --first-order-limit 500 --first-order-to-second-count 200
    """
    try:
        # 解析ID列表
        first_ids = [int(x.strip()) for x in first_order_to_second_ids.split(',') if x.strip()] if first_order_to_second_ids else []
        second_ids = [int(x.strip()) for x in second_order_to_third_ids.split(',') if x.strip()] if second_order_to_third_ids else []
        third_ids = [int(x.strip()) for x in third_order_test_ids.split(',') if x.strip()] if third_order_test_ids else []
        
        # 解析模板名称列表
        template_name_list = [x.strip() for x in template_names.split(',') if x.strip()] if template_names else None
        
        # 解析操作符列表
        operations_list = [x.strip() for x in operations.split(',') if x.strip()] if operations else None
        
        # 解析时间窗口列表
        time_windows_list = [int(x.strip()) for x in time_windows.split(',') if x.strip()] if time_windows else None
        
        logger.info("启动三阶Alpha生成Pipeline...")
        logger.info(f"阶段控制参数: 第一阶段限制={first_order_limit}, "
                   f"第一到第二数量={first_order_to_second_count}, "
                   f"第二到第三数量={second_order_to_third_count}")

        engine = PipelineEngine(
            config_path=config,
            state_file=state_file,
            first_order_limit=first_order_limit,
            first_order_to_second_count=first_order_to_second_count,
            first_order_to_second_ids=first_ids,
            second_order_to_third_count=second_order_to_third_count,
            second_order_to_third_ids=second_ids,
            third_order_test_ids=third_ids,
            dataset=dataset,
            region=region,
            universe=universe,
            delay=delay,
            instrument_type=instrument_type,
            template_names=template_name_list,
            operations=operations_list,
            time_windows=time_windows_list
        )

        engine.run(
            start_stage=from_stage,
            end_stage=to_stage,
            force=force
        )

        logger.info("Pipeline执行完成!")

    except Exception as e:
        logger.exception("Pipeline执行失败")
        raise click.ClickException(str(e))


@third_order.command(name='resume')
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
def third_order_resume(state_file):
    """从上次中断处恢复Pipeline执行"""
    try:
        logger.info("恢复Pipeline执行...")

        engine = PipelineEngine(state_file=state_file)
        engine.resume()

        logger.info("Pipeline恢复执行完成!")

    except Exception as e:
        logger.exception("Pipeline恢复失败")
        raise click.ClickException(str(e))


@third_order.command(name='status')
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
def third_order_status(state_file):
    """查看Pipeline执行状态"""
    try:
        engine = PipelineEngine(state_file=state_file)
        summary = engine.status()
        click.echo(summary)

    except Exception as e:
        logger.exception("获取状态失败")
        raise click.ClickException(str(e))


@third_order.command(name='reset')
@click.option('--state-file', default='.pipeline_state.json', help='状态文件路径')
@click.confirmation_option(prompt='确定要重置Pipeline状态吗?')
def third_order_reset(state_file):
    """重置Pipeline状态"""
    try:
        engine = PipelineEngine(state_file=state_file)
        engine.reset()
        click.echo("Pipeline状态已重置")

    except Exception as e:
        logger.exception("重置失败")
        raise click.ClickException(str(e))


@third_order.command(name='validate')
@click.option('--config', '-c', required=True, help='配置文件路径')
def third_order_validate(config):
    """验证Pipeline配置文件"""
    try:
        loader = ConfigLoader()
        cfg = loader.load(config)

        click.echo(f"配置名称: {cfg.name}")
        click.echo(f"配置版本: {cfg.version}")
        click.echo(f"地区: {cfg.settings.region}")
        click.echo(f"Universe: {cfg.settings.universe}")
        click.echo(f"数据集: {', '.join(cfg.data.datasets)}")
        click.echo("\n阶段配置:")
        click.echo(f"  一阶生成: {'启用' if cfg.stages.first_order.enabled else '禁用'}")
        click.echo(f"  二阶生成: {'启用' if cfg.stages.second_order.enabled else '禁用'}")
        click.echo(f"  三阶生成: {'启用' if cfg.stages.third_order.enabled else '禁用'}")
        click.echo(f"\n回测模式: {cfg.backtest.mode.value}")
        click.echo(f"最大并发: {cfg.backtest.max_workers}")
        click.echo("\n配置验证通过!")

    except Exception as e:
        logger.exception("配置验证失败")
        raise click.ClickException(f"配置错误: {e}")


@third_order.command(name='list-configs')
def third_order_list_configs():
    """列出可用配置文件"""
    try:
        loader = ConfigLoader()
        configs = loader.list_configs()

        if configs:
            click.echo("可用配置文件:")
            for cfg in configs:
                click.echo(f"  - {cfg}")
        else:
            click.echo("未找到配置文件")

    except Exception as e:
        logger.exception("列出配置失败")
        raise click.ClickException(str(e))


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="WorldQuant Alpha策略生成和回测工具")
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 初始化命令
    init_parser = subparsers.add_parser('init', help='初始化系统')

    # 获取数据命令
    fetch_parser = subparsers.add_parser('fetch', help='获取基本面数据字段')
    fetch_parser.add_argument('--dataset', type=str, default='fundamental6', help='数据集名称')
    fetch_parser.add_argument('--instrumentType', type=str, default='EQUITY', help='工具类型')
    fetch_parser.add_argument('--region', type=str, default='USA', help='地区')
    fetch_parser.add_argument('--universe', type=str, default='TOP3000', help='股票池')
    fetch_parser.add_argument('--delay', type=int, default=1, help='延迟')

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
        datafields = fetch_fundamental_data(
            template_name=args.dataset,
            instrumentType=args.instrumentType,
            region=args.region,
            universe=args.universe,
            delay=args.delay
        )
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
