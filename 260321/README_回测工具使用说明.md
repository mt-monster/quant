# Alpha回测工具使用说明

## 📋 文件说明

### 1. Alpha_candidates.json
包含5个Alpha策略模板，每个模板包含：
- **alpha表达式**：包含占位符的模板表达式
- **template_explanation**：策略说明
- **seed_alpha_settings**：回测参数设置
- **placeholder_candidates**：占位符的候选数据字段

### 2. Alpha_generated_expressions_success.json
已生成成功的Alpha表达式列表（共1000个），可直接用于回测。

---

## 🚀 使用方法

### 环境准备

```bash
# 确保在项目根目录
cd c:/Users/MENGTAO/Desktop/E3/quant

# 配置.env文件（worldquant_alpha/.env）
WQ_USERNAME=your_username
WQ_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=worldquant_alpha
```

### 命令行使用

#### 1. 查看可用模板

```bash
cd 260321
python alpha_backtest_tool.py --list-templates
```

输出示例：
```
可用的Alpha模板:
------------------------------------------------------------

1. trade_when(ts_arg_max(volume,5)==0, group_rank(rank(group_zscore(winsorize(ts_backfill(<fundamental_field/>,63),std=4),subindustry))...
   说明: Generalised volume-spike entry: buy the most attractive stocks within each sub-industry only on the day liquidity surges...
```

#### 2. 回测已生成的表达式

```bash
# 回测所有表达式（共1000个）
python alpha_backtest_tool.py --mode generated

# 回测前20个表达式
python alpha_backtest_tool.py --mode generated --limit 20

# 回测前50个表达式
python alpha_backtest_tool.py --mode generated --limit 50

# 不保存到数据库
python alpha_backtest_tool.py --mode generated --no-db
```

> ⚠️ **注意**：如果不指定 `--limit`，将回测所有1000个表达式，耗时较长（约3-5小时）。建议先用小数量测试。

#### 3. 从模板生成并回测

```bash
# 使用第一个模板生成10个表达式并回测
python alpha_backtest_tool.py --mode template --template "trade_when(ts_arg_max(volume,5)==0..." --limit 10

# 生成20个表达式
python alpha_backtest_tool.py --mode template --template "trade_when(ts_arg_max(volume,5)==0..." --limit 20
```

---

## 📊 回测结果

### 控制台输出

```
============================================================
回测结果分析
============================================================
总回测数: 20
有效回测: 18
优质Alpha (Sharpe>=1.5): 3
成功率: 90.00%

------------------------------------------------------------
Top 10 优质Alpha:
------------------------------------------------------------

1. Sharpe: 2.1234, Fitness: 1.5678, Turnover: 0.2345, Color: GREEN
   表达式: group_rank(ts_delta(winsorize(ts_backfill(star_new_eps_smart_estimate_fq1,63),std=4),21), subindustry) * trade_when...
```

### 结果文件

回测结果自动保存到：
- `backtest_results_YYYYMMDD_HHMMSS.json` - 详细回测结果
- `alpha_backtest.log` - 运行日志

### 数据库保存

回测结果自动保存到MySQL数据库的以下表：
- `alphas_YYYYMMDD` - Alpha表达式和基本信息
- `alpha_results` - 回测结果详情

---

## 🔧 高级用法

### 自定义回测设置

修改 `alpha_backtest_tool.py` 中的 `default_settings`：

```python
default_settings = {
    "instrumentType": "EQUITY",
    "region": "USA",  # 改为 EUR, CHN 等
    "universe": "TOP3000",  # 改为 TOP2500 等
    "delay": 1,
    "decay": 0,
    "neutralization": "SUBINDUSTRY",  # 改为 MARKET, SECTOR 等
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False
}
```

### 使用Python API

