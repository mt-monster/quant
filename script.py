import numpy as np
from empyrical import max_drawdown, alpha_beta
import empyrical as empyrical
returns = np.array([.01, .02, .03, -.4, -.06, -.02])
benchmark_returns = np.array([.02, .02, .03, -.35, -.05, -.01])

# calculate the max drawdown
max_drawdown(returns)

# calculate alpha and beta
alpha, beta = alpha_beta(returns, benchmark_returns)
print(alpha, beta)
alpha_beta(returns, benchmark_returns)

sharpe_ratio = empyrical.sharpe_ratio(returns, risk_free=0.02, period='daily')
print(f"夏普比率: {sharpe_ratio}")