"""
回测阶段执行器

执行Alpha回测，支持并发和顺序模式。
"""

import logging
import hashlib
from datetime import datetime
from typing import List, Dict, Any

from .base import StageExecutor, StageResult, PipelineContext
from ..core.backtest_mgr import BacktestManager

try:
    from database import get_session, update_pipeline_alpha_backtest
except ImportError:
    from worldquant_alpha.database import get_session, update_pipeline_alpha_backtest

logger = logging.getLogger(__name__)


class BacktestStage(StageExecutor):
    """回测阶段执行器"""

    def __init__(self, stage_name: str, input_attr: str, output_attr: str, neutrals: List[str] = None):
        super().__init__(f"backtest_{stage_name}")
        self.input_attr = input_attr
        self.output_attr = output_attr
        self.neutrals = neutrals or ["SUBINDUSTRY"]

    def execute(self, context: PipelineContext) -> StageResult:
        """执行回测"""
        try:
            alphas = getattr(context, self.input_attr, [])

            if not alphas:
                return StageResult(
                    success=False,
                    message=f"没有可回测的Alpha (属性: {self.input_attr})"
                )

            backtest_config = context.config.backtest
            global_settings = context.config.settings

            logger.info(f"开始回测 {len(alphas)} 个Alpha")
            logger.info(f"回测模式: {backtest_config.mode}, 并发数: {backtest_config.max_workers}")

            # 打印回测设置
            logger.info(f"回测设置 - Region: {global_settings.region}, Universe: {global_settings.universe}, Delay: {global_settings.delay}")

            manager = BacktestManager(
                max_workers=backtest_config.max_workers,
                batch_size=backtest_config.batch_size
            )

            # 构建回测设置
            settings = {
                "instrumentType": global_settings.instrument_type,
                "region": global_settings.region,
                "universe": global_settings.universe,
                "delay": global_settings.delay,
                "truncation": backtest_config.settings.truncation,
                "pasteurization": backtest_config.settings.pasteurization,
                "testPeriod": backtest_config.settings.test_period,
                "decay": backtest_config.settings.decay,
                "neutralization": self.neutrals[0] if self.neutrals else "SUBINDUSTRY",
                "language": "FASTEXPR",
                "visualization": False,
                "unitHandling": "VERIFY",
                "nanHandling": "ON",
            }

            # 执行回测
            all_results = []
            for neutral in self.neutrals:
                settings["neutralization"] = neutral
                results = manager.run(
                    alphas,
                    settings,
                    context.client,
                    mode=backtest_config.mode.value
                )

                # 转换结果格式
                for r in results:
                    # 更新数据库中的Alpha状态（无论成功还是失败）
                    try:
                        session = get_session()
                        expr_hash = hashlib.sha256(r.alpha_expression.encode()).hexdigest()

                        if r.success:
                            # 提取 self_corr
                            self_corr = None
                            if r.raw_result:
                                self_corr = r.raw_result.get('self_corr')

                            all_results.append({
                                "expression": r.alpha_expression,
                                "alpha_id": r.alpha_id,
                                "sharpe": r.sharpe,
                                "fitness": r.fitness,
                                "turnover": r.turnover,
                                "color": r.color,
                                "self_corr": self_corr,
                                "neutralization": neutral,
                                "raw_result": r.raw_result
                            })

                            # 更新为完成状态
                            update_pipeline_alpha_backtest(
                                session,
                                expr_hash,
                                is_tested=True,
                                backtest_status='completed',
                                platform_alpha_id=r.alpha_id,
                                sharpe=r.sharpe,
                                fitness=r.fitness,
                                turnover=r.turnover,
                                color=r.color,
                                self_corr=self_corr,
                                backtested_at=datetime.now()
                            )
                        else:
                            # 更新为失败状态
                            update_pipeline_alpha_backtest(
                                session,
                                expr_hash,
                                is_tested=True,
                                backtest_status='failed',
                                error_message=r.error
                            )

                        session.close()
                    except Exception as db_err:
                        logger.warning(f"更新数据库失败: {db_err}")

            setattr(context, self.output_attr, all_results)

            return StageResult(
                success=True,
                data=all_results,
                message=f"回测完成: {len(all_results)} 个成功结果",
                metadata={
                    "input_count": len(alphas),
                    "success_count": len(all_results),
                    "neutrals": self.neutrals
                }
            )

        except Exception as e:
            logger.exception("回测失败")
            return StageResult(
                success=False,
                message=f"回测失败: {str(e)}"
            )
