"""
WorldQuant Brain API常量定义
"""

# API基础URL
API_BASE_URL = 'https://api.worldquantbrain.com'

# 支持的地区
REGIONS = {
    'USA': '美国',
    'CHN': '中国',
    'JPN': '日本',
    'EUR': '欧洲',
    'ASI': '亚洲',
    'GLB': '全球',
    'HKG': '香港',
    'TWN': '台湾',
    'KOR': '韩国',
    'AMR': '美洲',
}

# 支持的工具类型
INSTRUMENT_TYPES = ['EQUITY', 'FUTURES', 'ETF']

# 支持的宇宙
UNIVERSES = [
    'TOP3000',
    'TOP2000', 
    'TOP1000', 
    'TOP1200', 
    'ALL'
]

# 支持的中性化参数
NEUTRALIZATIONS = [
    'MARKET',
    'SECTOR',
    'INDUSTRY', 
    'SUBINDUSTRY', 
    'COUNTRY',
    'RAM'
]

# 基本操作符
BASIC_OPS = ["reverse", "inverse", "rank", "zscore", "quantile", "normalize"]

# 时间序列操作符
TS_OPS = [
    "ts_rank", "ts_zscore", "ts_delta", "ts_sum", "ts_delay",
    "ts_std_dev", "ts_mean", "ts_arg_min", "ts_arg_max", "ts_scale", "ts_quantile"
]

# 所有操作符集合
OPS_SET = BASIC_OPS + TS_OPS

# Alpha颜色定义
ALPHA_COLORS = {
    'GREEN': '绿色 - 高质量',
    'BLUE': '蓝色 - 待评估',
    'YELLOW': '黄色 - 检查失败',
    'RED': '红色 - 问题',
    'PURPLE': '紫色 - 特殊标记'
}

# 返回状态码
STATUS_CODES = {
    200: '成功',
    400: '请求参数错误',
    401: '认证失败',
    403: '权限不足',
    404: '资源不存在',
    429: '请求过多',
    500: '服务器错误'
}

# API请求超时设置
REQUEST_TIMEOUT = 30  # 秒

# 默认重试次数
DEFAULT_MAX_RETRIES = 3

# 默认回测设置
DEFAULT_BACKTEST_SETTINGS = {
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
} 