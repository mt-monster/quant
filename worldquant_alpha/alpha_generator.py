import logging
import json
import itertools
from datetime import datetime
import pandas as pd
import os
import time
import random
from database import save_alpha, alpha_exists

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        生成Alpha表达式
        
        参数:
        - limit: 限制生成的Alpha数量
        - datafields: 如果提供，则替换<company_fundamentals>组件
        
        返回:
        - 生成的Alpha表达式列表
        """
        logger.info(f"开始生成Alpha表达式，限制: {limit if limit else '无限制'}")
        
        # 如果提供了datafields，更新components
        if datafields is not None and '<company_fundamentals>' in self.components:
            self.components['<company_fundamentals>'] = datafields
            self.total_combinations = self._calculate_combinations()
            logger.info(f"使用提供的数据字段，更新组合数: {self.total_combinations}")
        
        # 准备组件值的列表
        component_values = []
        component_keys = []
        
        for key, values in self.components.items():
            # 跳过嵌套组件，这些将在后面手动处理
            if key not in ['<ratio_expr>']:
                component_keys.append(key)
                component_values.append(values)
        
        # 生成组合
        alpha_expressions = []
        count = 0
        
        # 处理特殊的嵌套模板
        if '<ratio_expr>' in self.components:
            # 对于每个比率表达式模板
            for ratio_template in self.components['<ratio_expr>']:
                # 准备这个比率表达式的基本模板
                base_template = self.template.replace('<ratio_expr>', ratio_template)
                
                # 对于其他组件，使用itertools.product获取所有组合
                for combination in itertools.product(*component_values):
                    # 创建替换映射
                    replacements = dict(zip(component_keys, combination))
                    
                    # 替换模板中的组件
                    expression = base_template
                    for key, value in replacements.items():
                        expression = expression.replace(key, value)
                    
                    # 如果是有效的表达式，添加到结果中
                    if all(tag not in expression for tag in ['<', '>']):
                        alpha_expressions.append(expression)
                        count += 1
                        
                        # 如果达到限制，则停止
                        if limit and count >= limit:
                            break
                    
                # 如果达到限制，则停止
                if limit and count >= limit:
                    break
        else:
            # 使用原有的处理方式
            for combination in itertools.product(*component_values):
                # 创建替换映射
                replacements = dict(zip(component_keys, combination))
                replacements = {key: str(value) for key, value in replacements.items()}

                # 替换模板中的组件
                expression = self.template
                for key, value in replacements.items():
                    expression = expression.replace(key, value)
                
                alpha_expressions.append(expression)
                count += 1
                
                # 如果达到限制，则停止
                if limit and count >= limit:
                    break
        # 将datafield和operator替换到Alpha模板(框架)中group_rank(ts_rank({fundamental model data},252),industry),批量生成Alpha
        # 模板<group_compare_op>(<ts_compare_op>(<company_fundamentals>,<days>),<group>)
        logger.info(f"Alpha表达式生成完成，总数: {len(alpha_expressions)}")
        return alpha_expressions

# 创建默认的Alpha模板
def create_default_templates():
    """创建默认的Alpha模板列表"""
    templates = []
    
    # 模板：基础的组比较模板
    # 将datafield和operator替换到Alpha模板(框架)中group_rank(ts_rank({fundamental model data},252),industry),批量生成Alpha
    # 模板<group_compare_op>(<ts_compare_op>(<company_fundamentals>,<days>),<group>)
    group_compare_template = AlphaTemplate(
        name="基础组比较模板",
        template="<group_compare_op>(<ts_compare_op>(<company_fundamentals>,<days>),<group>)",
        components={
            "<group_compare_op>": ["group_rank", "group_neutralize", "group_scale", "group_backfill", "group_mean", "group_zscore"],
            "<ts_compare_op>": ['ts_rank', 'ts_zscore', 'ts_av_diff'],
            "<days>": [60, 200],
            "<company_fundamentals>": [],  # 将由数据字段填充
            "<group>": ["industry", "subindustry", "sector", "market"]
        }
    )
    templates.append(group_compare_template)

    logger.info(f"创建了 {len(templates)} 个默认Alpha模板")
    return templates

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
        "decay": 0,
        "neutralization": "SUBINDUSTRY",
        "truncation": 0.08,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "ON",
        "language": "FASTEXPR",
        "visualization": False,
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

def batch_generate_alphas(template=None, datafields=None, limit=None, db_save=True, settings=None):
    """
    批量生成Alpha并保存到数据库
    
    参数:
    - template: Alpha模板对象，如果为None则使用默认模板
    - datafields: 数据字段列表
    - limit: 限制生成的Alpha数量
    - db_save: 是否保存到数据库
    - settings: 回测设置
    
    返回:
    - 模板名称和生成的模拟请求数据列表
    """
    if template is None:
        # 如果没有提供模板，创建默认模板并使用第一个
        templates = create_default_templates()
        template = templates[0]
    
    logger.info(f"开始批量生成Alpha，使用模板: {template.name}")
    
    # 如果模板使用<company_fundamentals>且提供了数据字段，则更新模板
    if '<company_fundamentals>' in template.components and datafields is not None:
        template.components['<company_fundamentals>'] = datafields
    
    # 生成Alpha表达式
    alpha_expressions = template.generate_alphas(limit=limit)
    
    # 创建模拟请求数据
    simulation_data_list = []
    saved_count = 0
    
    for expression in alpha_expressions:
        # 检查表达式是否已存在于数据库
        if db_save and alpha_exists(expression):
            logger.info(f"跳过已存在的Alpha表达式: {expression}")
            continue
        
        # 创建模拟请求数据
        sim_data = create_simulation_data(expression, settings)
        simulation_data_list.append(sim_data)
        
        # 保存到数据库
        if db_save:
            alpha_id = save_alpha(
                alpha_expression=expression,
                template_name=template.name,
                settings=sim_data['settings']
            )
            if alpha_id:
                saved_count += 1
                # 每保存100个记录打印一次进度
                if saved_count % 100 == 0:
                    logger.info(f"已保存 {saved_count} 个Alpha到数据库")
    
    if db_save:
        logger.info(f"批量生成完成，总共生成 {len(alpha_expressions)} 个Alpha表达式，保存 {saved_count} 个到数据库")
    else:
        logger.info(f"批量生成完成，总共生成 {len(alpha_expressions)} 个Alpha表达式，未保存到数据库")
    
    return template.name, simulation_data_list 