"""
Alpha相关API
提供对WorldQuant Alpha的管理功能
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional, Union
from urllib.parse import urljoin

from ..auth import get_session
from ..config.constants import API_BASE_URL
from ..utils.retry import with_retry
from ..utils.exceptions import APIError

# 配置日志
logger = logging.getLogger(__name__)

@with_retry()
def get_alpha_details(alpha_id: str, session=None) -> Dict[str, Any]:
    """
    获取Alpha详情
    
    参数:
    - alpha_id: Alpha ID
    - session: 会话对象，如果为None则使用当前会话
    
    返回:
    - Alpha详情字典
    """
    if session is None:
        session = get_session()
    
    logger.info(f"获取Alpha详情: {alpha_id}")
    
    try:
        response = session.get(urljoin(API_BASE_URL, f"alphas/{alpha_id}"))
        response.raise_for_status()
        
        details = response.json()
        logger.info(f"成功获取Alpha详情: {alpha_id}")
        
        return details
    except Exception as e:
        error_msg = f"获取Alpha详情失败: {str(e)}"
        logger.error(error_msg)
        raise APIError(error_msg)

@with_retry()
def update_alpha_properties(
    alpha_id: str,
    properties: Dict[str, Any] = None,
    session=None
) -> bool:
    """
    更新Alpha属性
    
    参数:
    - alpha_id: Alpha ID
    - properties: 属性字典，包含以下可选键:
      - name: Alpha名称
      - color: Alpha颜色
      - tags: Alpha标签列表
      - category: Alpha类别
      - regular.description: 常规描述
      - combo.description: 组合描述
      - selection.description: 选择描述
    - session: 会话对象，如果为None则使用当前会话
    
    返回:
    - 是否更新成功
    """
    if session is None:
        session = get_session()
    
    if not properties:
        logger.warning("没有提供任何属性进行更新")
        return True
        
    logger.info(f"更新Alpha属性: {alpha_id}")
    
    # 转换属性格式
    params = {}
    
    if properties.get('name'):
        params['name'] = properties['name']
        
    if properties.get('color'):
        params['color'] = properties['color']
        
    if properties.get('tags'):
        params['tags'] = properties['tags']
        
    if properties.get('category'):
        params['category'] = properties['category']
        
    if properties.get('regular.description') is not None:
        if 'regular' not in params:
            params['regular'] = {}
        params['regular']['description'] = properties['regular.description']
        
    if properties.get('combo.description') is not None:
        if 'combo' not in params:
            params['combo'] = {}
        params['combo']['description'] = properties['combo.description']
        
    if properties.get('selection.description') is not None:
        if 'selection' not in params:
            params['selection'] = {}
        params['selection']['description'] = properties['selection.description']
    
    try:
        response = session.patch(urljoin(API_BASE_URL, f"alphas/{alpha_id}"), json=params)
        response.raise_for_status()
        
        logger.info(f"成功更新Alpha属性: {alpha_id}")
        return True
    except Exception as e:
        error_msg = f"更新Alpha属性失败: {str(e)}"
        logger.error(error_msg)
        return False

@with_retry()
def check_alpha_status(alpha_id: str, session=None) -> Tuple[bool, Optional[str]]:
    """
    检查Alpha状态
    
    参数:
    - alpha_id: Alpha ID
    - session: 会话对象，如果为None则使用当前会话
    
    返回:
    - (成功状态, 颜色值) 元组
    """
    if session is None:
        session = get_session()
    
    logger.info(f"检查Alpha状态: {alpha_id}")
    
    try:
        # 检查check状态
        check_response = session.get(urljoin(API_BASE_URL, f"alphas/{alpha_id}/check"))
        check_response.raise_for_status()
        
        check_data = check_response.json()
        checks = check_data.get("is", {}).get("checks", [])
        
        # 检查是否有失败的检查项
        for check in checks:
            if check.get("result") == "FAIL":
                logger.info(f"Alpha {alpha_id} 检查失败: {check.get('name')}")
                # 设置颜色为黄色
                update_alpha_properties(alpha_id, {"color": "YELLOW"}, session=session)
                return False, "YELLOW"

        # 获取自相关性值
        self_corr = None
        for check in checks:
            if check.get("name") == "SELF_CORRELATION":
                self_corr = check.get("value")
                break
                
        # 根据自相关性值设置颜色
        color = "BLUE"  # 默认蓝色
        update_alpha_properties(alpha_id, {"color": color}, session=session)
        
        if self_corr is not None:
            if self_corr <= 0.7:
                # 自相关性小于0.7，设置为绿色
                update_alpha_properties(alpha_id, {"color": "GREEN"}, session=session)
                logger.info(f"Alpha {alpha_id} 自相关性为 {self_corr}，设置为绿色")
                color = "GREEN"
        
        return True, color
    
    except Exception as e:
        error_msg = f"检查Alpha状态时发生错误: {e}"
        logger.error(error_msg)
        return False, None

@with_retry()
def get_alphas(limit: int = 50, offset: int = 0, filters: Dict[str, Any] = None, session=None) -> pd.DataFrame:
    """
    获取Alpha列表
    
    参数:
    - limit: 每页数量
    - offset: 偏移量
    - filters: 过滤条件，可包含以下键:
      - status: 状态筛选
      - dateCreated: 创建日期范围
      - is.fitness: 适应度阈值
      - is.sharpe: 夏普比率阈值
      - settings.region: 地区
      - order: 排序方式
      - hidden: 是否包含隐藏
      - type: Alpha类型
    - session: 会话对象，如果为None则使用当前会话
    
    返回:
    - Alpha列表的DataFrame
    """
    if session is None:
        session = get_session()
    
    logger.info(f"获取Alpha列表，limit: {limit}, offset: {offset}")
    
    query_params = f"limit={limit}&offset={offset}"
    if filters:
        for key, value in filters.items():
            if value is not None:
                query_params += f"&{key}={value}"
    
    try:
        response = session.get(urljoin(API_BASE_URL, f"users/self/alphas?{query_params}"))
        response.raise_for_status()
        
        data = response.json()
        alphas_df = pd.DataFrame(data.get('results', []))
        logger.info(f"成功获取{len(alphas_df)}个Alpha")
        
        return alphas_df
    except Exception as e:
        error_msg = f"获取Alpha列表失败: {str(e)}"
        logger.error(error_msg)
        raise APIError(error_msg)

def get_vec_fields(fields: List[str]) -> List[str]:
    """
    生成向量字段列表
    
    参数:
    - fields: 原始字段列表
    
    返回:
    - 向量字段列表
    """
    vec_ops = ["vec_avg", "vec_sum"]
    vec_fields = []
 
    for field in fields:
        for vec_op in vec_ops:
            if vec_op == "vec_choose":
                vec_fields.append("%s(%s, nth=-1)" % (vec_op, field))
                vec_fields.append("%s(%s, nth=0)" % (vec_op, field))
            else:
                vec_fields.append("%s(%s)" % (vec_op, field))
 
    return vec_fields


def process_datafields(df: pd.DataFrame) -> List[str]:
    """
    处理数据字段
    
    参数:
    - df: 数据字段DataFrame
    
    返回:
    - 处理后的字段列表
    """
    datafields = []
    
    # 添加矩阵类型的字段
    if 'type' in df.columns and 'id' in df.columns:
        datafields += df[df['type'] == "MATRIX"]["id"].tolist()
        
        # 处理向量类型的字段
        vector_fields = df[df['type'] == "VECTOR"]["id"].tolist()
        datafields += get_vec_fields(vector_fields)
    
    # 处理并返回
    return ["winsorize(ts_backfill(%s, 120), std=4)" % field for field in datafields] 