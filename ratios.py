import quantstats as qs
import akshare as ak  # pip install akshare
import pandas as pd
import numpy as np

import warnings

warnings.filterwarnings("ignore")
qs.extend_pandas()  # 开启pandas拓展配置

# 方法二用akshare 获取股票日度回报率,当作量化策略的回报
stock_us_hist_df = ak.stock_us_hist(symbol='105.META', period="daily", adjust="qfq", start_date="20240101",
                                    end_date="20241231", )
stock_close = stock_us_hist_df[['日期', '收盘']]
stock_close['日期'] = pd.to_datetime(stock_close['日期'])
stock_close['return'] = stock_close['收盘'].pct_change()
stock_index = stock_close.set_index('日期')
stock = stock_index['return'].dropna()
# 获取基准日度回报率
index_sp500_df = ak.index_us_stock_sina(symbol=".INX")  # 标音500
index_sp500_df['date'] = pd.to_datetime(index_sp500_df['date'])
index_sp500_df = index_sp500_df.query('date >= "2024-01" & date <= "2024-12-31"')
index_sp500_df['return'] = index_sp500_df['close'].pct_change()
index_sp500_df = index_sp500_df.set_index('date')
benchmark = index_sp500_df['return'].dropna()

stats = qs.stats.sharpe(stock)

stock.sharpe()

qs.plots.snapshot(stock, title='My Quant Stats Report', show=True)
qs.reports.html(stock, benchmark=benchmark, output='output.html')
