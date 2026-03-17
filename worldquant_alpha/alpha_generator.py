import logging
import json
import itertools
from datetime import datetime
import pandas as pd
import os
import time
import random
from collections import defaultdict

try:
    from database import save_alpha, alpha_exists
except ImportError:
    from worldquant_alpha.database import save_alpha, alpha_exists

# ==================== 扩展操作符池 ====================
# 基础操作集合
basic_ops = ["reverse", "inverse", "rank", "zscore", "quantile", "normalize"]

# 扩展的数学操作
math_ops = ["sign", "abs", "log", "sqrt", "sign_power", "sigmoid", "clamp"]

# 时间序列操作（扩展版）
ts_ops = [
    # 基础时间序列
    "ts_rank", "ts_zscore", "ts_delta", "ts_sum", "ts_delay",
    "ts_std_dev", "ts_mean", "ts_arg_min", "ts_arg_max", "ts_scale", "ts_quantile",
    # 新增：收益率相关
    "ts_returns", "ts_cum_returns", "ts_log_return",
    # 新增：统计套利
    "ts_corr", "ts_cov", "ts_beta", "ts_resi", "ts_regression",
    # 新增：移动平均
    "ts_ema", "ts_ma", "ts_wma", "ts_tema",
    # 新增：波动率
    "ts_atr", "ts_downside_dev",
    # 新增：其他有用操作
    "ts_zscore_ma", "ts_decay_linear", "ts_decay_exp_window",
    "ts_min", "ts_max", "ts_median", "ts_skew", "ts_kurtosis",
    "ts_product", "ts_change", "ts_percentile",
]

# 分组操作
group_ops = ["group_rank", "group_neutralize", "group_scale", "group_mean", "group_zscore", "group_normalize"]

# 交易事件操作
trade_ops = ["trade_when", "trade_if", "trade_unless"]

# 组合操作集合
ops_set = basic_ops + math_ops + ts_ops
all_group_ops = group_ops + trade_ops

# ==================== 扩展时间窗口 ====================
# 短期
short_days = [1, 2, 3, 5, 7, 10]
# 中期
medium_days = [15, 20, 22, 30, 44]
# 长期
long_days = [60, 66, 90, 120, 180, 240, 500]
# 完整时间窗口
all_days = short_days + medium_days + long_days

# 常用时间窗口组合
common_day_combinations = [
    [5, 10, 20],      # 短期组合
    [20, 60, 120],    # 中长期组合
    [5, 20, 60],      # 全周期组合
]

# ==================== 支持的数据集 ====================
DATASETS = {
    "EQUITY": {
        "USA": ["fundamental6", "barra_cse6", "sentiment", "shortinterest", "technical6"],
        "CHN": ["fundamental6", "barra_cse6", "technical6"],
        "HKG": ["fundamental6", "barra_cse6"],
        "JPN": ["fundamental6", "barra_cse6"],
        "EUR": ["fundamental6", "barra_cse6"],
    },
    "FUTURES": {
        "GLB": ["futures_return6"],
    }
}

# ==================== 常用数据字段（备选）====================
# 当无法从API获取时使用的默认字段
DEFAULT_FIELDS = [
    "close", "open", "high", "low", "volume", "returns",
    "vwap", "market_cap", "cap", "turnover",
    "assets", "liabilities", "equity", "revenue", "earnings",
    "book_value", "sales", "profit", "ebitda",
]

# 配置日志
# 日志由 main.py 统一配置，这里只获取 logger
logger = logging.getLogger(__name__)


def get_vec_fields(fields):
    """获取向量字段的处理结果"""
    vec_ops = ["vec_avg", "vec_sum"]
    vec_fields = []

    for field in fields:
        for vec_op in vec_ops:
            if vec_op == "vec_choose":
                vec_fields.append("%s(%s, nth=-1)"%(vec_op, field))
                vec_fields.append("%s(%s, nth=0)"%(vec_op, field))
            else:
                vec_fields.append("%s(%s)"%(vec_op, field))

    return vec_fields


def prune(alpha_records, prefix, keep_num):
    """剪枝函数：精减相似alpha，提高回测资源利用率"""
    output = []
    num_dict = defaultdict(int)
    
    # 按sharpe值降序排序
    sorted_records = sorted(alpha_records, key=lambda x: x[2], reverse=True)  # x[2]是sharpe值
    
    for rec in sorted_records:
        exp = rec[1]
        try:
            field = exp.split(prefix)[-1].split(",")[0]
            sharpe = rec[2]
            if sharpe < 0:
                field = "-%s"%field
            if num_dict[field] < keep_num:
                num_dict[field] += 1
                decay = rec[-1] if len(rec) > 1 else 10  # 默认decay为10
                output.append([exp, decay])
        except Exception as e:
            logger.warning(f"剪枝过程中处理表达式 {exp} 时出错: {e}")
            continue
    
    return output


def load_datafields_from_json():
    """从data目录下的JSON文件中加载数据字段
    
    返回:
    - 加载的数据字段列表
    """
    import os
    import json
    
    datafields = []
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    
    # 检查data目录是否存在
    if not os.path.exists(data_dir):
        logger.warning(f"data目录不存在: {data_dir}")
        return datafields
    
    # 遍历data目录下的所有JSON文件
    for filename in os.listdir(data_dir):
        if filename.endswith('.json'):
            json_path = os.path.join(data_dir, filename)
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    # 假设JSON文件包含一个字符串列表
                    if isinstance(content, list):
                        datafields.extend(content)
                        logger.info(f"从 {filename} 加载了 {len(content)} 个数据字段")
            except Exception as e:
                logger.warning(f"加载 {json_path} 时出错: {e}")
    
    # 去重
    datafields = list(set(datafields))
    logger.info(f"总共加载了 {len(datafields)} 个唯一数据字段")
    return datafields


def process_datafields(df):
    """处理数据字段，包括MATRIX和VECTOR类型
    
    参数:
    - df: 数据字段DataFrame或字符串列表
        - 如果是DataFrame，需要包含'type'和'id'列
        - 如果是字符串列表，直接处理每个字符串
    
    返回:
    - 处理后的数据字段列表
    """
    datafields = []
    
    # 检查输入类型
    if isinstance(df, list):
        # 如果是字符串列表，直接使用
        datafields = df
    elif hasattr(df, 'iloc'):  # 检查是否是DataFrame
        # 如果是DataFrame，按原逻辑处理
        datafields += df[df['type'] == "MATRIX"]["id"].tolist()
        datafields += get_vec_fields(df[df['type'] == "VECTOR"]["id"].tolist())
    else:
        # 其他类型，直接转换为列表
        datafields = list(df)
    
    return ["winsorize(ts_backfill(%s, 120), std=4)" % field for field in datafields]


