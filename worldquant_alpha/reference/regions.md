# 区域参数配置

> 各区域的回测参数、特殊规则和注意事项。

---

## 一、区域参数表

### USA

| 参数 | 值 | 说明 |
|------|---|------|
| Region | `USA` | 美国 |
| Universe | `TOP3000` | 流动性前 3000 |
| Delay | `1` (D1) | 1 天延迟 |
| max_trade | `OFF` | 不限制最大交易 |
| Margin 门槛 | **> 5bp** | 低于其他区域 |
| 竞争度 | 中（medium_saturated） | 中等饱和 |
| 支持的 Neutralization | MARKET / SLOW / FAST / SLOW_AND_FAST / CROWDING / REVERSION_AND_MOMENTUM / STATISTICAL |

### ASI

| 参数 | 值 | 说明 |
|------|---|------|
| Region | `ASI` | 亚洲（日/港/澳/新等） |
| Universe | `MINVOL1M` | 最小成交量 1 个月 |
| Delay | `1` (D1) | 1 天延迟 |
| max_trade | **`ON`（强制）** | 必须开启 |
| Margin 门槛 | > 10bp | 标准门槛 |
| 竞争度 | 高（low_saturated） | 相对不饱和 |
| 支持的 Neutralization | MARKET / COUNTRY / SLOW / FAST / SLOW_AND_FAST / CROWDING / REVERSION_AND_MOMENTUM |

**ASI 特殊规则**：
- ⚠️ `max_trade=ON` 是强制性的，不开启会导致无效回测
- COUNTRY 中性化通常是首选（多国市场需消除国家效应）
- Robust Universe Test 返回 Sharpe 与 IS Sharpe 衰减 ≤ 10%
- `ILLIQUID_MINVOL1M` 是替代 universe

### EUR

| 参数 | 值 | 说明 |
|------|---|------|
| Region | `EUR` | 欧洲 |
| Universe | `TOPCS1600` | Top 1600 by country |
| Delay | `1` (D1) | 1 天延迟 |
| max_trade | `OFF` | 不限制最大交易 |
| Margin 门槛 | > 10bp | 标准门槛 |
| 竞争度 | 高（low_saturated） | 相对不饱和 |
| 支持的 Neutralization | MARKET / SLOW / FAST / SLOW_AND_FAST / CROWDING / REVERSION_AND_MOMENTUM / STATISTICAL |

### KOR

| 参数 | 值 | 说明 |
|------|---|------|
| Region | `KOR` | 韩国 |
| Universe | `TOP600` | 流动性前 600 |
| Delay | `1` (D1) | 1 天延迟 |
| max_trade | `OFF` | 不限制最大交易 |
| Margin 门槛 | > 10bp | 标准门槛 |
| 竞争度 | 中低 | 探索较少 |
| 支持的 Neutralization | MARKET / SLOW / FAST / SLOW_AND_FAST / CROWDING / REVERSION_AND_MOMENTUM |

---

## 二、通用参数

所有区域共享的默认参数：

```yaml
language:       FASTEXPR
pasteurization: ON
nan_handling:   ON
decay:          4          # 日更默认；季/年更用 0
test_period:    P0Y0M      # 不留测试期
truncation:     0.08       # 截断 8%
```

---

## 三、Neutralization 说明

| Neut 类型 | 说明 | 适用场景 |
|-----------|------|---------|
| `MARKET` | 全市场中性化 | 默认基线 |
| `SLOW` | 慢速风格中性化 | 低频因子 |
| `FAST` | 快速风格中性化 | 高频因子、事件驱动 |
| `SLOW_AND_FAST` | 双重中性化 | 综合控制 |
| `CROWDING` | 拥挤度中性化 | 避免拥挤信号 |
| `REVERSION_AND_MOMENTUM` | 反转与动量中性化 | 对冲趋势反转 |
| `STATISTICAL` | 统计中性化 | 仅 USA / EUR 支持 |
| `COUNTRY` | 国家中性化 | 仅多国区域（ASI） |

### Neut 遍历优先级

Stage 4 参数优化时的 neut 遍历顺序：

```
1. MARKET（基线）
2. SLOW（低频数据首选）
3. FAST（高频数据首选）
4. SLOW_AND_FAST（如 SLOW/FAST 都有改善）
5. CROWDING（如 ProdCorr 偏高）
6. STATISTICAL（仅 USA/EUR，如其他 neut 不理想）
```

---

## 四、不支持的区域

以下区域当前暂不探索：

| 区域 | 原因 |
|------|------|
| CHN | 数据限制 |
| HKG | 市场特殊性 |
| GLB | 跨国稀释效应，Margin 结构性低 |
| IND | 暂停新提交（竞争度高） |

---

## 五、区域特异性注意事项

### USA
- Margin 门槛最低（> 5bp），其他指标标准不变
- STATISTICAL neut 是 USA 独有（也支持 EUR）
- TOP3000 竞争激烈，ProdCorr 容易偏高

### ASI
- **必须** `max_trade=ON`
- COUNTRY neut 消除日本/澳大利亚/新加坡等国别差异
- MINVOL1M universe 过滤低流动性股票
- Robust Universe Test 是提交前的额外验证

### EUR
- TOPCS1600 按国家分配配额
- 相比 USA 竞争度低，更容易找到低 ProdCorr 的 Alpha
- 与 USA 类似的 neut 支持（含 STATISTICAL）

### KOR
- TOP600 universe 较小
- 单一国家市场，不需要 COUNTRY neut
- 探索较少，可能有更多机会
