解释每个算子的含义和用法

我先读取页面的完整内容，以便准确解释每个算子。

下面我按照页面上算子的分类顺序，逐类讲解每个算子的含义与用法。WorldQuant BRAIN 平台的算子（Operator）是构建 Alpha 表达式的基本构件，每个算子作用于数据字段，产生可用于交易信号的数值。页面顶部还提示，更复杂的算子需要在 Expert、Master、Grandmaster 等 Genius 等级解锁。

### **一、算术类算子（Arithmetic）**

这类算子执行基本的逐元素数学运算，是最常用的基础构件。

| 算子 | 含义与用法 |
|---|---|
| `abs(x)` | 返回 x 的绝对值，去掉负号。用于将所有值转为非负数。 |
| `add(x, y, filter=false)` 或 `x + y` | 逐元素相加，支持两个及以上输入。设 `filter=true` 可在求和前把 NaN 当作 0 处理，避免 NaN 污染结果。 |
| `densify(x)` | 把一个分组字段中众多桶（bucket）压缩为仅保留实际存在的桶，提升分组字段运算效率。 |
| `divide(x, y)` 或 `x / y` | 返回 x/y。除以零会报错，建议写 `divide(x, add(y, 0.0001))` 加一个小量防止报错。 |
| `inverse(x)` | 返回 1/x。x=0 时报错，可用 `inverse(add(x, 0.0001))` 规避。 |
| `log(x)` | 自然对数。常用于对正值数据做压缩变换，降低量纲影响。 |
| `max(x, y, ..)` | 多个输入中的最大值，至少需 2 个输入。 |
| `min(x, y, ..)` | 多个输入中的最小值，至少需 2 个输入。 |
| `multiply(x, y, ..., filter=false)` 或 `x * y` | 逐元素相乘，支持多输入。`filter=true` 时把 NaN 当 0 处理后再乘。 |
| `pasteurize(x)` | 若 x 为 INF 或对应标的不在 Alpha  universe 中，则置为 NaN。可用于剔除异常值和无效标的。例如输入 `(2,3,5,INF,3,8,10)`，其中 10 不在 universe，输出 `(2,3,5,NaN,3,8,NaN)`。 |
| `power(x, y)` | 返回 x^y。注意 y 为非整数时可能丢失 x 的符号，需保留符号时改用 `signed_power`。 |
| `reverse(x)` | 即取负 `-x`，反转信号方向。 |
| `sign(x)` | 返回符号函数：正数为 +1，负数为 -1，零为 0，NaN 返回 NaN。仅保留方向信息。 |
| `signed_power(x, y)` | x^y 且结果保留 x 的符号，适合在保留方向的同时做幂变换。 |
| `sqrt(x)` | 非负平方根，等价 `power(x, 0.5)`。x<0 时未定义，需保留符号时用 `signed_power(x, 0.5)`。 |
| `subtract(x, y, filter=false)` 或 `x - y` | 从左到右逐元素相减，支持多输入。`filter=true` 时把 NaN 当 0。 |

### **二、逻辑类算子（Logical）**

这类算子基于条件判断输出 1（真）或 0（假），用于构建条件信号或筛选逻辑。

| 算子 | 含义与用法 |
|---|---|
| `and(input1, input2)` | 两个输入都为 1（真）时返回 1，否则返回 0。 |
| `if_else(input1, input2, input3)` | 条件判断：input1 为真返回 input2，为假返回 input3。是构建分支信号的核心算子。 |
| `input1 < input2` | 小于判断，真返回 1，假返回 0。 |
| `input1 <= input2` | 小于等于判断。 |
| `input1 == input2` | 相等判断。 |
| `input1 > input2` | 大于判断。 |
| `input1 >= input2` | 大于等于判断。 |
| `input1 != input2` | 不等判断，不同返回 1。 |
| `is_nan(input)` | 判断是否为 NaN，是返回 1，否则返回 0。常用于检测缺失值。 |
| `not(x)` | 逻辑取反：x 为 1 返回 0，x 为 0 返回 1。 |
| `or(input1, input2)` | 任一输入为 1（真）即返回 1，否则返回 0。 |