def get_multi_dataset_fields(api=None, instrument_type="EQUITY", region="USA", datasets=None):
    """获取多个数据集的数据字段

    参数:
    - api: WorldQuant API 实例，如果为 None 则跳过 API 获取
    - instrument_type: 工具类型 (EQUITY, FUTURES 等)
    - region: 地区 (USA, CHN, HKG 等)
    - datasets: 数据集列表，默认为 DATASETS 中的配置

    返回:
    - 处理后的数据字段列表
    """
    all_fields = []

    if datasets is None:
        datasets = DATASETS.get(instrument_type, {}).get(region, ["fundamental6"])

    logger.info(f"开始获取数据集: {datasets}, 地区: {region}")

    # 尝试从 API 获取
    if api is not None:
        try:
            from wd_lib.api.datasets import get_datafields
            for dataset in datasets:
                try:
                    df = get_datafields(
                        session=api.session,
                        instrument_type=instrument_type,
                        region=region,
                        dataset_id=dataset
                    )
                    if df is not None and not df.empty:
                        processed = process_datafields(df)
                        all_fields.extend(processed)
                        logger.info(f"从数据集 {dataset} 获取了 {len(processed)} 个字段")
                except Exception as e:
                    logger.warning(f"获取数据集 {dataset} 失败: {e}")
        except Exception as e:
            logger.warning(f"API 调用失败，使用默认字段: {e}")

    # 如果没有获取到任何字段，使用默认字段
    if not all_fields:
        logger.info("使用默认字段列表")
        all_fields = DEFAULT_FIELDS

    # 去重
    all_fields = list(set(all_fields))
    logger.info(f"总共获取了 {len(all_fields)} 个数据字段")
    return all_fields


def generate_advanced_alpha(
    datafields=None,
    order=1,
    limit=None,
    region="USA",
    template_name=None,
    use_expanded_ops=True
):
    """生成高级Alpha表达式（整合函数）

    参数:
    - datafields: 数据字段列表
    - order: 阶数 (1, 2, 3)
    - limit: 生成数量限制
    - region: 地区
    - template_name: 可选的模板名称
    - use_expanded_ops: 是否使用扩展操作符

    返回:
    - alpha表达式列表
    """
    logger.info(f"生成 {order} 阶 Alpha，使用扩展操作符: {use_expanded_ops}")

    # 选择操作符集合
    ops = ops_set if use_expanded_ops else basic_ops + ts_ops

    # 准备数据字段
    if datafields is None:
        datafields = DEFAULT_FIELDS

    processed_fields = process_datafields(datafields)

    # 生成一阶 Alpha
    if order == 1:
        alphas = first_order_factory(processed_fields, ops)
    elif order == 2:
        # 先生成一阶
        first_order = first_order_factory(processed_fields, ops)
        # 生成二阶
        second_order = get_group_second_order_factory(first_order, group_ops, region)
        alphas = second_order
    elif order == 3:
        # 先生成二阶
        first_order = first_order_factory(processed_fields, ops)
        second_order = get_group_second_order_factory(first_order, group_ops, region)
        # 生成三阶
        third_order = []
        for so_alpha in second_order:
            third_order += trade_when_factory("trade_when", so_alpha, region)
            if limit and len(third_order) >= limit:
                break
        alphas = third_order
    else:
        raise ValueError(f"不支持的阶数: {order}")

    # 应用限制
    if limit and len(alphas) > limit:
        alphas = alphas[:limit]

    logger.info(f"生成了 {len(alphas)} 个 {order} 阶 Alpha")
    return alphas


def ts_factory(op, field, days=None):
    """生成时间序列操作的alpha表达式

    参数:
    - op: 时间序列操作符
    - field: 数据字段
    - days: 时间窗口列表，默认为 all_days
    """
    output = []
    if days is None:
        days = all_days  # 使用扩展的时间窗口

    for day in days:
        alpha = "%s(%s, %d)" % (op, field, day)
        output.append(alpha)

    return output


def ts_factory_multi_window(op, field, window_combinations=None):
    """生成多时间窗口组合的alpha表达式

    参数:
    - op: 时间序列操作符
    - field: 数据字段
    - window_combinations: 时间窗口组合列表
    """
    output = []
    if window_combinations is None:
        window_combinations = common_day_combinations

    for combo in window_combinations:
        for day in combo:
            alpha = "%s(%s, %d)" % (op, field, day)
            output.append(alpha)

    return output


def math_factory(op, field):
    """生成数学操作的alpha表达式

    参数:
    - op: 数学操作符
    - field: 数据字段
    """
    if op == "clamp":
        return [f"clamp({field}, -3, 3)"]
    elif op == "sign_power":
        return [f"sign_power({field}, 2)", f"sign_power({field}, 0.5)"]
    elif op == "sigmoid":
        return [f"sigmoid({field})"]
    else:
        return [f"{op}({field})"]


def ts_comp_factory(op, field, factor, paras):
    """生成复杂时间序列操作的alpha表达式"""
    output = []
    days = [5, 22, 66, 240]
    
    for day, para in itertools.product(days, paras):
        if type(para) == float:
            alpha = "%s(%s, %d, %s=%.1f)"%(op, field, day, factor, para)
        elif type(para) == int:
            alpha = "%s(%s, %d, %s=%d)"%(op, field, day, factor, para)
        elif type(para) == str:
            alpha = "%s(%s, %d, %s=%s)"%(op, field, day, factor, para)
        else:
            continue
        
        output.append(alpha)
    
    return output


def vector_factory(op, field):
    """生成向量操作的alpha表达式"""
    output = []
    vectors = ["cap"]
    
    for vector in vectors:
        alpha = "%s(%s, %s)"%(op, field, vector)
        output.append(alpha)
    
    return output


def first_order_factory(fields, ops_set=None):
    """生成一阶alpha表达式

    参数:
    - fields: 数据字段列表
    - ops_set: 操作符列表，默认为扩展后的 ops_set

    返回:
    - alpha表达式列表
    """
    if ops_set is None:
        ops_set = ops_set  # 使用全局扩展的操作符

    alpha_set = []
    for field in fields:
        # 保留原始字段
        alpha_set.append(field)

        for op in ops_set:
            # 处理需要额外参数的时间序列操作
            if op == "ts_percentage":
                alpha_set += ts_comp_factory(op, field, "percentage", [0.3, 0.5, 0.7])
            elif op == "ts_decay_exp_window":
                alpha_set += ts_comp_factory(op, field, "factor", [0.3, 0.5, 0.7, 0.9])
            elif op == "ts_moment":
                alpha_set += ts_comp_factory(op, field, "k", [2, 3, 4])
            elif op == "ts_beta":
                # 需要基准字段，使用 returns 作为默认
                alpha_set += ts_comp_factory(op, field, "benchmark", ["returns"])
            elif op == "ts_corr":
                # 需要第二个字段
                alpha_set += ts_comp_factory(op, field, "second", ["returns", "volume"])
            elif op == "ts_cov":
                alpha_set += ts_comp_factory(op, field, "second", ["returns", "volume"])
            elif op == "ts_regression":
                alpha_set += ts_comp_factory(op, field, "benchmark", ["returns"])
            elif op in ["ts_ema", "ts_wma", "ts_tema"]:
                # 移动平均使用较短的时间窗口
                alpha_set += ts_factory(op, field, short_days + medium_days)
            elif op in ["ts_atr", "ts_downside_dev"]:
                # 波动率相关使用中期窗口
                alpha_set += ts_factory(op, field, medium_days + [120])
            elif op.startswith("ts_"):
                # 其他时间序列操作使用默认窗口
                alpha_set += ts_factory(op, field)
            elif op in math_ops:
                # 数学操作
                alpha_set += math_factory(op, field)
            elif op == "inst_tvr":
                alpha_set += ts_factory(op, field)
            else:
                # 基础操作
                alpha = "%s(%s)" % (op, field)
                alpha_set.append(alpha)

    return alpha_set


