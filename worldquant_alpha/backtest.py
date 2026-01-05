import logging
import time
import random
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

from dotenv import load_dotenv
import os
from wd_lib_wrapper import get_api
from database import get_session, Alpha, update_alpha_status, save_alpha_result, update_alpha_submission_time, update_alpha_sharpe
from notification import send_alpha_test_notification, send_batch_completion_notification, send_error_notification

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

    def backtest_from_database(self, limit=None):
        """从数据库批量获取Alpha进行回测"""
        logger.info("开始从数据库获取Alpha进行回测...")
        results = []

        try:
            # 获取待回测的Alpha
            session = get_session()
            query = session.query(Alpha).filter_by(is_tested=False).order_by(Alpha.created_at.desc())

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

            # 创建进度条
            pbar = tqdm(total=total_alphas, desc="回测进度", unit="alpha")
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
                logger.info(f"开始对 Alpha ID: {alpha_id} ({alpha_expression[:50]}) 进行回测...")

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
                pbar.update(1)
                pbar.set_postfix({
                    '已完成': completed,
                    '成功': success_count,
                    '失败': fail_count,
                    '优质Alpha': good_alpha_count
                })

                return result

            # 使用ThreadPoolExecutor进行并发处理，最多同时运行指定数量的线程
            with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
                future_to_alpha = {executor.submit(process_alpha, alpha): alpha for alpha in alphas}
                for future in concurrent.futures.as_completed(future_to_alpha):
                    future.result()  # 只是为了捕获异常，结果已经在process_alpha中处理了

            pbar.close()
            
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

    def backtest_simulation_data_list(self, simulation_data_list, ir_threshold=0.1):
        """运行多个模拟请求数据"""
        total_count = len(simulation_data_list)
        success_count = 0
        fail_count = 0
        good_alpha_count = 0
        results = []
        
        logger.info(f"开始对 {total_count} 个模拟请求数据进行回测")
        
        # 创建进度条
        pbar = tqdm(total=total_count, desc="回测进度", unit="alpha")
        
        for data in simulation_data_list:
            alpha_expression = data.get('regular')
            settings = data.get('settings')
            
            # 执行回测
            result = self.run_backtest(alpha_expression, settings)
            
            if result:
                success_count += 1
                # 检查是否是优质Alpha
                is_data = result.get('is', {})
                sharpe = is_data.get('sharpe', 0)
                if result.get('color') == 'GREEN':
                    good_alpha_count += 1
                
                # 只添加达到Sharpe阈值的结果
                if sharpe >= self.sharpe_threshold:
                    results.append(result)
                else:
                    logger.info(f"模拟数据回测的Alpha Sharpe比率 {sharpe} 未达到阈值 {self.sharpe_threshold}，不保存结果")
            else:
                fail_count += 1
            
            pbar.update(1)
            pbar.set_postfix({
                '成功': success_count,
                '失败': fail_count,
                '优质Alpha': good_alpha_count
            })
            
            # 避免频繁请求
            time.sleep(3)
        
        pbar.close()
        
        # 发送批量完成通知
        if self.notify:
            send_batch_completion_notification(total_count, success_count, good_alpha_count, ir_threshold)
        
        return {
            'success': True,
            'total_processed': total_count,
            'success_count': success_count,
            'fail_count': fail_count,
            'good_alpha_count': good_alpha_count,
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