### **三、时间序列类算子（Time Series）**

这是数量最多的一类，用于在历史时间窗口（过去 d 天）上做统计计算，捕捉动量、均值回归、波动等时序特征。

| 算子 | 含义与用法 |
|---|---|
| `days_from_last_change(x)` | 计算自 x 上一次发生变化以来经过的天数，用于度量数据的更新频率。 |
| `hump(x, hump=0.01)` | 限制输入变化的幅度与频次，从而降低换手率（turnover）。hump 参数控制阈值。 |
| `kth_element(x, d, k, ignore="NaN")` | 在过去 d 天中取第 k 个值，可选忽略某些值（如 NaN）。常用于回填缺失数据。 |
| `last_diff_value(x, d)` | 返回过去 d 天内与当前值不同的最近一个 x 值。 |
| `ts_arg_max(x, d)` | 返回过去 d 天内最大值出现距今的天数。今天最大返回 0，昨天最大返回 1，以此类推。 |
| `ts_arg_min(x, d)` | 返回过去 d 天内最小值出现距今的天数。 |
| `ts_av_diff(x, d)` | 返回 x 与其过去 d 天均值之差（忽略 NaN），即 `x - ts_mean(x, d)`。用于度量相对均值的偏离。 |
| `ts_backfill(x, lookback=d, k=1)` | 用回看窗口内最近的合法值替换 NaN，提升数据覆盖率、降低缺失风险。 |
| `ts_corr(x, y, d)` | 计算 x 与 y 在过去 d 天的皮尔逊相关系数，衡量两者同向运动程度。 |
| `ts_count_nans(x, d)` | 统计过去 d 天内 NaN 值的个数。 |
| `ts_covariance(y, x, d)` | 计算 x、y 在过去 d 天的协方差，衡量两者共同变动。 |
| `ts_decay_linear(x, d, dense=false)` | 对过去 d 天做线性衰减加权平均，越近权重越大，平滑数据并降低旧值与缺失值影响。 |
| `ts_delay(x, d)` | 返回 x 在 d 天前的值，用于获取历史数据点。 |
| `ts_delta(x, d)` | 返回 x 与其 d 天前值之差，即 `x - ts_delay(x, d)`，衡量动量/变化。 |
| `ts_ir(x, d)` | 信息比率，等于 `ts_mean(x, d) / ts_std_dev(x, d)`，衡量均值相对波动的稳定性。 |
| `ts_kurtosis(x, d)` | 过去 d 天的峰度（kurtosis），衡量分布尾部厚度。 |
| `ts_max_diff(x, d)` | 返回 `x - ts_max(x, d)`，即当前值与窗口最大值之差。 |
| `ts_mean(x, d)` | 过去 d 天的简单均值。 |
| `ts_product(x, d)` | 过去 d 天值的连乘积，可用于几何均值或复利收益计算。 |
| `ts_quantile(x, d, driver="gaussian")` | 先计算 `ts_rank`，再用指定分布（默认高斯）的反累积分布函数变换，用于归一化或重塑分布形状。 |
| `ts_rank(x, d, constant=0)` | 在过去 d 天内对当前值做排名（可加常数偏移），输出相对位置，用于时序归一化。 |
| `ts_regression(y, x, d, lag=0, rettype=0)` | 对 y、x 做滚动回归（窗口 d 天），通过 rettype 返回不同回归参数（如斜率、残差等）。 |
| `ts_returns(x, d, mode=1)` | 返回 x 的相对变化（收益率），mode 控制具体计算方式。 |
| `ts_scale(x, d, constant=0)` | 基于过去 d 天的极值把序列缩放到 0–1 区间，可加常数偏移。 |
| `ts_std_dev(x, d)` | 过去 d 天的标准差，衡量波动。 |
| `ts_step(1)` | 返回按天递增的计数器，每过一天加 1。 |
| `ts_sum(x, d)` | 过去 d 天值之和。 |
| `ts_target_tvr_decay(x, lambda_min=0, lambda_max=1, target_tvr=0.1)` | 在 `ts_decay` 基础上调节衰减权重，使换手率逼近目标值 target_tvr，权重范围由 lambda_min/max 控制。 |
| `ts_target_tvr_hump(x, lambda_min=0, lambda_max=1, target_tvr=0.1)` | 调节 `hump` 参数使换手率逼近目标值。 |
| `ts_zscore(x, d)` | 过去 d 天的 Z 分数，即 `(x - ts_mean) / ts_std`，衡量当前值偏离均值多少个标准差。 |