# Alpha模板定义
class AlphaTemplate:
    def __init__(self, name, template, components):
        """
        初始化Alpha模板
        
        参数:
        - name: 模板名称
        - template: 模板字符串，如"<group_compare_op>(<ts_compare_op>(<company_fundamentals>,<days>),<group>)"
        - components: 字典，包含每个组件的可能值
        """
        self.name = name
        self.template = template
        self.components = components
        self.total_combinations = self._calculate_combinations()

        logger.info(f"初始化Alpha模板: {name}")
        logger.info(f"组件: {components.keys()}")
        logger.info(f"理论上可能的组合数: {self.total_combinations}")

    def _calculate_combinations(self):
        """计算所有可能的组合数"""
        combinations = 1
        for component, values in self.components.items():
            combinations *= len(values)
        return combinations

    def generate_alphas(self, limit=None, datafields=None):
        """
        生成Alpha表达式（兼容旧版本）
        
        参数:
        - limit: 限制生成的Alpha数量
        - datafields: 如果提供，则替换<company_fundamentals>组件
        
        返回:
        - 生成的Alpha表达式列表
        """
        # 默认使用一阶生成
        return self.generate_multi_order_alphas(order=1, limit=limit, datafields=datafields)

    def generate_multi_order_alphas(self, order=1, limit=None, datafields=None, region="USA"):
        """
        生成多阶Alpha表达式
        
        参数:
        - order: Alpha阶数（0, 1, 2, 或 3），0表示使用模板生成
        - limit: 限制生成的Alpha数量
        - datafields: 如果提供，则使用这些数据字段
        - region: 地区标识，用于分组和交易事件
        
        返回:
        - 生成的Alpha表达式列表
        """
        logger.info(f"开始生成{order}阶Alpha表达式，限制: {limit if limit else '无限制'}")

        if order not in [0, 1, 2, 3]:
            raise ValueError("阶数必须为0、1、2或3")

        # 如果提供了datafields，使用它们
        if datafields is None and '<fundamental_ratio>' in self.components:
            # 对于基础比率模板，我们不需要默认数据字段
            # 因为会使用模板中定义的默认比率
            pass

        # 不需要检查datafields是否为空，因为模板有默认值

        # 一阶alpha生成
        if order == 0:
            # 使用原有的模板生成方式
            logger.info("使用模板方式生成一阶Alpha")
            return self._generate_template_alphas(limit=limit, datafields=datafields)
        else:
            ## 4，数据字段预处理
            # 使用工厂函数方式生成
            logger.info("使用工厂函数方式生成Alpha")
            # 如果datafields为None，从JSON文件加载
            if datafields is None:
                logger.info("未提供datafields，从JSON文件加载")
                datafields = load_datafields_from_json()
                if not datafields:
                    raise ValueError("无法加载数据字段，请确保data目录下有有效的JSON数据字段文件")
            pc_fields = process_datafields(datafields)
            logger.info(f"生成了 {len(pc_fields)} 个一阶预处理数据字段")
            
            
            # 首先生成一阶alpha
            first_order_alphas = first_order_factory(pc_fields, ops_set)
            logger.info(f"生成了 {len(first_order_alphas)} 个一阶Alpha表达式")

            # ##8, 筛选Alpha - get_alpha：截取有潜力提升表现至可以提交的alpha进入下一阶
            # 由于没有实际的历史数据计算性能指标，这里使用基于规则的筛选
            def get_alpha(alphas, limit=None):
                """筛选有潜力的alpha进入下一阶
                
                参数:
                - alphas: alpha表达式列表
                - limit: 限制返回的alpha数量
                
                返回:
                - 筛选后的alpha表达式列表
                """
                # 优先保留包含有效操作符的alpha
                valid_ops = ["ts_rank", "ts_zscore", "ts_moment", "ts_returns", "group_rank", "group_neutralize"]
                filtered_alphas = []
                
                for alpha in alphas:
                    # 保留包含有效操作符的alpha
                    if any(op in alpha for op in valid_ops):
                        filtered_alphas.append(alpha)
                
                # 如果没有足够的alpha，添加剩余的
                if len(filtered_alphas) < len(alphas):
                    for alpha in alphas:
                        if alpha not in filtered_alphas:
                            filtered_alphas.append(alpha)
                
                # 应用限制
                if limit and len(filtered_alphas) > limit:
                    filtered_alphas = filtered_alphas[:limit]
                
                return filtered_alphas
            
            # 筛选有潜力的一阶alpha
            potential_first_order = get_alpha(first_order_alphas)
            logger.info(f"筛选后有潜力的一阶Alpha表达式数量: {len(potential_first_order)} 个")
            
            # ##8, 剪枝Prune：精减相似alpha，提高回测资源利用率
            pruned_first_order = []
            seen_combinations = set()
            
            for alpha in potential_first_order:
                # 提取操作符和数据字段
                try:
                    if "(" in alpha:
                        op_part, field_part = alpha.split("(", 1)
                        field_part = field_part.split(")", 1)[0]
                        # 对于时间序列操作，我们可以忽略时间参数
                        if op_part.startswith("ts_") and "," in field_part:
                            field = field_part.split(",", 1)[0]
                            key = (op_part, field)
                        else:
                            key = (op_part, field_part)
                        
                        if key not in seen_combinations:
                            seen_combinations.add(key)
                            pruned_first_order.append(alpha)
                    else:
                        # 对于原始数据字段，直接添加
                        if alpha not in seen_combinations:
                            seen_combinations.add(alpha)
                            pruned_first_order.append(alpha)
                except Exception as e:
                    logger.warning(f"剪枝过程中处理一阶alpha {alpha} 时出错: {e}")
                    pruned_first_order.append(alpha)
            
            logger.info(f"剪枝后一阶Alpha表达式数量: {len(pruned_first_order)} 个")
            first_order_alphas = pruned_first_order
            
            # 如果只需要一阶alpha
            if order == 1:
                # 应用限制
                if limit and len(first_order_alphas) > limit:
                    first_order_alphas = first_order_alphas[:limit]
                
                logger.info(f"返回一阶Alpha表达式数量: {len(first_order_alphas)}")
                return first_order_alphas
            
            # 如果需要二阶或三阶alpha
            if order == 2:
                # 定义分组操作
                group_ops = ["group_rank", "group_neutralize", "group_scale", "group_mean", "group_zscore"]
                
                # 添加数量限制，防止生成过多
                max_first_order = 5000
                if len(first_order_alphas) > max_first_order:
                    logger.warning(f"一阶Alpha数量 {len(first_order_alphas)} 超过限制 {max_first_order}，进行截断")
                    first_order_alphas = first_order_alphas[:max_first_order]
                
                # 生成二阶alpha
                second_order_alphas = get_group_second_order_factory(first_order_alphas, group_ops, region)
                logger.info(f"生成了 {len(second_order_alphas)} 个二阶Alpha表达式")
                
                # 剪枝：精减相似二阶alpha
                pruned_second_order = []
                seen_second_order = set()
                
                for alpha in second_order_alphas:
                    # 提取分组操作符和基础alpha
                    try:
                        if "(" in alpha and "," in alpha:
                            # 解析group_rank(ts_rank(close, 5), densify(industry))这样的表达式
                            group_op, rest = alpha.split("(", 1)
                            # 找到第一个逗号，它是分组操作符的参数分隔符
                            comma_pos = rest.find(",")
                            if comma_pos != -1:
                                base_alpha = rest[:comma_pos]
                                group_part = rest[comma_pos+1:]
                                # 提取分组名称（去掉densify和括号）
                                if "densify(" in group_part:
                                    group_name = group_part.replace("densify(", "").replace(")", "").strip()
                                else:
                                    group_name = group_part.split(")", 1)[0].strip()
                                
                                key = (group_op, base_alpha, group_name)
                                if key not in seen_second_order:
                                    seen_second_order.add(key)
                                    pruned_second_order.append(alpha)
                            else:
                                # 如果没有逗号，可能是格式不同，直接使用完整alpha
                                if alpha not in seen_second_order:
                                    seen_second_order.add(alpha)
                                    pruned_second_order.append(alpha)
                        else:
                            if alpha not in seen_second_order:
                                seen_second_order.add(alpha)
                                pruned_second_order.append(alpha)
                    except Exception as e:
                        logger.warning(f"剪枝过程中处理二阶alpha {alpha} 时出错: {e}")
                        pruned_second_order.append(alpha)
                
                logger.info(f"剪枝后二阶Alpha表达式数量: {len(pruned_second_order)} 个")
                second_order_alphas = pruned_second_order
                
                # 应用限制
                if limit and len(second_order_alphas) > limit:
                    second_order_alphas = second_order_alphas[:limit]
                
                return second_order_alphas
            elif order == 3:
                # 定义分组操作
                group_ops = ["group_rank", "group_neutralize", "group_scale", "group_mean", "group_zscore"]
                
                # 添加数量限制，防止生成过多
                max_first_order = 2000
                if len(first_order_alphas) > max_first_order:
                    logger.warning(f"一阶Alpha数量 {len(first_order_alphas)} 超过限制 {max_first_order}，进行截断")
                    first_order_alphas = first_order_alphas[:max_first_order]
                
                # 生成二阶alpha
                second_order_alphas = get_group_second_order_factory(first_order_alphas, group_ops, region)
                logger.info(f"生成了 {len(second_order_alphas)} 个二阶Alpha表达式")
                
                # 限制二阶Alpha数量
                max_second_order = 5000
                if len(second_order_alphas) > max_second_order:
                    logger.warning(f"二阶Alpha数量 {len(second_order_alphas)} 超过限制 {max_second_order}，进行截断")
                    second_order_alphas = second_order_alphas[:max_second_order]
                
                # 生成三阶alpha
                third_order_alphas = []
                for so_alpha in second_order_alphas:
                    third_order_alphas += trade_when_factory("trade_when", so_alpha, region)
                    
                    # 应用限制
                    if limit and len(third_order_alphas) >= limit:
                        break
                
                logger.info(f"生成了 {len(third_order_alphas)} 个三阶Alpha表达式")
                
                # 应用限制
                if limit and len(third_order_alphas) > limit:
                    third_order_alphas = third_order_alphas[:limit]
                
                return third_order_alphas

    def _generate_template_alphas(self, limit=None, datafields=None):
        """
        使用模板方式生成Alpha表达式（内部方法）
        
        参数:
        - limit: 限制生成的Alpha数量
        - datafields: 如果提供，则替换<fundamental_ratio>组件
        
        返回:
        - 生成的Alpha表达式列表
        """
        # 如果没有提供datafields，自动从JSON文件加载
        if datafields is None:
            datafields = load_datafields_from_json()
            logger.info(f"自动从JSON文件加载了 {len(datafields)} 个数据字段")
        
        # 更新components
        if '<fundamental_ratio>' in self.components:
            # 从datafields生成比率表达式
            ratio_expressions = []
            if len(datafields) >= 2:
                # 生成所有可能的两两组合作为比率
                for i, j in itertools.combinations(datafields, 2):
                    ratio_expressions.append(f"{i}/{j}")
            else:
                # 如果数据字段不足，使用默认比率
                ratio_expressions = ["annual_unearned_revenue_total/annual_sga_cost_total"]
            
            self.components['<fundamental_ratio>'] = ratio_expressions
            self.total_combinations = self._calculate_combinations()
            logger.info(f"生成了 {len(ratio_expressions)} 个比率表达式，更新组合数: {self.total_combinations}")

        # 准备组件值的列表
        component_values = []
        component_keys = []

        for key, values in self.components.items():
            component_keys.append(key)
            component_values.append(values)

        # 生成组合
        alpha_expressions = []
        count = 0

        # 使用原有的处理方式
        for combination in itertools.product(*component_values):
            # 创建替换映射
            replacements = dict(zip(component_keys, combination))
            replacements = {key: str(value) for key, value in replacements.items()}

            # 替换模板中的组件
            expression = self.template
            for key, value in replacements.items():
                expression = expression.replace(key, value)

            # 调试输出
            # print(f"DEBUG: Generated expression: {expression}")
            # print(f"DEBUG: Contains template tags: {'<' in expression and '>' in expression}")

            # 如果是有效的表达式（没有未替换的模板标签），添加到结果中
            if '<fundamental_ratio>' not in expression:
                alpha_expressions.append(expression)
                count += 1
                # print(f"DEBUG: Added expression to list")

                # 如果达到限制，则停止
                if limit and count >= limit:
                    break
        
        logger.info(f"Alpha表达式生成完成，总数: {len(alpha_expressions)}")
        return alpha_expressions


