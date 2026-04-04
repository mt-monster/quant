#!/usr/bin/env python3
"""
挖掘USA地区 D1延迟 RAM中性化 PPA类型Alpha
任务要求:
- region=USA, delay=D1, neutralization=RAM
- 单数据集，2字段组合
- 未点亮金字塔数据集
- 生产相关性 ≤0.7 且有结果
- 至少找到2个可提交Alpha
"""
import os
import logging
import json
import itertools
from datetime import datetime
from dotenv import load_dotenv

try:
    from wd_lib_wrapper import get_api
    from database import save_alpha, alpha_exists
    from alpha_generator import process_datafields, ts_factory, math_factory, group_factory
except ImportError:
    from worldquant_alpha.wd_lib_wrapper import get_api
    from worldquant_alpha.database import save_alpha, alpha_exists
    from worldquant_alpha.alpha_generator import process_datafields, ts_factory, math_factory, group_factory

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 任务配置
CONFIG = {
    "region": "USA",
    "delay": 1,
    "neutralization": "RAM",
    "universe": "TOP3000",
    "instrumentType": "EQUITY",
    "max_production_correlation": 0.7,
    "min_sharpe": 1.2,
    "target_alpha_count": 2,
    # 未点亮金字塔数据集列表(USA地区)
    "target_datasets": [
        "fundamental6", 
        "technical6",
        "sentiment",
        "shortinterest",
        "barra_cse6"
    ],
    # 优先使用的单数据集
    "single_dataset": "fundamental6"
}

def get_unlit_pyramid_dataset_fields(api, dataset_id):
    """获取单个未点亮金字塔数据集的字段"""
    try:
        from wd_lib.api.datasets import get_datafields
        logger.info(f"正在获取数据集 {dataset_id} 字段...")
        
        search_scope = {
            "instrumentType": CONFIG["instrumentType"],
            "region": CONFIG["region"],
            "delay": CONFIG["delay"],
            "universe": CONFIG["universe"]
        }
        
        df = get_datafields(
            search_scope=search_scope,
            dataset_id=dataset_id,
            session=api.session
        )
        
        if df is not None and not df.empty:
            fields = df[df['type'] == "MATRIX"]["id"].tolist()
            logger.info(f"数据集 {dataset_id} 获取到 {len(fields)} 个字段")
            return fields
        else:
            logger.warning(f"数据集 {dataset_id} 无字段返回")
            return []
    except Exception as e:
        logger.error(f"获取数据集 {dataset_id} 字段失败: {e}")
        return []

def generate_two_field_combination_alphas(fields):
    """使用2个字段组合生成Alpha表达式"""
    alphas = []
    logger.info(f"开始2字段组合Alpha生成，基础字段数: {len(fields)}")
    
    # 基础操作符
    binary_ops = ["add", "subtract", "multiply", "divide", "correlation", "covariance", "beta", "regression"]
    ops = ["rank", "zscore", "normalize", "ts_rank", "ts_zscore", "ts_mean", "ts_delta"]
    
    # 所有两两字段组合
    field_pairs = list(itertools.combinations(fields, 2))
    logger.info(f"总共有 {len(field_pairs)} 种字段组合")
    
    count = 0
    for (f1, f2) in field_pairs:
        # 1. 二元运算组合
        for op in binary_ops:
            alpha = f"{op}({f1}, {f2})"
            alphas.append(alpha)
            
            # 再套一层基础操作
            for outer_op in ops:
                alphas.append(f"{outer_op}({alpha})")
                count += 1
        
        # 2. 时序组合
        for ts_op in ["ts_corr", "ts_cov", "ts_beta"]:
            for day in [5, 10, 20, 60]:
                alpha = f"{ts_op}({f1}, {f2}, {day})"
                alphas.append(alpha)
                count += 1
        
        # 3. 差分组合
        alpha = f"divide(subtract({f1}, {f2}), add({f1}, {f2}))"
        alphas.append(f"rank({alpha})")
        count += 1
    
    logger.info(f"生成了 {len(alphas)} 个2字段组合Alpha表达式")
    return alphas

def backtest_alpha(api, expression):
    """回测单个Alpha"""
    try:
        settings = {
            "instrumentType": CONFIG["instrumentType"],
            "region": CONFIG["region"],
            "universe": CONFIG["universe"],
            "delay": CONFIG["delay"],
            "decay": 5,
            "neutralization": CONFIG["neutralization"],
            "truncation": 0.08,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "ON",
            "language": "FASTEXPR",
            "visualization": False
        }
        
        simulation_data = {
            "type": "REGULAR",
            "settings": settings,
            "regular": expression
        }
        
        logger.info(f"开始回测: {expression[:60]}...")
        result = api.submit_simulation(simulation_data)
        
        if result and 'id' in result:
            alpha_id = result['id']
            logger.info(f"Alpha提交成功 ID: {alpha_id}")
            
            # 等待回测完成
            status = api.wait_simulation(alpha_id, timeout=300)
            if status == "COMPLETE":
                alpha_info = api.get_alpha(alpha_id)
                return alpha_info
            else:
                logger.warning(f"Alpha {alpha_id} 回测失败 状态: {status}")
                return None
        else:
            logger.error("Alpha提交失败")
            return None
            
    except Exception as e:
        logger.error(f"回测出错: {e}")
        return None

