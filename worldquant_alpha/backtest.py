import logging
import time
import random
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from dotenv import load_dotenv
import os
import sys
import threading

# 加载环境变量
load_dotenv()

# 获取logger，但不重新配置（避免覆盖main.py的日志配置）
logger = logging.getLogger(__name__)

# 其他导入
from wd_lib_wrapper import get_api
from database import get_session, Alpha, update_alpha_status, save_alpha_result, update_alpha_submission_time, update_alpha_sharpe
from notification import send_alpha_test_notification, send_batch_completion_notification, send_error_notification
from graceful_shutdown import is_shutting_down, wait_if_shutting_down, add_cleanup_callback

logger.info("回测模块已加载")


class Backtester:
    """回测器类，提供完整的回测功能"""

    def __init__(self, max_retry=3, batch_size=1, notify=False, sharpe_threshold=1.6):
        # 初始化API
        self.api = get_api()
        self.max_retry = max_retry
        self.batch_size = batch_size
        self.notify = notify
        self.sharpe_threshold = sharpe_threshold
        logger.info(f"回测器初始化成功，Sharpe阈值: {sharpe_threshold}")

    def run_backtest(self, alpha_expression, settings=None, retry=0):
        """运行Alpha回测"""
        if retry > self.max_retry:
            logger.error("回测重试已达上限")
            return None

        # 执行回测
        result = self.api.run_backtest(alpha_expression, settings)
        
        # 如果失败且未超过重试次数，则重试
        if result is None and retry < self.max_retry:
            logger.warning(f"回测失败，将在5秒后进行第{retry+1}次重试...")
            time.sleep(5)
            return self.run_backtest(alpha_expression, settings, retry + 1)
            
        return result

    def backtest_from_database(self, limit=None, template_name=None):
        """从数据库批量获取Alpha进行回测"""
        logger.info(f"开始从数据库获取Alpha进行回测，模板名称：{template_name}...")
        results = []

        try:
            # 获取待回测的Alpha
            session = get_session()
            query = session.query(Alpha).filter_by(is_tested=False).order_by(Alpha.created_at.desc())

            # 按模板名称筛选
            if template_name:
                query = query.filter(Alpha.template_name == template_name)

            if limit:
                query = query.limit(limit)

            alphas = query.all()
            session.close()

            # 打乱alphas
            random.shuffle(alphas)

            if not alphas:
                logger.info("没有待回测的Alpha")
                return []

            total_alphas = len(alphas)
            logger.info(f"从数据库获取了 {total_alphas} 个待回测的Alpha")

            # 使用纯日志模式
            completed = 0
            success_count = 0
            fail_count = 0
            good_alpha_count = 0

            def process_alpha(alpha):
                nonlocal completed, success_count, fail_count, good_alpha_count
                alpha_id = alpha.id
                alpha_expression = alpha.alpha_expression
                settings = alpha.settings if hasattr(alpha, 'settings') and alpha.settings else None

                # 更新状态为running
                update_alpha_status(alpha_id, 'running')
                logger.info(f"开始对 Alpha ID: {alpha_id} 进行回测...")

                # 进行回测
                result = self.run_backtest(alpha_expression, settings)

                if result:
                    success_count += 1
                    # 提取新的回测结果格式中的数据
                    is_data = result.get('is', {})

                    # 直接从顶层或从性能数据中获取指标
                    processed_result = {
                        'id': alpha_id,
                        'platform_id': result.get('id'),
                        'status': 'valid' if result.get('status') != 'UNSUBMITTED' else 'invalid',
                        'expression': alpha_expression,
                        'sharpe': result.get('sharpe'),
                        'turnover': result.get('turnover'),
                        'fitness': result.get('fitness'),
                        'pnl': result.get('pnl'),
                        'returns': result.get('returns'),
                        'drawdown': result.get('drawdown'),
                        'grade': result.get('grade'),
                        'details': result,
                        "is_good_alpha": True if result.get("color") == "GREEN" else False,
                    }

                    if processed_result['is_good_alpha']:
                        good_alpha_count += 1

                    results.append(processed_result)
                    
                    # 检查Sharpe比率是否达到阈值
                    sharpe = processed_result['sharpe']
                    if sharpe is not None and sharpe >= self.sharpe_threshold:
                        # 保存回测结果到数据库
                        logger.info(f"准备保存Alpha结果到数据库，Alpha ID: {alpha_id}, Sharpe: {sharpe} (达到阈值 {self.sharpe_threshold})")
                        result_id = save_alpha_result(
                            alpha_id=alpha_id,
                            platform_id=processed_result['platform_id'],
                            sharpe=processed_result['sharpe'],
                            turnover=processed_result['turnover'],
                            fitness=processed_result['fitness'],
                            raw_result=processed_result['details']
                        )
                        if result_id:
                            logger.info(f"Alpha结果成功保存到数据库，结果ID: {result_id}")
                            # 更新Alpha表中的Sharpe比率
                            update_alpha_sharpe(alpha_id, processed_result['sharpe'])
                        else:
                            logger.error(f"保存Alpha结果到数据库失败，Alpha ID: {alpha_id}")
                    else:
                        logger.info(f"Alpha ID: {alpha_id} 的Sharpe比率 {sharpe} 未达到阈值 {self.sharpe_threshold}，不保存到数据库")

                    # if self.notify:
                    #     send_alpha_test_notification(alpha_id, alpha_expression, processed_result)

                    # 更新状态为completed（无论是否保存结果）
                    update_alpha_status(alpha_id, 'completed')

                    # 避免频繁请求
                    # time.sleep(3)
                else:
                    fail_count += 1
                    update_alpha_status(alpha_id, 'failed')

                completed += 1
                # 每10个打印一次进度
                if completed % 10 == 0 or completed == total_alphas:
                    logger.info(f"进度: [{completed}/{total_alphas}] 成功:{success_count} 失败:{fail_count} 优质:{good_alpha_count}")

                return result

            # 使用ThreadPoolExecutor进行并发处理，最多同时运行指定数量的线程
            with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
                future_to_alpha = {executor.submit(process_alpha, alpha): alpha for alpha in alphas}
                for future in concurrent.futures.as_completed(future_to_alpha):
                    future.result()  # 只是为了捕获异常，结果已经在process_alpha中处理了
            
            # 发送批量完成通知
            if self.notify:
                send_batch_completion_notification(total_alphas, success_count, good_alpha_count)
                
            return {
                'success': True,
                'total_processed': total_alphas,
                'success_count': success_count,
                'fail_count': fail_count,
                'good_alpha_count': good_alpha_count,
                'results': results
            }

        except Exception as e:
            logger.error(f"批量回测失败: {str(e)}")
            if self.notify:
                send_error_notification(f"批量回测失败: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def backtest_simulation_data_list(self, simulation_data_list, ir_threshold=0.1, max_workers=4):
        """
        运行多个模拟请求数据（支持多线程并发）
        
        参数:
        - simulation_data_list: 模拟请求数据列表
        - ir_threshold: IR阈值
        - max_workers: 并发线程数，默认4个
        """
        total_count = len(simulation_data_list)
        
        # 使用线程安全的计数器和锁
        counters = {
            'success': 0,
            'fail': 0,
            'good': 0,
            'completed': 0
        }
        counters_lock = threading.Lock()
        results_lock = threading.Lock()
        results = []
        
        logger.info(f"[THREAD-POOL] 开始对 {total_count} 个Alpha进行回测，并发数: {max_workers}")

        def process_single_backtest(args):
            """处理单个回测任务"""
            idx, data = args
            thread_name = threading.current_thread().name
            
            # 检查是否收到关闭信号
            if is_shutting_down():
                logger.info(f"[{thread_name}] 检测到关闭信号，跳过")
                return None

            alpha_expression = data.get('regular')
            settings = data.get('settings')
            
            # 记录开始时间
            start_time = time.time()
            
            try:
                # 执行回测
                logger.info(f"[{thread_name}] 开始回测 [{idx+1}/{total_count}]: {alpha_expression[:60]}...")
                result = self.run_backtest(alpha_expression, settings)
                elapsed = time.time() - start_time
                
                with counters_lock:
                    counters['completed'] += 1
                    current = counters['completed']
                
                if result:
                    with counters_lock:
                        counters['success'] += 1
                    
                    # 检查是否是优质Alpha
                    is_data = result.get('is', {})
                    sharpe = is_data.get('sharpe', 0)
                    fitness = is_data.get('fitness', 0)
                    turnover = is_data.get('turnover', 0)
                    
                    is_good = result.get('color') == 'GREEN'
                    if is_good:
                        with counters_lock:
                            counters['good'] += 1
                        logger.info(f"[{thread_name}] [OK] 回测成功 - Sharpe: {sharpe:.2f}, Fitness: {fitness:.2f}, "
                                   f"Turnover: {turnover:.2f}, 耗时: {elapsed:.1f}s")

                    # 只添加达到Sharpe阈值的结果
                    if sharpe >= self.sharpe_threshold:
                        with results_lock:
                            results.append(result)
                    else:
                        logger.info(f"[{thread_name}] [SKIP] Sharpe {sharpe:.2f} < 阈值 {self.sharpe_threshold}")
                else:
                    with counters_lock:
                        counters['fail'] += 1
                    logger.warning(f"[{thread_name}] [FAIL] 回测失败")
                
                # 每5个打印一次进度汇总
                if current % 5 == 0 or current == total_count:
                    with counters_lock:
                        logger.info(f"[PROGRESS] [{current}/{total_count}] "
                                   f"成功:{counters['success']} "
                                   f"失败:{counters['fail']} "
                                   f"优质:{counters['good']}")
                
                # 避免频繁请求 - 每个任务完成后延时
                time.sleep(3)
                
                return result
                
            except Exception as e:
                with counters_lock:
                    counters['fail'] += 1
                    counters['completed'] += 1
                logger.error(f"[{thread_name}] [ERROR] 回测异常: {str(e)}")
                return None

        # 使用线程池执行回测
        completed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Backtest") as executor:
            # 提交所有任务
            future_to_idx = {
                executor.submit(process_single_backtest, (idx, data)): idx 
                for idx, data in enumerate(simulation_data_list)
            }
            
            # 处理完成的任务
            for future in as_completed(future_to_idx):
                if is_shutting_down():
                    logger.info("[SHUTDOWN] 检测到关闭信号，取消未完成任务")
                    # 取消剩余任务
                    for f in future_to_idx:
                        if not f.done():
                            f.cancel()
                    break
                
                try:
                    result = future.result()
                    completed_count += 1
                except Exception as e:
                    logger.error(f"[ERROR] 线程执行异常: {str(e)}")

        # 汇总结果
        logger.info(f"[COMPLETE] 回测完成，总计:{total_count} 成功:{counters['success']} "
                   f"失败:{counters['fail']} 优质:{counters['good']}")
        
        # 发送批量完成通知
        if self.notify:
            send_batch_completion_notification(total_count, counters['success'], counters['good'], ir_threshold)
        
        return {
            'success': True,
            'total_processed': total_count,
            'success_count': counters['success'],
            'fail_count': counters['fail'],
            'good_alpha_count': counters['good'],
            'results': results
        }


def run_backtest(alphas=None, from_db=False, limit=10, sharpe_threshold=0):
    """运行回测"""
    logger.info(f"开始回测，Sharpe阈值: {sharpe_threshold}...")

    backtester = Backtester(sharpe_threshold=sharpe_threshold)
    
    try:
        if from_db:
            # 使用Backtester类的方法从数据库获取Alpha进行回测
            return backtester.backtest_from_database(limit)
        elif alphas:
            # 逐个处理传入的Alpha
            results = []
            for alpha in alphas:
                if isinstance(alpha, dict):
                    alpha_id = alpha.get('id')
                    alpha_expression = alpha.get('alpha_expression')
                    settings = alpha.get('settings')

                    result = backtester.run_backtest(alpha_expression, settings)
                    if result:
                        results.append(result)
            return results

    except Exception as e:
        logger.error(f"回测过程中出错: {e}")
        return []


def backtest_from_db(limit=10, sharpe_threshold=0):
    """从数据库获取Alpha并运行回测"""
    return run_backtest(from_db=True, limit=limit, sharpe_threshold=sharpe_threshold)


if __name__ == "__main__":
    backtest_from_db()