### **四、截面类算子（Cross Sectional）**

这类算子在同一日对所有标的（instruments）做横截面运算，用于标准化、排名、去极值等，是消除市场整体偏差的关键工具。

| 算子 | 含义与用法 |
|---|---|
| `normalize(x, useStd=false, limit=0.0)` | 减去市场均值做中心化；`useStd=true` 时再除以横截面标准差，并可把结果截断到 [-limit, +limit]。NaN 在均值/标准差中被忽略。 |
| `quantile(x, driver=gaussian, sigma=1.0)` | 对 Alpha 值做排名与平移后，套用指定分布（gaussian、cauchy、uniform）变换以降低异常值影响，sigma 控制输出尺度。 |
| `rank(x, rate=2)` | 在所有标的中对 x 排名，输出 0.0–1.0 之间均匀分布的值。用于归一化并降低异常值影响。 |
| `scale(x, scale=1, longscale=1, shortscale=1)` | 缩放使所有标的绝对值之和等于指定 book size；longscale、shortscale 可分别调整多头与空头权重。 |
| `winsorize(x, std=4)` | 把超出均值 ±std 个标准差的值压到边界，降低极端值影响。std 取 2、3、4、5 分别约剔除 4.5%、0.27%、0.01%、0.0001% 的极端值。 |
| `zscore(x)` | 横截面 Z 分数，度量每个值相对全市场均值的标准差距离。 |

### **五、向量类算子（Vector）**

当数据字段本身是向量（如一条记录里多个子项）时，用这类算子把向量聚合为单一标量值。

| 算子 | 含义与用法 |
|---|---|
| `vec_avg(x)` | 向量字段中所有元素的均值，把向量转为单一矩阵值。 |
| `vec_count(x)` | 向量字段中元素的个数。 |
| `vec_max(x)` | 向量字段中的最大值。 |
| `vec_min(x)` | 向量字段中的最小值。 |
| `vec_range(x)` | 向量字段中最大值与最小值之差。 |
| `vec_stddev(x)` | 向量字段中元素的标准差。 |
| `vec_sum(x)` | 向量字段中所有值之和。 |

### **六、变换类算子（Transformational）**

这类算子对信号做结构性变换，如分桶、条件交易、统计生成等，用于精细控制信号行为。

| 算子 | 含义与用法 |
|---|---|
| `bucket(rank(x), range="0,1,0.1", skipBoth=False, NaNGroup=False)` 或 `bucket(rank(x), buckets="2,5,6,7,10", ...)` | 基于排名值把数据分成自定义桶（区间），产出的分组可用于 `group_neutralize`、`group_rank`、`group_zscore` 等分组算子。range 方式按等距划分，buckets 方式按指定边界划分。 |
| `generate_stats(alpha)` | 为 IS（样本内）期间每天计算各 Alpha 的统计量。输入形状 (A×D×I)，输出 (S×D×A)，S 为统计量个数。常用于 Combo Alpha 的统计分析。 |
| `tail(x, lower=0, upper=0, newval=0)` | 当 x 严格大于 lower 且严格小于 upper 时返回 newval，否则返回 x。lower/upper/newval 须为常数，用于压缩中间值或剔除噪声区间。 |
| `trade_when(x, y, z)` | 仅在条件 x 满足时更新 Alpha 值为 y，否则保留前值；z 作为退出条件可赋 NaN 平仓。用于降低换手率、控制交易时机。 |

### **七、分组类算子（Group）**

这类算子在指定分组（行业、板块、国家或自定义桶）内做运算，用于剥离组内共性、比较组内相对位置。

