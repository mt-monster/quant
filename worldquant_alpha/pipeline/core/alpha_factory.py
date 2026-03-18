"""
Alpha工厂模块

提供一阶、二阶、三阶Alpha表达式生成。
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class AlphaFactory:
    """Alpha表达式工厂类"""

    @staticmethod
    def preprocess_fields(fields: List[str], backfill_days: int = 120, winsorize_std: float = 4.0) -> List[str]:
        """预处理数据字段"""
        processed = []
        for field in fields:
            processed.append(f"winsorize(ts_backfill({field}, {backfill_days}), std={winsorize_std})")
        logger.info(f"预处理完成: {len(fields)} 个字段")
        return processed

    @classmethod
    def first_order(cls, fields: List[str], ops: List[str], time_windows: List[int]) -> List[str]:
        """生成一阶Alpha表达式"""
        alphas = []
        for field in fields:
            alphas.append(field)
            for op in ops:
                if op.startswith("ts_"):
                    for window in time_windows:
                        alphas.append(f"{op}({field}, {window})")
                elif op == "signed_power":
                    alphas.append(f"{op}({field}, 2)")
                else:
                    alphas.append(f"{op}({field})")
        logger.info(f"一阶生成: {len(fields)} 字段 -> {len(alphas)} Alpha")
        return alphas

    @classmethod
    def second_order(cls, first_order_alphas: List[str], group_ops: List[str], region: str) -> List[str]:
        """生成二阶Alpha表达式 (分组操作)"""
        alphas = []
        groups = cls._get_groups_for_region(region)

        for fo_alpha in first_order_alphas:
            for group_op in group_ops:
                for group in groups:
                    if group_op.startswith("group_vector"):
                        alphas.append(f"{group_op}({fo_alpha}, cap, densify({group}))")
                    elif group_op.startswith("group_percentage"):
                        alphas.append(f"{group_op}({fo_alpha}, densify({group}), percentage=0.5)")
                    else:
                        alphas.append(f"{group_op}({fo_alpha}, densify({group}))")

        logger.info(f"二阶生成: {len(first_order_alphas)} -> {len(alphas)} Alpha")
        return alphas

    @classmethod
    def third_order(cls, second_order_alphas: List[str], region: str,
                   entry_events: Dict[str, bool] = None,
                   exit_events: Dict[str, Any] = None) -> List[str]:
        """生成三阶Alpha表达式 (trade_when)"""
        alphas = []
        open_events = cls._get_open_events(region, entry_events)
        close_events = cls._get_exit_events(exit_events)

        for so_alpha in second_order_alphas:
            for open_event in open_events:
                for close_event in close_events:
                    alphas.append(f"trade_when({open_event}, {so_alpha}, {close_event})")

        logger.info(f"三阶生成: {len(second_order_alphas)} -> {len(alphas)} Alpha")
        return alphas

    @classmethod
    def _get_groups_for_region(cls, region: str) -> List[str]:
        """获取地区特定的分组列表"""
        cap_group = "bucket(rank(cap), range='0.1, 1, 0.1')"
        asset_group = "bucket(rank(assets),range='0.1, 1, 0.1')"
        sector_cap_group = "bucket(group_rank(cap, sector),range='0.1, 1, 0.1')"
        vol_group = "bucket(rank(ts_std_dev(returns,20)),range = '0.1, 1, 0.1')"
        liquidity_group = "bucket(rank(close*volume),range = '0.1, 1, 0.1')"

        groups = [
            "market", "sector", "industry", "subindustry",
            cap_group, asset_group, sector_cap_group, vol_group, liquidity_group
        ]

        region_groups = {
            "USA": [
                'pv13_h_min2_3000_sector', 'pv13_r2_min20_3000_sector',
                'pv13_r2_min2_3000_sector', 'sta1_top3000c50'
            ],
            "CHN": ['pv13_h_min2_sector', 'sta1_top3000c30'],
            "HKG": ['pv13_10_minvol_1m_sector', 'sta1_allc50'],
            "EUR": ['pv13_5_sector', 'sta1_allc10'],
        }

        if region in region_groups:
            groups.extend(region_groups[region])

        return groups

    @classmethod
    def _get_open_events(cls, region: str, entry_config: Dict[str, bool] = None) -> List[str]:
        """获取开仓事件列表"""
        events = [
            "ts_arg_max(volume, 5) == 0",
            "ts_corr(close, volume, 20) < 0",
            "ts_corr(close, volume, 5) < 0",
            "ts_mean(volume,10) > ts_mean(volume,60)",
            "group_rank(ts_std_dev(returns,60), sector) > 0.7",
            "ts_zscore(returns,60) > 2",
        ]

        region_events = {
            "USA": ["rank(rp_css_business) > 0.8", "rank(vec_avg(mws82_sentiment)) > 0.8"],
            "CHN": ["rank(vec_avg(oth111_xueqiunaturaldaybasicdivisionstat_senti_conform)) > 0.8"],
            "EUR": ["rank(rp_css_business) > 0.8"],
        }

        if region in region_events:
            events.extend(region_events[region])

        return events

    @classmethod
    def _get_exit_events(cls, exit_config: Dict[str, Any] = None) -> List[str]:
        """获取平仓事件列表"""
        if exit_config:
            profit_target = exit_config.get("profit_target", 0.1)
            events = [f"abs(returns) > {profit_target}", "-1"]
        else:
            events = ["abs(returns) > 0.1", "-1"]
        return events
