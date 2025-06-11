#!/usr/bin/env python3
"""
Alpha回测示例脚本
展示如何简单运行一个Alpha回测
"""
import logging
import os
import sys
import time
from dotenv import load_dotenv

# 将项目根目录添加到模块搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from wd_lib_wrapper import get_api

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    print("开始Alpha回测示例...")

    # 初始化API客户端
    try:
        api = get_api()
        print("成功初始化API")
    except Exception as e:
        print(f"初始化API失败: {str(e)}")
        return

    # Alpha表达式示例
    alpha_expression = "rank(close)"

    # 回测设置
    settings = {
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

    try:
        print(f"开始回测Alpha: {alpha_expression}")

        # 运行回测
        result = api.run_backtest(alpha_expression, settings)

        if result:
            print("\n回测结果:")
            print(f"Alpha ID: {result.get('id', 'N/A')}")
            print(f"状态: {result.get('status',  'N/A')}")
            print(f"夏普比率: {result.get('sharpe', 'N/A')}")
            print(f"回撤: {result.get('drawdown', 'N/A')}")
            print(f"换手率: {result.get('turnover', 'N/A')}")
            print(f"颜色: {result.get('color', 'N/A')}")

            # 更新Alpha属性
            if result.get('id'):
                alpha_id = result.get('id')
                print("\n更新Alpha属性...")
                properties = {
                    "name": "示例Alpha",
                    "tags": ["示例", "测试"],
                    "regular.description": "这是一个示例Alpha"
                }
                success = api.set_alpha_color(alpha_id, "BLUE")
                print(f"更新颜色结果: {'成功' if success else '失败'}")
        else:
            print("回测失败")
    except Exception as e:
        print(f"回测过程中出错: {str(e)}")

    print("\n示例运行完成")


if __name__ == "__main__":
    main()