# 创建默认的Alpha模板
def create_default_templates():
    """创建基于analyst10的高级Alpha模板列表"""
    templates = []

    # ==================== 模板 1：行业中性化的残差动量 (CAPM残差扩展) ====================
    # 经济逻辑：剥离股票收益率中的行业共性部分，捕捉纯粹的个股特异性动量
    residual_momentum_template = AlphaTemplate(
        name="行业中性化残差动量",
        template="group_neutralize(rank(ts_regression(winsorize(ts_backfill(<returns_field>, 63), std=4), group_mean(winsorize(ts_backfill(<returns_field>, 63), std=4), log(ts_mean(cap, 21)), <sector_field>), 252, rettype=0)), <sector_field>)",
        components={
            "<returns_field>": ["anl10_netfy1_consensus_653", "anl10_netfy2_consensus_633", "anl10_ebify1_consensus_17", "anl10_ebify2_consensus_39"],
            "<sector_field>": ["sector", "industry", "subindustry"],
        }
    )
    templates.append(residual_momentum_template)

    # ==================== 模板 2：分析师预期修正陡度 (预期曲线结构) ====================
    # 经济逻辑：比较不同预测期的分析师预期均值，捕捉基本面加速改善的信号
    analyst_expectation_template = AlphaTemplate(
        name="分析师预期修正陡度",
        template="zscore(group_zscore(subtract(winsorize(ts_backfill(<near_term_field>, 63), std=3), winsorize(ts_backfill(<far_term_field>, 63), std=3)), <group_field>))",
        components={
            "<near_term_field>": ["anl10_netfy1_consensus_653", "anl10_ebify1_consensus_17", "anl10_salff_538"],
            "<far_term_field>": ["anl10_netfy2_consensus_633", "anl10_ebify2_consensus_39", "anl10_salfy2_consensus_562"],
            "<group_field>": ["industry", "sector"],
        }
    )
    templates.append(analyst_expectation_template)

    # ==================== 模板 3：价量背离的隐性强度 (量价确认) ====================
    # 经济逻辑：价格小幅上涨伴随成交量急剧放大，显示有资金暗中吸筹
    price_volume_divergence_template = AlphaTemplate(
        name="价量背离隐性强度",
        template="vector_neut(rank(divide(ts_returns(close, <price_window>), ts_zscore(ts_returns(volume, <volume_window>), <zscore_window>)))), log(cap))",
        components={
            "<price_window>": [5, 10, 20],
            "<volume_window>": [5, 10, 20],
            "<zscore_window>": [10, 20],
        }
    )
    templates.append(price_volume_divergence_template)

    # ==================== 模板 4：多因子模型残差的横截面挖掘 (集成模型残差) ====================
    # 经济逻辑：计算模型因子与其在分组内均值的残差，挖掘组内相对低估/高估的股票
    model_residual_template = AlphaTemplate(
        name="模型残差横截面挖掘",
        template="rank(ts_mean(subtract(winsorize(ts_backfill(<model_field>, 21), std=4), group_mean(winsorize(ts_backfill(<model_field>, 21), std=4), 1, <group_field>)), <momentum_window>))",
        components={
            "<model_field>": ["anl10_ebify1_consensus_17", "anl10_salfy1_consensus_559", "anl10_netfy1_consensus_653", "anl10_gpsfy1_consensus_449"],
            "<group_field>": ["sector", "industry"],
            "<momentum_window>": [5, 10, 20],
        }
    )
    templates.append(model_residual_template)

    # ==================== 模板 5：期权隐含偏度的跨品种比较 (期权市场信息) ====================
    # 经济逻辑：看涨与看跌期权的隐含波动率之差，反映市场对方向性风险的定价
    options_skew_template = AlphaTemplate(
        name="期权隐含偏度比较",
        template="rank(if_else(ts_std_dev(group_neutralize(subtract(<put_field>, <call_field>), <group_field>), <vol_window>) < <vol_threshold>, group_neutralize(subtract(<put_field>, <call_field>), <group_field>), NaN))",
        components={
            "<put_field>": ["anl10_netinnovate_decrease_fy1", "anl10_ebiinnovate_decrease_fy1"],
            "<call_field>": ["anl10_netinnovate_increase_fy1", "anl10_ebiinnovate_increase_fy1"],
            "<group_field>": ["industry", "sector"],
            "<vol_window>": [20, 60],
            "<vol_threshold>": [0.5, 1.0],
        }
    )
    templates.append(options_skew_template)

    # ==================== 模板 6：智能预期分歧度 ====================
    # 经济逻辑：当顶级分析师的"智能预期"与市场共识出现显著偏离时，往往预示着非公开信息或深度研究结论尚未充分反映到股价中
    smart_expectation_divergence_template = AlphaTemplate(
        name="智能预期分歧度",
        template="rank(group_zscore((winsorize(ts_backfill(<smart_est_field>, 63), std=4) - winsorize(ts_backfill(<consensus_field>, 63), std=4)) / winsorize(ts_backfill(<consensus_field>, 63), std=4), <group_field>))",
        components={
            "<smart_est_field>": ["anl10_netfy1_smart_ests_v0_647", "anl10_ebify1_smart_ests_v0_15", "anl10_salff_538"],
            "<consensus_field>": ["anl10_netfy1_consensus_653", "anl10_ebify1_consensus_17", "anl10_salfy1_consensus_559"],
            "<group_field>": ["sector", "industry", "subindustry"],
        }
    )
    templates.append(smart_expectation_divergence_template)

    # ==================== 模板 7：创新性修正动量 ====================
    # 经济逻辑：创新性修正（非羊群式调整）更能反映分析师的真实观点变化。捕捉这类修正的加速度可提前发现基本面拐点
    innovation_revision_momentum_template = AlphaTemplate(
        name="创新性修正动量",
        template="rank(group_zscore(ts_delta(winsorize(ts_backfill(<innovation_field>, 63), std=4), <momentum_window>), <group_field>))",
        components={
            "<innovation_field>": ["anl10_netinnovation_score_fy1", "anl10_ebify1_smart_ests_v0_15", "anl10_salff_538"],
            "<momentum_window>": [5, 10, 21],
            "<group_field>": ["sector", "industry", "subindustry"],
        }
    )
    templates.append(innovation_revision_momentum_template)

    # ==================== 模板 8：预期惊喜复合强度 ====================
    # 经济逻辑：预测惊喜本身的方向性需结合修正的广度（参与分析师数量）验证。单向大广度修正能过滤虚假信号
    predicted_surprise_composite_template = AlphaTemplate(
        name="预期惊喜复合强度",
        template="rank(group_zscore(winsorize(ts_backfill(<pred_surp_field>, 63), std=4) * sign(winsorize(ts_backfill(<innov_up_field>, 63), std=4) - winsorize(ts_backfill(<innov_down_field>, 63), std=4)), <group_field>))",
        components={
            "<pred_surp_field>": ["anl10_netfy1_pred_surps_v0_623", "anl10_ebify1_pred_surps_v0_12", "anl10_salff_538"],
            "<innov_up_field>": ["anl10_netinnovate_increase_fy1", "anl10_ebiinnovate_increase_fy1", "anl10_salinnovate_increase_fy1"],
            "<innov_down_field>": ["anl10_netinnovate_decrease_fy1", "anl10_ebiinnovate_decrease_fy1", "anl10_salinnovate_decrease_fy1"],
            "<group_field>": ["sector", "industry", "subindustry"],
        }
    )
    templates.append(predicted_surprise_composite_template)

    # ==================== 模板 9：修正时效性加权 ====================
    # 经济逻辑：分析师修正的时效性决定信息价值。越近期的修正应赋予越高权重，stale数据应被惩罚
    revision_freshness_weighting_template = AlphaTemplate(
        name="修正时效性加权",
        template="rank(group_zscore(winsorize(ts_backfill(<revise_field>, 63), std=4) * (1 / (1 + winsorize(ts_backfill(<est_age_field>, 63), std=4) / <half_life>)), <group_field>))",
        components={
            "<revise_field>": ["anl10_netrevise_value_fy1", "anl10_ebirevise_value_fy1", "anl10_salrevise_value_fy1"],
            "<est_age_field>": ["anl10_netsmun_1yf_632", "anl10_ebismun_1yf_4", "anl10_salsmun_1yf_560"],
            "<half_life>": [30, 60, 90],
            "<group_field>": ["sector", "industry", "subindustry"],
        }
    )
    templates.append(revision_freshness_weighting_template)

    # ==================== 模板 10：修正幅度-广度协同 ====================
    # 经济逻辑：大幅修正若缺乏广度支持可能是噪音；小幅但大广度修正则反映共识迁移。两者乘积可捕捉"质量×数量"效应
    revision_magnitude_breadth_synthesis_template = AlphaTemplate(
        name="修正幅度-广度协同",
        template="rank(group_zscore(ts_zscore(winsorize(ts_backfill(<revise_field>, 63), std=4), <time_window>) * ts_zscore((winsorize(ts_backfill(<innov_up_field>, 63), std=4) - winsorize(ts_backfill(<innov_down_field>, 63), std=4)), <time_window>), <group_field>))",
        components={
            "<revise_field>": ["anl10_netrevise_value_fy1", "anl10_ebirevise_value_fy1", "anl10_salrevise_value_fy1"],
            "<innov_up_field>": ["anl10_netinnovate_increase_fy1", "anl10_ebiinnovate_increase_fy1", "anl10_salinnovate_increase_fy1"],
            "<innov_down_field>": ["anl10_netinnovate_decrease_fy1", "anl10_ebiinnovate_decrease_fy1", "anl10_salinnovate_decrease_fy1"],
            "<time_window>": [21, 63, 126],
            "<group_field>": ["sector", "industry", "subindustry"],
        }
    )
    templates.append(revision_magnitude_breadth_synthesis_template)

    logger.info(f"创建了 {len(templates)} 个analyst10高级Alpha模板")
    return templates


