"""
WorldQuant Brain API回测执行模块
提供Alpha回测执行功能
"""

import time
import json
import logging
import random
from typing import Dict, List, Any, Optional, Union
from urllib.parse import urljoin

from ..auth import get_session, refresh_session
from ..config.constants import API_BASE_URL, DEFAULT_BACKTEST_SETTINGS
from ..utils.retry import with_retry
from ..utils.exceptions import APIError, SimulationError

# 配置日志
logger = logging.getLogger(__name__)


class Backtester:
    """回测器类，提供完整的回测功能"""

    def __init__(self, session=None):
        """
        初始化回测器
        
        参数:
        - session: 会话对象，如果为None则创建新会话
        """
        self.session = session or get_session()
        logger.info("回测器初始化完成")

    def _check_auth_error(self, response):
        """
        检查是否是身份验证错误，如果是则刷新会话
        
        参数:
        - response: 响应对象
        
        返回:
        - 是否为认证错误
        """
        if response.status_code in [401, 403]:  # 认证失败的状态码
            logger.warning("检测到身份验证错误，尝试刷新会话...")
            self.session = refresh_session()
            return True
        return False

    def _make_request(self, method, url, **kwargs):
        """
        发送请求并处理可能的认证错误
        
        参数:
        - method: HTTP方法
        - url: 请求URL
        - kwargs: 请求参数
        
        返回:
        - 响应对象
        """
        retry_count = 0
        max_retries = 2  # 最多重试2次

        while retry_count <= max_retries:
            try:
                if method == 'get':
                    response = self.session.get(url, **kwargs)
                elif method == 'post':
                    response = self.session.post(url, **kwargs)
                elif method == 'patch':
                    response = self.session.patch(url, **kwargs)
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")

                # 如果认证失败且刷新会话成功，则重试
                if self._check_auth_error(response):
                    logger.info("会话已刷新，重试请求...")
                    retry_count += 1
                    continue

                return response

            except Exception as e:
                logger.error(f"请求失败 ({retry_count + 1}/{max_retries + 1}): {str(e)}")
                if retry_count < max_retries:
                    logger.info("尝试刷新会话后重试...")
                    self.session = refresh_session()
                    retry_count += 1
                    time.sleep(2)  # 等待2秒后重试
                else:
                    raise

        raise APIError(f"请求失败，已达到最大重试次数 ({max_retries})")

    @with_retry()
    def check_alpha_status(self, alpha_id):
        """
        检查Alpha的状态并设置颜色
        
        参数:
        - alpha_id: Alpha ID
        
        返回:
        - (成功状态, 颜色值) 元组
        """
        try:
            # 从API模块导入，避免循环导入
            from ..api.alphas import check_alpha_status
            return check_alpha_status(alpha_id, self.session)
        except Exception as e:
            logger.error(f"检查Alpha状态时发生错误: {e}")
            return False, None

    def run_backtest(self, alpha_expression, settings=None, retry=0):
        """
        运行Alpha回测
        
        参数:
        - alpha_expression: Alpha表达式
        - settings: 回测设置
        - retry: 当前重试次数
        
        返回:
        - 回测结果字典，失败时返回None
        """
        if retry > 10:
            logger.error("回测重试已达上限")
            return None

        if settings is None:
            settings = DEFAULT_BACKTEST_SETTINGS.copy()

        simulation_data = {
            "type": "REGULAR",
            "settings": settings,
            "regular": alpha_expression
        }

        logger.info(f"开始对Alpha进行回测: {alpha_expression[:50]}...")

        try:
            # 发送回测请求
            sim_resp = self._make_request(
                'post',
                urljoin(API_BASE_URL, 'simulations'),
                json=simulation_data,
            )

            if not sim_resp.ok:
                logger.error(f"回测请求失败: {sim_resp.status_code} - {sim_resp.text}")
                return None

            # 获取回测进度URL
            sim_progress_url = sim_resp.headers.get('Location')
            if not sim_progress_url:
                logger.error("回测请求没有返回Location头")
                # 重试
                retry = retry + 1
                time.sleep(5)
                return self.run_backtest(alpha_expression, settings, retry)

            logger.info(f"回测请求已提交，进度URL: {sim_progress_url}")

            # 轮询回测进度
            wait_count = 0
            total_wait_time = 0
            while True:
                sim_progress_resp = self._make_request('get', sim_progress_url)
                progress = sim_progress_resp.json().get("progress")
                retry_after_sec = float(sim_progress_resp.headers.get("Retry-After", 0))

                if retry_after_sec == 0:  # 回测完成
                    break

                # 如果二十分钟都没回测完，就进行下一个
                if total_wait_time > 1200:  # 20分钟都没回测完，就中止回测
                    logger.warning("回测超时，中止回测...")
                    # 随机暂停十分钟到一小时
                    random_wait_time = random.randint(600, 3600)  # 10分钟到一小时
                    logger.info(f"回测超时，随机暂停 {random_wait_time / 60:.1f} 分钟...")
                    time.sleep(random_wait_time)
                    break

                wait_count += 1
                total_wait_time += retry_after_sec

                # 只在第一次和之后每5次才打印日志
                if wait_count == 1 or wait_count % 5 == 0:
                    logger.info(
                        f"回测进行中，进度：{progress}, 已等待 {total_wait_time:.1f} 秒，当前轮询次数: {wait_count}")

                time.sleep(retry_after_sec)

            # 解析回测结果
            result_data = sim_progress_resp.json()
            alpha_id = result_data.get("alpha")  # WorldQuant平台返回的Alpha ID

            if not alpha_id:
                logger.error("回测结果中没有Alpha ID")
                return None

            logger.info(f"回测完成，获得Alpha ID: {alpha_id}")

            # 获取详细结果
            alpha_detail_url = urljoin(API_BASE_URL, f"alphas/{alpha_id}")
            alpha_detail_resp = self._make_request('get', alpha_detail_url)

            if not alpha_detail_resp.ok:
                logger.error(f"获取Alpha详情失败: {alpha_detail_resp.status_code}")
                return {
                    'alpha_id': alpha_id,
                    'status': 'UNSUBMITTED',
                    'expression': alpha_expression,
                    'performance': {},
                    'details': None
                }

            details = alpha_detail_resp.json()
            logger.info(f"获取到的Alpha详情: {json.dumps(details)[:300]}...")

            alpha_is = details.get('is', {})

            # 检查Alpha是否有效
            is_valid = details.get('status') == 'ACCEPTED'

            # 检查Sharpe比率是否大于等于1.5且Fitness >= 1.0
            # 确保 sharpe 和 fitness 是数字类型
            try:
                sharpe = float(alpha_is.get('sharpe', 0)) if alpha_is.get('sharpe') is not None else 0
                fitness = float(alpha_is.get('fitness', 0)) if alpha_is.get('fitness') is not None else 0
            except (ValueError, TypeError):
                sharpe = 0
                fitness = 0
            
            color = None
            if sharpe >= 1.5 and fitness >= 1.0:
                # 检查Alpha状态并设置颜色
                _, color = self.check_alpha_status(alpha_id)
            else:
                logger.info(f"Alpha {alpha_id} Sharpe {sharpe} < 1.5 或 Fitness {fitness} < 1.0，不进行颜色设置")

            # 返回格式化的结果
            result = {
                'alpha_id': alpha_id,
                'expression': alpha_expression,
                'status': details.get('status', 'UNSUBMITTED'),
                'author': details.get('author'),
                'date_created': details.get('dateCreated'),
                'date_modified': details.get('dateModified'),
                'sharpe': alpha_is.get('sharpe'),
                'turnover': alpha_is.get('turnover'),
                'fitness': alpha_is.get('fitness'),
                'pnl': alpha_is.get('pnl'),
                'returns': alpha_is.get('returns'),
                'drawdown': alpha_is.get('drawdown'),
                'margin': alpha_is.get('margin'),
                'long_count': alpha_is.get('longCount'),
                'short_count': alpha_is.get('shortCount'),
                'start_date': alpha_is.get('startDate'),
                'checks': alpha_is.get('checks', []),
                'grade': details.get('grade'),
                'color': color,  # 添加颜色信息到结果中
                'settings': settings  # 保存回测设置
            }

            logger.info(f"处理完成，Alpha状态: {result['status']}, 颜色: {color}")
            return result

        except Exception as e:
            logger.error(f"回测过程中出错: {e}")
            return None

    def run_batch_backtest(self, alpha_expressions, settings=None, max_parallel=5):
        """
        批量运行Alpha回测
        
        参数:
        - alpha_expressions: Alpha表达式列表
        - settings: 回测设置
        - max_parallel: 最大并行回测数量
        
        返回:
        - 回测结果字典列表
        """
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor
        
        if settings is None:
            settings = DEFAULT_BACKTEST_SETTINGS.copy()
            
        logger.info(f"开始批量回测，共 {len(alpha_expressions)} 个Alpha，最大并行数 {max_parallel}")
        
        results = []
        
        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            future_to_alpha = {
                executor.submit(self.run_backtest, alpha, settings): alpha
                for alpha in alpha_expressions
            }
            
            for future in concurrent.futures.as_completed(future_to_alpha):
                alpha = future_to_alpha[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                    else:
                        logger.error(f"回测失败: {alpha[:50]}...")
                except Exception as e:
                    logger.error(f"回测执行异常: {str(e)}")
                    
        logger.info(f"批量回测完成，成功 {len(results)}/{len(alpha_expressions)}")
        return results


def run_backtest(alpha_expression, settings=None, session=None):
    """
    运行单个Alpha回测的便捷函数
    
    参数:
    - alpha_expression: Alpha表达式
    - settings: 回测设置
    - session: 会话对象，如果为None则使用当前会话
    
    返回:
    - 回测结果字典，失败时返回None
    """
    backtester = Backtester(session)
    return backtester.run_backtest(alpha_expression, settings) 