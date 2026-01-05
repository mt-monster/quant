#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试generate_multi_order_alphas方法的脚本
"""

import logging
import json
from alpha_generator import AlphaTemplate, create_default_templates

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    logger.info("开始调试generate_multi_order_alphas方法")
    
    # 创建默认模板
    templates = create_default_templates()
    
    # 使用第一个模板
    if not templates:
        logger.error("未创建任何模板")
        return
    
    template = templates[0]
    logger.info(f"使用模板: {template.name}")
    
    # 加载数据字段
    try:
        import os
        data_dir = 'data'
        if os.path.exists(data_dir):
            files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
            if files:
                latest_file = max(files)
                with open(os.path.join(data_dir, latest_file), 'r') as f:
                    datafields = json.load(f)
                logger.info(f"从文件 {latest_file} 加载了 {len(datafields)} 个数据字段")
            else:
                logger.warning("未找到数据字段文件，使用模拟数据字段")
                datafields = ['close', 'volume', 'open', 'high', 'low']
        else:
            logger.warning("未找到数据目录，使用模拟数据字段")
            datafields = ['close', 'volume', 'open', 'high', 'low']
    except Exception as e:
        logger.error(f"加载数据字段时出错: {e}")
        # 使用模拟数据字段
        datafields = ['close', 'volume', 'open', 'high', 'low']
    
    # 调用generate_multi_order_alphas方法
    try:
        # 测试一阶alpha生成
        logger.info("测试一阶alpha生成...")
        first_order_alphas = template.generate_multi_order_alphas(
            order=1,
            limit=10,
            datafields=datafields,
            region="USA"
        )
        logger.info(f"一阶alpha生成完成，共生成 {len(first_order_alphas)} 个alpha")
        logger.info(f"前3个一阶alpha: {first_order_alphas[:3]}")
        
        # 测试二阶alpha生成
        logger.info("\n测试二阶alpha生成...")
        second_order_alphas = template.generate_multi_order_alphas(
            order=2,
            limit=10,
            datafields=datafields,
            region="USA"
        )
        logger.info(f"二阶alpha生成完成，共生成 {len(second_order_alphas)} 个alpha")
        logger.info(f"前3个二阶alpha: {second_order_alphas[:3]}")
        
        # 测试三阶alpha生成
        logger.info("\n测试三阶alpha生成...")
        third_order_alphas = template.generate_multi_order_alphas(
            order=3,
            limit=10,
            datafields=datafields,
            region="USA"
        )
        logger.info(f"三阶alpha生成完成，共生成 {len(third_order_alphas)} 个alpha")
        logger.info(f"前3个三阶alpha: {third_order_alphas[:3]}")
        
    except Exception as e:
        logger.error(f"调用generate_multi_order_alphas方法时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()