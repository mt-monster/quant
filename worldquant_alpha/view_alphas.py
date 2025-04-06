#!/usr/bin/env python3
"""
查看数据库中的Alpha表达式
"""
import os
import logging
from dotenv import load_dotenv
from database import get_session, Alpha

# 加载环境变量
load_dotenv()

# 配置日志
log_level_str = os.getenv('LOG_LEVEL', 'INFO')
log_level = getattr(logging, log_level_str.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def view_alphas(limit=20, template_name=None):
    """查看数据库中的Alpha表达式"""
    logger.info(f"查看数据库中的Alpha表达式，限制：{limit}")
    
    # 获取数据库会话
    session = get_session()
    
    try:
        # 构建查询
        query = session.query(Alpha).order_by(Alpha.id.desc())
        
        # 如果指定了模板名称，筛选对应的Alpha
        if template_name:
            query = query.filter(Alpha.template_name == template_name)
        
        # 限制返回数量
        alphas = query.limit(limit).all()
        
        logger.info(f"找到 {len(alphas)} 个Alpha表达式")
        
        # 打印Alpha信息
        for i, alpha in enumerate(alphas, 1):
            logger.info(f"Alpha {i} (ID: {alpha.id}):")
            logger.info(f"  模板: {alpha.template_name}")
            logger.info(f"  表达式: {alpha.alpha_expression}")
            logger.info(f"  状态: {alpha.status}")
            logger.info(f"  创建时间: {alpha.created_at}")
            logger.info("")
        
        # 统计每个模板的数量
        if not template_name:
            template_counts = {}
            for alpha in alphas:
                template_counts[alpha.template_name] = template_counts.get(alpha.template_name, 0) + 1
                
            logger.info("模板统计:")
            for template, count in template_counts.items():
                logger.info(f"  {template}: {count} 个Alpha")
    
    finally:
        # 关闭会话
        session.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='查看数据库中的Alpha表达式')
    parser.add_argument('--limit', type=int, default=20, help='最多显示的Alpha数量')
    parser.add_argument('--template', type=str, help='按模板名称筛选')
    
    args = parser.parse_args()
    
    try:
        view_alphas(limit=args.limit, template_name=args.template)
    except Exception as e:
        logger.exception(f"查看Alpha表达式时发生错误: {e}") 