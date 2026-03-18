"""
回测管理器模块

提供并发回测执行、速率限制和结果收集功能。
"""

import time
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """回测结果"""
    alpha_expression: str
    success: bool
    alpha_id: Optional[str] = None
    sharpe: Optional[float] = None
    fitness: Optional[float] = None
    turnover: Optional[float] = None
    color: Optional[str] = None
    error: Optional[str] = None
    raw_result: Optional[Dict[str, Any]] = None


class BacktestManager:
    """并发回测管理器"""

    def __init__(self, max_workers: int = 4, batch_size: int = 10, rate_limit_delay: float = 1.0):
        """
        初始化回测管理器

        参数:
        - max_workers: 最大并发数
        - batch_size: 批处理大小
        - rate_limit_delay: 速率限制延迟(秒)
        """
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.rate_limit_delay = rate_limit_delay
        self.results: List[BacktestResult] = []

    def run(self, alphas: List[str], settings: Dict[str, Any],
            client=None, mode: str = "concurrent",
            result_callback=None) -> List[BacktestResult]:
        """
        执行回测

        参数:
        - alphas: Alpha表达式列表
        - settings: 回测设置
        - client: WorldQuantClient实例
        - mode: 执行模式 (concurrent/sequential)
        - result_callback: 结果回调函数，单个结果完成时立即调用，签名为 callback(result: BacktestResult)

        返回:
        - 回测结果列表
        """
        if mode == "concurrent":
            return self._run_concurrent(alphas, settings, client, result_callback)
        else:
            return self._run_sequential(alphas, settings, client, result_callback)

    def _run_concurrent(self, alphas: List[str], settings: Dict[str, Any],
                       client=None, result_callback=None) -> List[BacktestResult]:
        """并发执行回测"""
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_alpha = {
                executor.submit(self._run_single_backtest, alpha, settings, client): alpha
                for alpha in alphas
            }

            for future in as_completed(future_to_alpha):
                alpha = future_to_alpha[future]
                try:
                    result = future.result()
                    results.append(result)

                    # 如果提供了回调，立即触发
                    if result_callback and callable(result_callback):
                        try:
                            result_callback(result)
                        except Exception as cb_err:
                            logger.error(f"回调执行失败: {cb_err}")

                    # 打印进度
                    if len(results) % 10 == 0:
                        logger.info(f"回测进度: {len(results)}/{len(alphas)}")

                except Exception as e:
                    logger.error(f"回测异常: {alpha[:50]}... - {e}")
                    results.append(BacktestResult(
                        alpha_expression=alpha,
                        success=False,
                        error=str(e)
                    ))

        return results

    def _run_sequential(self, alphas: List[str], settings: Dict[str, Any],
                       client=None, result_callback=None) -> List[BacktestResult]:
        """顺序执行回测"""
        results = []

        for i, alpha in enumerate(alphas):
            result = self._run_single_backtest(alpha, settings, client)
            results.append(result)

            # 如果提供了回调，立即触发
            if result_callback and callable(result_callback):
                try:
                    result_callback(result)
                except Exception as cb_err:
                    logger.error(f"回调执行失败: {cb_err}")

            if (i + 1) % 10 == 0:
                logger.info(f"回测进度: {i + 1}/{len(alphas)}")

            # 速率限制
            time.sleep(self.rate_limit_delay)

        return results

    def _run_single_backtest(self, alpha: str, settings: Dict[str, Any],
                            client=None) -> BacktestResult:
        """执行单个回测"""
        try:
            if client is None:
                # 延迟导入避免循环依赖
                try:
                    from wd_lib import WorldQuantClient
                except ImportError:
                    from worldquant_alpha.wd_lib import WorldQuantClient
                client = WorldQuantClient()
                client.login()

            result = client.run_backtest(alpha, settings)

            if result and result.get("alpha_id"):
                return BacktestResult(
                    alpha_expression=alpha,
                    success=True,
                    alpha_id=result.get("alpha_id"),
                    sharpe=result.get("sharpe"),
                    fitness=result.get("fitness"),
                    turnover=result.get("turnover"),
                    color=result.get("color"),
                    raw_result=result
                )
            else:
                return BacktestResult(
                    alpha_expression=alpha,
                    success=False,
                    error="回测失败或返回结果无效"
                )

        except Exception as e:
            logger.error(f"回测失败: {alpha[:50]}... - {e}")
            return BacktestResult(
                alpha_expression=alpha,
                success=False,
                error=str(e)
            )

    def filter_by_threshold(self, results: List[BacktestResult],
                           sharpe_threshold: float = 0.7,
                           fitness_threshold: float = 0.5) -> List[BacktestResult]:
        """
        按阈值筛选回测结果

        参数:
        - results: 回测结果列表
        - sharpe_threshold: Sharpe阈值
        - fitness_threshold: Fitness阈值

        返回:
        - 筛选后的结果列表
        """
        filtered = []
        for r in results:
            if r.success and r.sharpe is not None and r.fitness is not None:
                if abs(r.sharpe) >= sharpe_threshold and abs(r.fitness) >= fitness_threshold:
                    filtered.append(r)

        logger.info(f"阈值筛选: {len(results)} -> {len(filtered)} (sharpe>={sharpe_threshold}, fitness>={fitness_threshold})")
        return filtered