# 二阶alpha生成函数
def get_group_second_order_factory(first_order, group_ops, region):
    """
    生成二阶alpha因子
    
    参数:
    - first_order: 一阶alpha因子列表
    - group_ops: 分组操作列表
    - region: 地区标识
    
    返回:
    - 二阶alpha因子列表
    """
    second_order = []
    for fo in first_order:
        for group_op in group_ops:
            second_order += group_factory(group_op, fo, region)
    return second_order


def group_factory(op, field, region):
    """
    生成分组操作的alpha因子
    
    参数:
    - op: 分组操作类型
    - field: 数据字段
    - region: 地区标识
    
    返回:
    - 分组操作的alpha因子列表
    """
    output = []
    vectors = ["cap"] 
    
    # 定义不同地区的分组
    chn_group_13 = ['pv13_h_min2_sector', 'pv13_di_6l', 'pv13_rcsed_6l', 'pv13_di_5l', 'pv13_di_4l', 
                    'pv13_di_3l', 'pv13_di_2l', 'pv13_di_1l', 'pv13_parent', 'pv13_level']
    
    chn_group_1 = ['sta1_top3000c30','sta1_top3000c20','sta1_top3000c10','sta1_top3000c2','sta1_top3000c5']
    
    chn_group_2 = ['sta2_top3000_fact4_c10','sta2_top2000_fact4_c50','sta2_top3000_fact3_c20']
    
    hkg_group_13 = ['pv13_10_f3_g2_minvol_1m_sector', 'pv13_10_minvol_1m_sector', 'pv13_20_minvol_1m_sector', 
                    'pv13_2_minvol_1m_sector', 'pv13_5_minvol_1m_sector', 'pv13_1l_scibr', 'pv13_3l_scibr',
                    'pv13_2l_scibr', 'pv13_4l_scibr', 'pv13_5l_scibr']
    
    hkg_group_1 = ['sta1_allc50','sta1_allc5','sta1_allxjp_513_c20','sta1_top2000xjp_513_c5']
    
    hkg_group_2 = ['sta2_all_xjp_513_all_fact4_c10','sta2_top2000_xjp_513_top2000_fact3_c10',
                   'sta2_allfactor_xjp_513_13','sta2_top2000_xjp_513_top2000_fact3_c20']
    
    twn_group_13 = ['pv13_2_minvol_1m_sector','pv13_20_minvol_1m_sector','pv13_10_minvol_1m_sector',
                    'pv13_5_minvol_1m_sector','pv13_10_f3_g2_minvol_1m_sector','pv13_5_f3_g2_minvol_1m_sector',
                    'pv13_2_f4_g3_minvol_1m_sector']
    
    twn_group_1 = ['sta1_allc50','sta1_allxjp_513_c50','sta1_allxjp_513_c20','sta1_allxjp_513_c2',
                   'sta1_allc20','sta1_allxjp_513_c5','sta1_allxjp_513_c10','sta1_allc2','sta1_allc5']
    
    twn_group_2 = ['sta2_allfactor_xjp_513_0','sta2_all_xjp_513_all_fact3_c20',
                   'sta2_all_xjp_513_all_fact4_c20','sta2_all_xjp_513_all_fact4_c50']
    
    usa_group_13 = ['pv13_h_min2_3000_sector','pv13_r2_min20_3000_sector','pv13_r2_min2_3000_sector',
                    'pv13_r2_min2_3000_sector', 'pv13_h_min2_focused_pureplay_3000_sector']
    
    usa_group_1 = ['sta1_top3000c50','sta1_allc20','sta1_allc10','sta1_top3000c20','sta1_allc5']
    
    usa_group_2 = ['sta2_top3000_fact3_c50','sta2_top3000_fact4_c20','sta2_top3000_fact4_c10']
    
    usa_group_6 = ['mdl10_group_name']
    
    asi_group_13 = ['pv13_20_minvol_1m_sector', 'pv13_5_f3_g2_minvol_1m_sector', 'pv13_10_f3_g2_minvol_1m_sector',
                    'pv13_2_f4_g3_minvol_1m_sector', 'pv13_10_minvol_1m_sector', 'pv13_5_minvol_1m_sector']
    
    asi_group_1 = ['sta1_allc50', 'sta1_allc10', 'sta1_minvol1mc50','sta1_minvol1mc20',
                   'sta1_minvol1m_normc20', 'sta1_minvol1m_normc50']
    
    jpn_group_1 = ['sta1_alljpn_513_c5', 'sta1_alljpn_513_c50', 'sta1_alljpn_513_c2', 'sta1_alljpn_513_c20']
    
    jpn_group_2 = ['sta2_top2000_jpn_513_top2000_fact3_c20', 'sta2_all_jpn_513_all_fact1_c5',
                   'sta2_allfactor_jpn_513_9', 'sta2_all_jpn_513_all_fact1_c10']
    
    jpn_group_13 = ['pv13_2_minvol_1m_sector', 'pv13_2_f4_g3_minvol_1m_sector', 'pv13_10_minvol_1m_sector',
                    'pv13_10_f3_g2_minvol_1m_sector', 'pv13_all_delay_1_parent', 'pv13_all_delay_1_level']
    
    kor_group_13 = ['pv13_10_f3_g2_minvol_1m_sector', 'pv13_5_minvol_1m_sector', 'pv13_5_f3_g2_minvol_1m_sector',
                    'pv13_2_minvol_1m_sector', 'pv13_20_minvol_1m_sector', 'pv13_2_f4_g3_minvol_1m_sector']
    
    kor_group_1 = ['sta1_allc20','sta1_allc50','sta1_allc2','sta1_allc10','sta1_minvol1mc50',
                   'sta1_allxjp_513_c10', 'sta1_top2000xjp_513_c50']
    
    kor_group_2 =['sta2_all_xjp_513_all_fact1_c50','sta2_top2000_xjp_513_top2000_fact2_c50',
                  'sta2_all_xjp_513_all_fact4_c50','sta2_all_xjp_513_all_fact4_c5']
    
    eur_group_13 = ['pv13_5_sector', 'pv13_2_sector', 'pv13_v3_3l_scibr', 'pv13_v3_2l_scibr', 'pv13_2l_scibr',
                    'pv13_52_sector', 'pv13_v3_6l_scibr', 'pv13_v3_4l_scibr', 'pv13_v3_1l_scibr']
    
    eur_group_1 = ['sta1_allc10', 'sta1_allc2', 'sta1_top1200c2', 'sta1_allc20', 'sta1_top1200c10']
    
    eur_group_2 = ['sta2_top1200_fact3_c50','sta2_top1200_fact3_c20','sta2_top1200_fact4_c50']
    
    glb_group_13 = ['pv13_2_sector', 'pv13_10_sector', 'pv13_3l_scibr', 'pv13_2l_scibr', 'pv13_1l_scibr',
                    'pv13_52_minvol_1m_all_delay_1_sector','pv13_52_minvol_1m_sector','pv13_52_minvol_1m_sector'] 
    
    glb_group_1 = ['sta1_allc20', 'sta1_allc10', 'sta1_allc50', 'sta1_allc5']
    
    glb_group_2 = ['sta2_all_fact4_c50', 'sta2_all_fact4_c20', 'sta2_all_fact3_c20', 'sta2_all_fact4_c10']
    
    amr_group_13 = ['pv13_4l_scibr', 'pv13_1l_scibr', 'pv13_hierarchy_min51_f1_sector',
                    'pv13_hierarchy_min2_600_sector', 'pv13_r2_min2_sector', 'pv13_h_min20_600_sector']
    
    # 额外的市场分组
    cap_group = "bucket(rank(cap), range='0.1, 1, 0.1')"
    asset_group = "bucket(rank(assets),range='0.1, 1, 0.1')"
    sector_cap_group = "bucket(group_rank(cap, sector),range='0.1, 1, 0.1')"
    sector_asset_group = "bucket(group_rank(assets, sector),range='0.1, 1, 0.1')"
    vol_group = "bucket(rank(ts_std_dev(returns,20)),range = '0.1, 1, 0.1')"
    liquidity_group = "bucket(rank(close*volume),range = '0.1, 1, 0.1')"
    
    # 先定义通用分组
    groups = ["market","sector", "industry", "subindustry",
              cap_group, asset_group, sector_cap_group, sector_asset_group, vol_group, liquidity_group]
    
    # 根据地区添加特定分组
    if region == "CHN":
        groups += chn_group_13 + chn_group_1 + chn_group_2
    elif region == "HKG":
        groups += hkg_group_13 + hkg_group_1 + hkg_group_2
    elif region == "TWN":
        groups += twn_group_13 + twn_group_1 + twn_group_2
    elif region == "USA":
        groups += usa_group_13 + usa_group_1 + usa_group_2 + usa_group_6
    elif region == "ASI":
        groups += asi_group_13 + asi_group_1
    elif region == "JPN":
        groups += jpn_group_1 + jpn_group_2 + jpn_group_13
    elif region == "KOR":
        groups += kor_group_13 + kor_group_1 + kor_group_2
    elif region == "EUR":
        groups += eur_group_13 + eur_group_1 + eur_group_2
    elif region == "GLB":
        groups += glb_group_13 + glb_group_1 + glb_group_2
    elif region == "AMR":
        groups += amr_group_13
    
    # 生成分组操作表达式
    for group in groups:
        if op.startswith("group_vector"):
            for vector in vectors:
                alpha = "%s(%s,%s,densify(%s))"%(op, field, vector, group)
                output.append(alpha)
        elif op.startswith("group_percentage"):
            alpha = "%s(%s,densify(%s),percentage=0.5)"%(op, field, group)
            output.append(alpha)
        else:
            alpha = "%s(%s,densify(%s))" % (op, field, group)
            output.append(alpha)
    
    return output


