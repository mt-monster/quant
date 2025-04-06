"""
数据集和数据字段API
提供获取WorldQuant数据集和字段的功能
"""

import time
import logging
import pandas as pd
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

from ..auth import get_session
from ..config.constants import API_BASE_URL
from ..utils.retry import with_retry
from ..utils.exceptions import APIError

# 配置日志
logger = logging.getLogger(__name__)

@with_retry()
def get_datasets(
    session=None,
    instrument_type: str = 'EQUITY',
    region: str = 'USA',
    delay: int = 1,
    universe: str = 'TOP3000'
) -> pd.DataFrame:
    """
    获取数据集列表
    
    参数:
    - session: 会话对象，如果为None则使用当前会话
    - instrument_type: 工具类型，如'EQUITY'
    - region: 地区，如'USA'
    - delay: 延迟
    - universe: 宇宙，如'TOP3000'
    
    返回:
    - 数据集的DataFrame
    """
    if session is None:
        session = get_session()
    
    url = urljoin(API_BASE_URL, "data-sets") + "?" + \
          f"instrumentType={instrument_type}&region={region}&delay={str(delay)}&universe={universe}"
    
    logger.info(f"获取数据集列表: {url}")
    
    try:
        result = session.get(url)
        result.raise_for_status()
        
        datasets_df = pd.DataFrame(result.json()['results'])
        logger.info(f"获取到 {len(datasets_df)} 个数据集")
        
        return datasets_df
    except Exception as e:
        logger.error(f"获取数据集失败: {str(e)}")
        raise APIError(f"获取数据集失败: {str(e)}")

@with_retry()
def get_datafields(
    search_scope: Dict[str, Any],
    dataset_id: str = '',
    search: str = '',
    field_type: str = None,
    session=None
) -> pd.DataFrame:
    """
    获取数据字段
    
    参数:
    - search_scope: 搜索范围参数, 包含以下键:
      - instrumentType: 工具类型，如'EQUITY'
      - region: 地区，如'USA'
      - delay: 延迟
      - universe: 宇宙，如'TOP3000'
    - dataset_id: 数据集ID
    - search: 搜索关键词
    - field_type: 字段类型过滤，如"MATRIX"
    - session: 会话对象，如果为None则使用当前会话
    
    返回:
    - 数据字段的DataFrame
    """
    if session is None:
        session = get_session()
    
    logger.info(f"开始获取数据字段 - 数据集ID: {dataset_id}, 搜索条件: {search}")
    
    instrument_type = search_scope.get('instrumentType', 'EQUITY')
    region = search_scope.get('region', 'USA')
    delay = search_scope.get('delay', 1)
    universe = search_scope.get('universe', 'TOP3000')
    
    base_url = urljoin(API_BASE_URL, "data-fields")

    if len(search) == 0:
        url_template = f"{base_url}?" + \
                       f"&instrumentType={instrument_type}" + \
                       f"&region={region}&delay={str(delay)}&universe={universe}&dataset.id={dataset_id}&limit=50" + \
                       "&offset={x}"
        
        try:
            response = session.get(url_template.format(x=0))
            response.raise_for_status()
                
            count = response.json()['count']
            logger.info(f"找到 {count} 个数据字段 (无搜索条件)")
        except Exception as e:
            logger.error(f"获取数据字段数量时出错: {str(e)}")
            raise APIError(f"获取数据字段数量失败: {str(e)}")
    else:
        url_template = f"{base_url}?" + \
                       f"&instrumentType={instrument_type}" + \
                       f"&region={region}&delay={str(delay)}&universe={universe}&limit=50" + \
                       f"&search={search}" + \
                       "&offset={x}"
        count = 100
        logger.info(f"使用搜索条件，设置获取上限为 {count} 个数据字段")

    datafields_list = []
    for x in range(0, count, 50):
        try:
            logger.debug(f"获取数据字段批次: {x}-{min(x+50, count)}")
            response = session.get(url_template.format(x=x))
            response.raise_for_status()
                
            datafields_list.append(response.json()['results'])
            # 防止API限制，添加小延迟
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"获取数据字段批次时出错: {str(e)}")
            continue

    datafields_list_flat = [item for sublist in datafields_list for item in sublist]
    logger.info(f"成功获取 {len(datafields_list_flat)} 个数据字段")

    datafields_df = pd.DataFrame(datafields_list_flat)
    
    # 如果指定了字段类型，进行过滤
    if field_type and 'type' in datafields_df.columns:
        datafields_df = datafields_df[datafields_df['type'] == field_type]
        logger.info(f"按类型'{field_type}'过滤后剩余 {len(datafields_df)} 个数据字段")
    
    return datafields_df 