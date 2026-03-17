#!/usr/bin/env python
"""
测试 WorldQuant Alpha 回测最大并发能力

测试原理：
- 使用不同并发数（1, 2, 4, 8, 10）
- 每个并发测试少量 Alpha（5个）
- 记录总耗时，计算实际并发效率
- 观察是否有 429 Too Many Requests 错误

注意事项：
- WorldQuant API 有请求频率限制
- 过于频繁的请求可能导致账号被限流
- 建议生产环境使用 4-6 线程，每个任务间隔 3-5 秒
"""

import time
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import Backtester
from alpha_generator import batch_generate_alphas, create_default_templates

def test_concurrency(max_workers_list=[1, 2, 4, 6, 8, 10], num_alphas=5):
    """测试不同并发数下的回测性能"""
    
    print("=" * 70)
    print("WorldQuant Alpha 回测并发能力测试")
    print("=" * 70)
    print(f"测试参数：每个并发数测试 {num_alphas} 个 Alpha")
    print(f"测试并发数：{max_workers_list}")
    print()
    
    results = []
    
    for max_workers in max_workers_list:
        print(f"\n{'='*70}")
        print(f"测试并发数: {max_workers}")
        print("=" * 70)
        
        # 创建回测器
        backtester = Backtester(max_retry=2, batch_size=max_workers, notify=False, sharpe_threshold=1.6)
        
        # 生成测试用的 Alpha 列表
        templates = create_default_templates()
        test_alphas = []
        
        # 从模板3（价量背离）生成，因为它字段最通用
        template = templates[2]
        template_name, sim_data = batch_generate_alphas(
            template=template,
            datafields=["close", "volume"],  # 使用简单数据字段
            limit=num_alphas,
            db_save=False,
            order=0
        )
        
        if not sim_data:
            print(f"[ERROR] 无法生成测试Alpha")
            continue
            
        print(f"[INFO] 生成 {len(sim_data)} 个测试Alpha")
        
        # 记录开始时间
        start_time = time.time()
        
        try:
            # 执行回测
            result = backtester.backtest_simulation_data_list(
                sim_data, 
                ir_threshold=0.1,
                max_workers=max_workers
            )
            
            elapsed = time.time() - start_time
            
            # 记录结果
            success_count = result.get('success_count', 0)
            fail_count = result.get('fail_count', 0)
            avg_time_per_alpha = elapsed / num_alphas if num_alphas > 0 else 0
            
            results.append({
                'workers': max_workers,
                'total_time': elapsed,
                'success': success_count,
                'fail': fail_count,
                'avg_time': avg_time_per_alpha
            })
            
            print(f"\n[RESULT] 并发数 {max_workers}:")
            print(f"  总耗时: {elapsed:.2f}秒")
            print(f"  成功: {success_count}")
            print(f"  失败: {fail_count}")
            print(f"  平均每个Alpha耗时: {avg_time_per_alpha:.2f}秒")
            print(f"  理论并发效率: {(num_alphas * 15) / elapsed:.1f}x (假设单次回测15秒)")
            
        except Exception as e:
            print(f"[ERROR] 测试失败: {str(e)}")
            results.append({
                'workers': max_workers,
                'total_time': -1,
                'success': 0,
                'fail': num_alphas,
                'avg_time': 0,
                'error': str(e)
            })
        
        # 测试间隔，避免触发限流
        if max_workers != max_workers_list[-1]:
            print(f"\n[WAIT] 等待 10 秒后进行下一组测试...")
            time.sleep(10)
    
    # 打印汇总
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    print(f"{'并发数':<8} {'总耗时(s)':<12} {'成功率':<10} {'平均耗时(s)':<12} {'效率':<10}")
    print("-" * 70)
    
    baseline_time = None
    for r in results:
        workers = r['workers']
        total_time = r['total_time']
        success = r['success']
        avg_time = r['avg_time']
        
        if total_time < 0:
            print(f"{workers:<8} {'FAIL':<12} {'FAIL':<10} {'FAIL':<12} {'FAIL':<10}")
            continue
            
        success_rate = f"{success}/{num_alphas}"
        
        # 计算相对效率（相对于单线程）
        if baseline_time is None:
            baseline_time = total_time
            efficiency = "baseline"
        else:
            speedup = baseline_time / total_time
            efficiency = f"{speedup:.2f}x"
        
        print(f"{workers:<8} {total_time:<12.2f} {success_rate:<10} {avg_time:<12.2f} {efficiency:<10}")
    
    print("\n" + "=" * 70)
    print("建议：")
    print("- 单线程: 最稳定，但速度最慢")
    print("- 4-6 线程: 平衡稳定性和速度的最佳选择")
    print("- 8+ 线程: 可能触发API限流（429错误），不推荐")
    print("=" * 70)

if __name__ == "__main__":
    # 从命令行获取参数
    workers = [1, 2, 4, 6, 8] if len(sys.argv) < 2 else [int(x) for x in sys.argv[1].split(',')]
    num = 5 if len(sys.argv) < 3 else int(sys.argv[2])
    
    test_concurrency(workers, num)
