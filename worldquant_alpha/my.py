import json
# from world_session_manager import SessionManager
import pandas as pd
import time
import logging

# 配置日志
logging.basicConfig(
    filename='alpha_mining.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class AlphaMining:
    """WorldQuant Brain Alpha 因子挖掘类"""
    
    def __init__(self):
        """初始化 Alpha 挖掘工具"""
        self.session_manager = SessionManager()
    
    def get_datafields(self, searchScope, dataset_id='', search=''):
        """获取数据字段"""
        instrument_type = searchScope['instrumentType']
        region = searchScope['region']
        delay = searchScope['delay']
        universe = searchScope['universe']
        
        if len(search) == 0:
            url_template = (
                "https://api.worldquantbrain.com/data-fields?"
                f"&instrumentType={instrument_type}"
                f"&region={region}&delay={str(delay)}&universe={universe}&dataset.id={dataset_id}&limit=50"
                "&offset={x}"
            )
            
            # 使用会话管理器获取数据
            response = self.session_manager.request_with_retry(
                'get', 
                url_template.format(x=0)
            )
            count = response.json()['count']
        else:
            url_template = (
                "https://api.worldquantbrain.com/data-fields?"
                f"&instrumentType={instrument_type}"
                f"&region={region}&delay={str(delay)}&universe={universe}&limit=50"
                f"&search={search}"
                "&offset={x}"
            )
            count = 100
        
        datafields_list = []
        for x in range(0, count, 50):
            response = self.session_manager.request_with_retry(
                'get', 
                url_template.format(x=x)
            )
            datafields_list.append(response.json()['results'])
        
        datafields_list_flat = [item for sublist in datafields_list for item in sublist]
        datafields_df = pd.DataFrame(datafields_list_flat)
        return datafields_df
    
    def create_alpha_expressions(self, datafields, template_type='simple'):
        """创建 Alpha 表达式"""
        if template_type == 'simple':
            # 简单模板: group_rank(datafield/cap, subindustry)
            return [f'group_rank(({df})/cap, subindustry)' for df in datafields]
        elif template_type == 'complex':
            # 更复杂的模板
            group_compare_op = ['group_rank', 'group_zscore', 'group_neutralize']
            ts_compare_op = ['ts_rank', 'ts_zscore', 'ts_av_diff']
            days = [60, 200]
            group = ['market', 'industry', 'subindustry', 'sector']
            
            alpha_expressions = []
            for gco in group_compare_op:
                for tco in ts_compare_op:
                    for df in datafields:
                        for d in days:
                            for grp in group:
                                alpha_expressions.append(f"{gco}({tco}({df}, {d}), {grp})")
            return alpha_expressions
    
    def create_simulation_config(self, alpha_expression):
        """创建模拟配置"""
        return {
            "type": "REGULAR",
            "settings": {
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
            },
            "regular": alpha_expression
        }
    
    def run_simulation(self, alpha_config, max_attempts=3):
        """运行模拟并等待结果"""
        attempt = 0
        while attempt < max_attempts:
            try:
                # 发送模拟请求
                sim_resp = self.session_manager.request_with_retry(
                    'post',
                    'https://api.worldquantbrain.com/simulations',
                    json=alpha_config
                )
                
                # 获取模拟进度 URL
                sim_progress_url = sim_resp.headers['Location']
                logging.info(f"Simulation started, location: {sim_progress_url}")
                
                # 轮询等待模拟完成
                while True:
                    sim_progress_resp = self.session_manager.request_with_retry(
                        'get',
                        sim_progress_url
                    )
                    
                    retry_after_sec = float(sim_progress_resp.headers.get("Retry-After", 0))
                    if retry_after_sec == 0:  # 模拟完成
                        alpha_result = sim_progress_resp.json()
                        logging.info(f"Simulation completed: {alpha_result.get('alpha')}")
                        return alpha_result
                    
                    time.sleep(retry_after_sec)
            
            except Exception as e:
                logging.error(f"Simulation failed: {str(e)}")
                attempt += 1
                if attempt < max_attempts:
                    logging.info(f"Retrying ({attempt}/{max_attempts})...")
                    time.sleep(15)  # 等待一段时间后重试
                else:
                    logging.error("Max attempts reached, moving to next alpha")
                    return None
    
    def mine_alphas(self, dataset_id, filter_type="MATRIX", start_index=0, end_index=None, template_type='simple'):
        """挖掘 Alpha 因子的主要流程"""
        # 1. 设置搜索范围
        searchScope = {'region': 'USA', 'delay': '1', 'universe': 'TOP3000', 'instrumentType': 'EQUITY'}
        
        # 2. 获取数据字段
        logging.info(f"Fetching datafields from dataset: {dataset_id}")
        datafields_df = self.get_datafields(searchScope, dataset_id=dataset_id)
        
        # 3. 筛选数据字段
        if filter_type:
            datafields_df = datafields_df[datafields_df['type'] == filter_type]
        
        datafields_list = datafields_df['id'].values
        logging.info(f"Found {len(datafields_list)} datafields")
        
        # 4. 创建 Alpha 表达式
        logging.info(f"Creating alpha expressions using template: {template_type}")
        alpha_expressions = self.create_alpha_expressions(datafields_list, template_type)
        
        # 5. 确定要处理的范围
        if end_index is None:
            end_index = len(alpha_expressions)
        
        logging.info(f"Processing alphas from index {start_index} to {end_index}")
        selected_expressions = alpha_expressions[start_index:end_index]
        
        # 6. 批量运行模拟
        results = []
        for i, expression in enumerate(selected_expressions, 1):
            logging.info(f"Processing alpha {i}/{len(selected_expressions)}: {expression}")
            alpha_config = self.create_simulation_config(expression)
            result = self.run_simulation(alpha_config)
            if result:
                results.append({
                    'expression': expression,
                    'alpha_id': result.get('alpha'),
                    'ir': result.get('performance', {}).get('ir'),
                    'sharpe': result.get('performance', {}).get('sharpe')
                })
            
            # 每处理 10 个 alpha 保存一次结果
            if i % 10 == 0:
                self._save_results(results, f"alpha_results_{i}.json")
        
        # 保存最终结果
        self._save_results(results, "alpha_results_final.json")
        return results
    
    def _save_results(self, results, filename):
        """保存结果到文件"""
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        logging.info(f"Results saved to {filename}")


# 使用示例
if __name__ == "__main__":
    miner = AlphaMining()
    
    # 挖掘 fundamental6 数据集中的 Alpha 因子
    results = miner.mine_alphas(
        dataset_id='fundamental6',
        filter_type="MATRIX",
        start_index=0,
        end_index=30000,  # 只处理前 30 个，可以根据需要调整
        template_type='complex' # complex :使用复杂模板 simple:使用简单模板
    )
    
    # 打印结果
    for result in results:
        print(f"Alpha: {result['expression']}")
        print(f"ID: {result['alpha_id']}")
        print(f"IR: {result['ir']}, Sharpe: {result['sharpe']}")
        print("-" * 50)