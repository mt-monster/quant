"""
Alpha剪枝器模块

按字段前缀去重，保留Top N的Alpha。
"""

import logging
from typing import List, Dict, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class Pruner:
    """Alpha剪枝器"""

    @staticmethod
    def prune(alpha_records: List[Dict[str, Any]], prefix: str, keep_per_field: int) -> List[Dict[str, Any]]:
        """
        按字段前缀剪枝

        参数:
        - alpha_records: Alpha记录列表，每项包含expression, sharpe等字段
        - prefix: 数据字段前缀 (如 "fnd6", "mdl110")
        - keep_per_field: 每个字段保留的数量

        返回:
        - 剪枝后的Alpha列表
        """
        output = []
        num_dict = defaultdict(int)

        # 按sharpe值降序排序
        sorted_records = sorted(alpha_records, key=lambda x: x.get("sharpe", 0), reverse=True)

        for rec in sorted_records:
            exp = rec.get("expression", "")
            try:
                # 提取字段名
                field = exp.split(prefix)[-1].split(",")[0]
                sharpe = rec.get("sharpe", 0)

                # 处理负sharpe的情况
                if sharpe < 0:
                    field = f"-{field}"

                if num_dict[field] < keep_per_field:
                    num_dict[field] += 1
                    output.append(rec)

            except Exception as e:
                logger.warning(f"剪枝处理表达式时出错: {exp}, 错误: {e}")
                continue

        logger.info(f"剪枝完成: 输入 {len(alpha_records)} 个, 输出 {len(output)} 个Alpha")
        return output

    @staticmethod
    def prune_with_decay(alpha_records: List[List[Any]], prefix: str, keep_per_field: int) -> List[List[Any]]:
        """
        带decay的剪枝 (兼容旧格式)

        参数:
        - alpha_records: [expression, decay] 列表
        - prefix: 数据字段前缀
        - keep_per_field: 每个字段保留数量

        返回:
        - 剪枝后的 [expression, decay] 列表
        """
        output = []
        num_dict = defaultdict(int)

        # 按sharpe排序 (假设第3个元素是sharpe)
        sorted_records = sorted(alpha_records, key=lambda x: x[2] if len(x) > 2 else 0, reverse=True)

        for rec in sorted_records:
            exp = rec[1] if len(rec) > 1 else rec[0]
            try:
                field = exp.split(prefix)[-1].split(",")[0]
                sharpe = rec[2] if len(rec) > 2 else 0

                if sharpe < 0:
                    field = f"-{field}"

                if num_dict[field] < keep_per_field:
                    num_dict[field] += 1
                    decay = rec[-1] if len(rec) > 1 else 10
                    output.append([exp, decay])

            except Exception as e:
                logger.warning(f"剪枝处理时出错: {e}")
                continue

        logger.info(f"剪枝完成: 输入 {len(alpha_records)} 个, 输出 {len(output)} 个")
        return output