# 三阶alpha生成函数
def trade_when_factory(op, field, region):
    """
    生成三阶alpha因子（基于交易事件的策略）
    
    参数:
    - op: 操作符，通常为"trade_when"
    - field: 二阶alpha因子表达式
    - region: 地区标识
    
    返回:
    - 三阶alpha因子列表
    """
    output = []
    
    # 定义入场事件
    open_events = [
        "ts_arg_max(volume, 5) == 0",  # 5天内成交量最大的一天
        "ts_corr(close, volume, 20) < 0",  # 20天内收盘价与成交量负相关
        "ts_corr(close, volume, 5) < 0",  # 5天内收盘价与成交量负相关
        "ts_mean(volume, 10) > ts_mean(volume, 60)",  # 10天平均成交量大于60天平均成交量
        "group_rank(ts_std_dev(returns, 60), sector) > 0.7",  # 行业内60天收益率标准差排名较高
        "ts_zscore(returns, 60) > 2",  # 60天收益率Z值大于2
        "ts_arg_min(volume, 5) > 3",  # 5天内成交量最小值不在最近3天
        "ts_std_dev(returns, 5) > ts_std_dev(returns, 20)",  # 5天波动率大于20天波动率
        "ts_arg_max(close, 5) == 0",  # 5天内收盘价最高的一天
        "ts_arg_max(close, 20) == 0",  # 20天内收盘价最高的一天
        "ts_corr(close, volume, 5) > 0",  # 5天内收盘价与成交量正相关
        "ts_corr(close, volume, 5) > 0.3",  # 5天内收盘价与成交量强正相关
        "ts_corr(close, volume, 5) > 0.5",  # 5天内收盘价与成交量很强正相关
        "ts_corr(close, volume, 20) > 0",  # 20天内收盘价与成交量正相关
        "ts_corr(close, volume, 20) > 0.3",  # 20天内收盘价与成交量强正相关
        "ts_corr(close, volume, 20) > 0.5",  # 20天内收盘价与成交量很强正相关
        "ts_regression(returns, %s, 5, lag = 0, rettype = 2) > 0" % field,  # 5天内因子与收益率正相关
        "ts_regression(returns, %s, 20, lag = 0, rettype = 2) > 0" % field,  # 20天内因子与收益率正相关
        "ts_regression(returns, ts_step(20), 20, lag = 0, rettype = 2) > 0",  # 20天内时间趋势与收益率正相关
        "ts_regression(returns, ts_step(5), 5, lag = 0, rettype = 2) > 0"  # 5天内时间趋势与收益率正相关
    ]
    
    # 定义出场事件
    exit_events = [
        "abs(returns) > 0.1",  # 收益率绝对值大于10%
        "-1"  # 永不平仓，由decay控制
    ]
    
    # 生成所有可能的trade_when表达式
    for oe in open_events:
        for ee in exit_events:
            alpha = "%s(%s, %s, %s)" % (op, oe, field, ee)
            output.append(alpha)
    
    return output


