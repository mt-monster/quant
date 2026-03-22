"""
阶段执行器基类

定义所有阶段执行器的通用接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """阶段执行结果"""
    success: bool
    data: Any = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    """Pipeline上下文"""
    config: Any = None  # PipelineConfig
    client: Any = None  # WorldQuantClient
    state: Any = None   # PipelineState

    # 各阶段数据
    datafields: List[str] = field(default_factory=list)
    first_order_alphas: List[str] = field(default_factory=list)
    filtered_first_order: List[Dict[str, Any]] = field(default_factory=list)
    second_order_alphas: List[str] = field(default_factory=list)
    filtered_second_order: List[Dict[str, Any]] = field(default_factory=list)
    third_order_alphas: List[str] = field(default_factory=list)
    filtered_third_order: List[Dict[str, Any]] = field(default_factory=list)

    # 全局元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 阶段控制参数
    first_order_limit: int = 0  # 第一阶段生成Alpha数量限制，0表示不限制
    first_order_to_second_count: int = 0  # 第一阶段到第二阶段的数量，0表示不限制
    first_order_to_second_ids: List[int] = field(default_factory=list)  # 第一阶段到第二阶段的指定ID
    second_order_to_third_count: int = 0  # 第二阶段到第三阶段的数量，0表示不限制
    second_order_to_third_ids: List[int] = field(default_factory=list)  # 第二阶段到第三阶段的指定ID
    third_order_test_ids: List[int] = field(default_factory=list)  # 第三阶段测试的指定ID


class StageExecutor(ABC):
    """阶段执行器基类"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    def execute(self, context: PipelineContext) -> StageResult:
        """
        执行阶段

        参数:
        - context: Pipeline上下文

        返回:
        - 阶段执行结果
        """
        pass

    def pre_execute(self, context: PipelineContext) -> bool:
        """
        执行前检查

        返回:
        - 是否继续执行
        """
        return True

    def post_execute(self, context: PipelineContext, result: StageResult) -> StageResult:
        """
        执行后处理

        返回:
        - 处理后的结果
        """
        return result

    def run(self, context: PipelineContext) -> StageResult:
        """
        运行阶段（包含前后处理）

        参数:
        - context: Pipeline上下文

        返回:
        - 阶段执行结果
        """
        self.logger.info(f"开始执行阶段: {self.name}")

        # 前置检查
        if not self.pre_execute(context):
            self.logger.warning(f"阶段 {self.name} 前置检查未通过，跳过")
            return StageResult(success=False, message="前置检查未通过")

        try:
            # 执行阶段
            result = self.execute(context)

            # 后置处理
            result = self.post_execute(context, result)

            if result.success:
                self.logger.info(f"阶段 {self.name} 执行成功: {result.message}")
            else:
                self.logger.error(f"阶段 {self.name} 执行失败: {result.message}")

            return result

        except Exception as e:
            self.logger.exception(f"阶段 {self.name} 执行异常")
            return StageResult(success=False, message=f"执行异常: {str(e)}")