| 算子 | 含义与用法 |
|---|---|
| `combo_a(alpha, nlength=250, mode='algo1')` | 把多个 Alpha 信号加权合成单一输出，权重依据各 Alpha 近 nlength 天的历史收益与波动权衡。mode 选 algo1/algo2/algo3，不同模式对收益与稳定性的侧重不同。 |
| `group_backfill(x, group, d, std=4.0)` | 用同组内非 NaN 值的缩尾均值（winsorized mean，std 控制截断倍数）填充缺失值，窗口为过去 d 天。 |
| `group_cartesian_product(g1, g2)` | 把两个分组合并成一个，新分组数为原两组数之积，用于构造更细粒度的交叉分组。 |
| `group_count(x, group)` | 统计同组内 x 有效（非 NaN）的标的数量。x=1 时即每组标的总数，可改善权重覆盖、降低回撤风险。 |
| `group_mean(x, weight, group)` | 计算每组内数据字段的调和均值。 |
| `group_neutralize(x, group)` | 在每组内减去组均值做中性化，剥离行业/板块等共性暴露。 |
| `group_rank(x, group)` | 在每组内对元素排名，输出 0.0–1.0，用于组内相对比较。 |
| `group_scale(x, group)` | 在每组内把值归一化到 0–1，使不同组间可比。 |
| `group_std_dev(x, group)` | 每组内所有元素等于该组的标准差。 |
| `group_sum(x, group)` | 同组内所有标的 x 值之和。 |
| `group_zscore(x, group)` | 每组内的 Z 分数，度量每个值相对组均值的标准差距离。 |

### **八、特殊类算子（Special）**

| 算子 | 含义与用法 |
|---|---|
| `in` | Selection 模式下的筛选算子，用于从一组标的中选取符合条件的子集。 |
| `self_corr(input)` | 输入 (D×N) 矩阵、回看 K 天，输出 (D×N×N) 矩阵，其中每个元素表示两个序列在窗口内的相关性。用于计算标的两两相关性。 |
| `universe_size` | 返回当前 universe（标的池）的规模。 |

### **九、归约类算子（Reduce）**

这一类算子对二维或三维矩阵的最后一维做归约（聚合），把多值压缩为单一值。输入若为 (D×N) 则输出 (D×1)，若为 (D×N×N) 则输出 (D×N×1)。归约函数作用于最后一维 `input(I, 0:N)`。

| 算子 | 含义与用法 |
|---|---|
| `reduce_avg(input, threshold=0)` | 非 NaN 元素的均值。threshold 为有效值最少个数要求，不足则输出 NaN，0 表示不限制。 |
| `reduce_choose(input, nth, ignoreNan=true)` | 选取数组中第 nth 个元素，找不到返回 NaN。ignoreNan 控制是否忽略 NaN。 |
| `reduce_count(input, threshold)` | 统计数组中大于 threshold 的元素个数。 |
| `reduce_ir(input)` | 数组内值的信息比率（均值/标准差）。 |
| `reduce_kurtosis(input)` | 数组内值的峰度。 |
| `reduce_max(input)` | 数组内元素的最大值。 |
| `reduce_min(input)` | 数组内元素的最小值。 |
| `reduce_norm(input)` | 数组内元素绝对值之和（L1 范数）。 |
| `reduce_percentage(input, percentage=0.5)` | 返回排序数组中指定百分位对应的值，如 0.5 即中位数。 |
| `reduce_powersum(input, constant=2, precise=false)` | 幂和 `sum(power(x, constant))`，constant>4 时可用 precise 提高精度。 |
| `reduce_range(input)` | 数组内值的极差（最大减最小），无有效值返回 NaN。 |
| `reduce_skewness(input)` | 数组内值的偏度。 |
| `reduce_stddev(input, threshold=0)` | 数组内值的标准差。threshold 为有效值最小比例要求，不足返回 NaN。 |
| `reduce_sum(input)` | 数组内元素之和。 |

---

以上算子是构建 Alpha 表达式的基础积木。实际使用时，通常会把数据字段代入算子，并嵌套组合——例如用时间序列算子捕捉动量，用截面算子做标准化，再用 `trade_when` 控制换手，用分组算子剥离行业暴露，层层组合形成最终的交易信号。Scope 列中的 base 表示基础算子人人可用，genius 表示需要达到相应 Genius 等级才能解锁。

*内容由 AI 生成仅供参考*