def create_simulation_data(alpha_expression, settings=None):
    """
    创建模拟请求数据
    
    参数:
    - alpha_expression: Alpha表达式
    - settings: 可选的设置参数，如果不提供则使用默认设置
    
    返回:
    - 模拟请求数据字典
    """
    # 默认设置
    default_settings = {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "decay": 5,
        "neutralization": "MARKET",
        "truncation": 0.08,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "ON",
        "language": "FASTEXPR",
        "visualization": False
    }

    # 如果提供了设置，则更新默认设置
    if settings:
        default_settings.update(settings)

    # 创建模拟请求数据
    simulation_data = {
        "type": "REGULAR",
        "settings": default_settings,
        "regular": alpha_expression
    }

    return simulation_data


def batch_generate_alphas(template=None, datafields=None, limit=None, db_save=True, settings=None, order=None, start_template=0, end_template=11):
    """
    批量生成Alpha并保存到数据库
    
    参数:
    - template: Alpha模板对象，如果为None则使用默认模板
    - datafields: 数据字段列表
    - limit: 限制生成的Alpha数量
    - db_save: 是否保存到数据库
    - settings: 回测设置
    - order: Alpha阶数（0, 1, 2, 3），0表示使用模板生成，1-3表示使用工厂函数生成对应阶数
    - start_template: 起始模板索引
    - end_template: 结束模板索引
    
    返回:
    - 模板名称和生成的模拟请求数据列表
    """
    if template is None:
        # 创建所有模板
        templates = create_default_templates()
        
    # 根据索引范围选择模板
    if template is not None:
        # 如果传入了template，使用单个模板
        selected_templates = [template]
    else:
        selected_templates = []
        for i in range(start_template, min(end_template, len(templates))):
            if i < len(templates):
                selected_templates.append(templates[i])
    
    if not selected_templates:
        logger.warning(f"模板索引范围 {start_template}-{end_template} 内没有可用模板")
        return None, []
    
    logger.info(f"选择了 {len(selected_templates)} 个模板，索引范围: {start_template}-{end_template}")
    
    # 存储所有生成的Alpha
    all_alpha_expressions = []
    
    # 遍历每个模板生成Alpha
    for template in selected_templates:
        # 如果模板使用<company_fundamentals>且提供了数据字段，则更新模板
        if '<company_fundamentals>' in template.components and datafields is not None:
            template.components['<company_fundamentals>'] = datafields

        # 生成Alpha表达式
        if order is not None:
            alpha_expressions = template.generate_multi_order_alphas(order=order, limit=limit, datafields=datafields)
        else:
            alpha_expressions = template.generate_alphas(limit=limit)
        
        if alpha_expressions:
            all_alpha_expressions.extend(alpha_expressions)
            logger.info(f"模板 {template.name} 生成了 {len(alpha_expressions)} 个Alpha")

    # 创建模拟请求数据
    simulation_data_list = []
    saved_count = 0

    for expression in all_alpha_expressions:
        # 检查表达式是否已存在于数据库
        if db_save and alpha_exists(expression):
            logger.info(f"跳过已存在的Alpha表达式: {expression}")
            continue

        # 保存到数据库，获取数据库ID
        alpha_id = None
        if db_save:
            alpha_id = save_alpha(
                alpha_expression=expression,
                template_name=template.name,
                settings=settings
            )
            if alpha_id:
                saved_count += 1
                # 每保存100个记录打印一次进度
                if saved_count % 100 == 0:
                    logger.info(f"已保存 {saved_count} 个Alpha到数据库")

        # 创建模拟请求数据（包含数据库ID，以便回测后更新状态）
        sim_data = create_simulation_data(expression, settings)
        
        # 将数据库ID添加到simulation_data中，以便回测后更新数据库状态
        if alpha_id:
            sim_data['id'] = alpha_id
        
        simulation_data_list.append(sim_data)

    if db_save:
        logger.info(f"批量生成完成，总共生成 {len(alpha_expressions)} 个Alpha表达式，保存 {saved_count} 个到数据库")
    else:
        logger.info(f"批量生成完成，总共生成 {len(alpha_expressions)} 个Alpha表达式，未保存到数据库")

    return template.name, simulation_data_list