def check_production_correlation(api, alpha_id):
    """检查生产相关性"""
    try:
        corr = api.get_production_correlation(alpha_id)
        if corr is not None:
            logger.info(f"Alpha {alpha_id} 生产相关性: {corr:.4f}")
            return corr
        else:
            logger.warning(f"无法获取Alpha {alpha_id} 生产相关性")
            return None
    except Exception as e:
        logger.error(f"检查生产相关性出错: {e}")
        return None

def main():
    logger.info("="*70)
    logger.info("开始挖掘 USA D1 RAM PPA 类型Alpha")
    logger.info(f"配置: region={CONFIG['region']}, delay={CONFIG['delay']}, neutralization={CONFIG['neutralization']}")
    logger.info(f"目标: 找到 {CONFIG['target_alpha_count']} 个生产相关性 ≤{CONFIG['max_production_correlation']} 的可提交Alpha")
    logger.info("="*70)
    
    try:
        # 初始化API
        api = get_api()
        logger.info("API连接成功")
        
        # 1. 获取目标数据集字段
        fields = get_unlit_pyramid_dataset_fields(api, CONFIG["single_dataset"])
        if not fields:
            logger.error(f"无法获取数据集 {CONFIG['single_dataset']} 字段，退出")
            return
        
        # 2. 预处理字段
        processed_fields = process_datafields(fields)
        logger.info(f"预处理后字段数: {len(processed_fields)}")
        
        # 3. 生成2字段组合Alpha
        alpha_expressions = generate_two_field_combination_alphas(processed_fields[:30])  # 限制前30个字段避免组合爆炸
        
        # 4. 回测并筛选
        valid_alphas = []
        
        for i, expr in enumerate(alpha_expressions):
            if len(valid_alphas) >= CONFIG["target_alpha_count"]:
                logger.info("已找到足够数量的有效Alpha，停止挖掘")
                break
                
            if alpha_exists(expr):
                logger.info(f"跳过已存在的Alpha: {expr[:50]}...")
                continue
                
            logger.info(f"\n[{i+1}/{len(alpha_expressions)}] 处理Alpha")
            
            # 回测
            alpha_info = backtest_alpha(api, expr)
            if not alpha_info:
                continue
                
            # 检查基本指标
            sharpe = alpha_info.get('is', {}).get('sharpe', 0)
            fitness = alpha_info.get('is', {}).get('fitness', 0)
            alpha_id = alpha_info.get('id')
            
            logger.info(f"Alpha {alpha_id}  Sharpe: {sharpe:.3f}  Fitness: {fitness:.3f}")
            
            if sharpe < CONFIG["min_sharpe"]:
                logger.info(f"Sharpe {sharpe:.3f} 低于阈值 {CONFIG['min_sharpe']}，跳过")
                continue
                
            # 检查生产相关性
            prod_corr = check_production_correlation(api, alpha_id)
            if prod_corr is None:
                continue
                
            if prod_corr > CONFIG["max_production_correlation"]:
                logger.info(f"生产相关性 {prod_corr:.3f} 超过上限 {CONFIG['max_production_correlation']}，跳过")
                continue
                
            # 符合所有条件
            valid_alpha = {
                "id": alpha_id,
                "expression": expr,
                "sharpe": sharpe,
                "fitness": fitness,
                "production_correlation": prod_corr,
                "found_at": datetime.now().isoformat()
            }
            valid_alphas.append(valid_alpha)
            
            logger.info(f"✅ 找到符合条件的Alpha #{len(valid_alphas)}! ID: {alpha_id}")
            logger.info(f"   表达式: {expr}")
            logger.info(f"   Sharpe: {sharpe:.3f}  Fitness: {fitness:.3f}  生产相关性: {prod_corr:.3f}")
            
            # 保存到数据库
            save_alpha(
                alpha_expression=expr,
                template_name=f"USA_RAM_PPA_2FIELD",
                settings=CONFIG,
                alpha_id=alpha_id,
                sharpe=sharpe,
                fitness=fitness,
                production_correlation=prod_corr
            )
        
        # 5. 输出最终结果
        logger.info("\n" + "="*70)
        logger.info(f"挖掘完成，总共找到 {len(valid_alphas)} 个符合条件的Alpha")
        logger.info("="*70)
        
        for i, alpha in enumerate(valid_alphas, 1):
            logger.info(f"\nAlpha #{i}:")
            logger.info(f"  ID: {alpha['id']}")
            logger.info(f"  表达式: {alpha['expression']}")
            logger.info(f"  Sharpe: {alpha['sharpe']:.3f}")
            logger.info(f"  Fitness: {alpha['fitness']:.3f}")
            logger.info(f"  生产相关性: {alpha['production_correlation']:.3f}")
        
        # 保存结果到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"results/usa_ram_ppa_alphas_{timestamp}.json"
        os.makedirs("results", exist_ok=True)
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(valid_alphas, f, indent=2, ensure_ascii=False)
            
        logger.info(f"\n结果已保存到: {result_file}")
        
        if len(valid_alphas) >= CONFIG["target_alpha_count"]:
            logger.info("\n✅ 任务完成! 成功找到至少2个符合要求的Alpha")
        else:
            logger.warning(f"\n⚠️  只找到 {len(valid_alphas)} 个Alpha，未达到目标 {CONFIG['target_alpha_count']} 个")
            
    except Exception as e:
        logger.error(f"程序运行异常: {e}", exc_info=True)

if __name__ == "__main__":
    main()