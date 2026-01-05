import sys
import os

# 添加当前目录到系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 修改database导入，避免导入错误
import alpha_generator
from alpha_generator import (
    first_order_factory,
    ts_comp_factory,
    vector_factory,
    get_vec_fields,
    process_datafields
)

# 测试数据
test_fields = ["close", "volume"]
test_ops_set = ["ts_rank", "ts_percentage", "ts_decay_exp_window", "ts_moment"]

def test_first_order_factory():
    """测试first_order_factory函数"""
    print("测试first_order_factory函数...")
    result = first_order_factory(test_fields, test_ops_set)
    print(f"输入字段: {test_fields}")
    print(f"操作集合: {test_ops_set}")
    print(f"生成的Alpha数量: {len(result)}")
    print("前10个生成的Alpha:")
    for alpha in result[:10]:
        print(f"  - {alpha}")
    print()

def test_ts_comp_factory():
    """测试ts_comp_factory函数"""
    print("测试ts_comp_factory函数...")
    result = ts_comp_factory("ts_percentage", "close", "percentage", [0.5])
    print(f"ts_percentage 生成的Alpha: {result}")
    
    result = ts_comp_factory("ts_moment", "volume", "k", [2, 3])
    print(f"ts_moment 生成的Alpha: {result}")
    print()

def test_vector_factory():
    """测试vector_factory函数"""
    print("测试vector_factory函数...")
    result = vector_factory("ts_corr", "close")
    print(f"vector_factory 生成的Alpha: {result}")
    print()

if __name__ == "__main__":
    print("=== Alpha Generator 函数测试 ===\n")
    test_first_order_factory()
    test_ts_comp_factory()
    test_vector_factory()
    print("=== 测试完成 ===")