```python
from alpha_backtest_tool import AlphaBacktestTool

# 初始化工具
tool = AlphaBacktestTool(data_dir="./260321")

# 回测已生成的表达式
results = tool.backtest_generated_expressions(limit=10)

# 从模板生成并回测
results = tool.backtest_from_template(
    template_key="trade_when(ts_arg_max(volume,5)==0...",
    count=5
)

# 分析结果
analysis = tool.analyze_results(results, sharpe_threshold=1.5)
tool.print_analysis(analysis)

# 导出结果
tool.export_results(results, "my_results.json")
```

---

## 📈 Alpha模板说明

### 模板1: 成交量突破入场
```
trade_when(ts_arg_max(volume,5)==0, 
  group_rank(rank(group_zscore(winsorize(ts_backfill(<fundamental_field/>,63),std=4),subindustry)), 
  densify(bucket(group_rank(cap,sector),range='0.1,1,0.1'))), 
  -1)
```
**策略逻辑**：在成交量激增日买入子行业内最优质的股票，其他时间空仓。

**适用数据**：基本面数据（EPS修正、销售惊喜等）

### 模板2: 成交量低谷反转
```
trade_when(ts_arg_min(volume,10)==0, 
  -group_rank(rank(group_zscore(winsorize(ts_backfill(<price_field/>,44),std=3),industry)), 
  bucket(rank(cap),range='0.1,1,0.1')), 
  -1)
```
**策略逻辑**：在成交量低谷时做空价格最高的股票，做多价格最低的股票。

**适用数据**：价格类数据（收益率、价格动量等）

### 模板3: 盈利动量+成交量确认
```
group_rank(ts_delta(winsorize(ts_backfill(<earnings_field/>,63),std=4),21), subindustry) * 
trade_when(ts_corr(volume,returns,5)>0.5,1,-1)
```
**策略逻辑**：按盈利修正排名，仅在成交量与收益率正相关时持有仓位。

**适用数据**：盈利类数据（EPS惊喜、盈利修正等）

### 模板4: 资产质量+成交量突破
```
-group_rank(ts_rank(ts_decay_linear(winsorize(ts_backfill(<balance_sheet_field/>,115),std=4),10), sector), 
bucket(rank(cap,sector),range='0.2,1,0.2')) * (ts_arg_max(volume,5)==0)
```
**策略逻辑**：在成交量突破日买入资产负债表改善的股票。

**适用数据**：资产负债表数据（净债务、ROE、流动比率等）

### 模板5: 情绪斜率+高流动性
```
group_neutralize(rank(ts_ir(ts_regression(winsorize(ts_backfill(<alternative_field/>,90),std=4), ts_step(1),126,rettype=2))), 
bucket(rank(cap),range='0.1,1,0.1')) * (volume>adv20*1.2)
```
**策略逻辑**：在成交量超过20日均量20%时，持有情绪指标斜率最高的股票。

**适用数据**：另类数据（网页浏览量、新闻情绪、信用风险等）

---

## ⚠️ 注意事项

1. **API限流**：每次回测间隔2秒，避免触发API限流
2. **数据库连接**：确保MySQL服务正在运行
3. **网络连接**：需要稳定的网络连接访问WorldQuant API
4. **回测时间**：每个Alpha回测约需10-30秒
5. **结果有效期**：回测结果基于历史数据，不代表未来表现

---

## 🔍 故障排查

### 问题1: API连接失败
```
ERROR: 获取API失败
```
**解决**：检查`.env`文件中的`WQ_USERNAME`和`WQ_PASSWORD`是否正确

### 问题2: 数据库连接失败
```
ERROR: 创建数据库引擎失败
```
**解决**：确保MySQL服务正在运行，检查数据库配置

### 问题3: 回测超时
```
WARNING: 回测未完成或失败
```
**解决**：可能是API限流，增加sleep时间或减少并发数量

---

## 📞 技术支持

如有问题，请查看：
- `alpha_backtest.log` - 详细运行日志
- `worldquant_alpha/README.md` - 项目主文档
- `项目使用说明.md` - 完整使用指南