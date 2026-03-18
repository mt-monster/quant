"""
回测阶段执行器

执行Alpha回测，支持并发和顺序模式。
"""

import logging
from typing import List, Dict, Any

from .base import StageExecutor, StageResult, PipelineContext
from ..core.backtest_mgr import BacktestManager

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
                    if r.success:
                        all_results.append({
                            "expression": r.alpha_expression,
                            "alpha_id": r.alpha_id,
                            "sharpe": r.sharpe,
                            "fitness": r.fitness,
                            "turnover": r.turnover,
                            "color": r.color,
                            "neutralization": neutral,
                            "raw_result": r.raw_result
                        })

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
