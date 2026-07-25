# WQ Brain PPA 挖掘经验总结

## 一、核心范式: spread + group_zscore + returns 反转

### 发现过程 (V2→V9→V17→V29)
1. **纯 spread**: S=1.7, IS_LADDER=1.37 — 不够
2. **+close 反转**: S=1.84, IS_LADDER=1.58 — 卡阈值(严格>1.58)
3. **🏆 returns 替代 close**: S=2.23, IS_LADDER=2.12 — **突破!** returns 捕捉日频变化, close 太粘性
4. **+group_zscore(industry)**: S=2.1-2.2, IS_LADDER 2.1+ — 行业标准化提升稳定性
5. **跨区域验证**: IND analyst39 同范式 S=1.81, IS_LADDER=2.69 — 范式通用

### 最终表达式
```
scale(rank(group_zscore(ts_zscore(
    subtract(ts_mean(ts_backfill(B,66),22), ts_mean(ts_backfill(A,66),22), filter=true),
    189), industry)))
+ scale(-rank(ts_zscore(returns, 42))) * 0.35
```
decay=4, neutralization=SUBINDUSTRY, truncation=0.08, testPeriod=P6Y

### 关键要素
- **spread (2字段差值)**: 经济意义信号 (基金持仓变化、EPS加速度等)
- **ts_mean(22) + ts_backfill(66)**: 平滑+回填降噪
- **ts_zscore(189)**: 9个月时序标准化窗口
- **group_zscore(industry)**: 行业内标准化消除偏差
- **returns 反转 (非close!)**: IS_LADDER 提升 0.54 的核心
- **低 decay (4-5)**: 配合 returns 使 IS_LADDER 飙升
- **weight 0.35**: 基金与反转信号最佳配比

## 二、闸门规则

### 廉价闸门 (PC 等待前)
- Sharpe ≥ 1.58 | Fitness ≥ 1.00 | TVR ∈ [5%, 20%] | Margin > 5bp | Returns > 5%
- 平台检查无 FAIL

### 硬闸门 (PC 等待后)
- **PROD_CORRELATION < 0.70** (用户绝对红线)
- SELF_CORRELATION < 0.50
- 复校廉价闸门

### 平台检查细节
- IS_LADDER_SHARPE 阈值: 严格 **>1.58** (显示 1.58 仍 FAIL)
- 含价格信号的 alpha 触发 IS_LADDER_SHARPE; 纯基金信号触发 LOW_2Y_SHARPE
- testPeriod P4Y/P3Y 不改变 IS_LADDER 计算; truncation 不影响 IS_LADDER
- SECTOR/MARKET 中性化大幅降低 IS_LADDER (不要用)
- hump 对组合信号有破坏性 (即使 0.001 也摧毁信号)

## 三、API 要点
- `subtract()` 支持 filter=true; `divide()` 不支持
- `ts_regression(A,B,n).residual` 语法无效
- `hump(x, hump=0.01)` 必须用命名参数
- **并发模型 = Token-Bucket（非固定槽）**: 突发 C≈7；提交间隔≥18s；批间≥45s；multi-sim=1 令牌
- **永远保证 8 路进程有回测任务**（`fleet_keeper.py` 常驻）；共享 `submit_gate`；禁齐射
- 429 风暴可临时 8→7→6→5→4，稳定后立刻补回 8
- 单进程=浪费令牌；轮询空档必须多进程吃桶
- 入口: `multi_sim.run_multi_batch` + `submit_gate`；规则见 `brain-multi-sim.mdc`
- 401 自动重认证 (_reauth())
- testPeriod 最大 P6Y0M0D
- 429 退避: `submit_gate.backoff_429`（≈30s+ refill），勿短退避打空桶
- TaskStop 会制造孤儿模拟, 只能等其自行释放
- VECTOR/event 字段需 vec_avg() 转标量再 ts_*；MATRIX 可直接 ts_backfill
- IND 数据集通过 pyramidMultiplier=1.5 判断未点亮 (非 PM 字段)

## 四、已提交 PPA Alpha (共 8 个)

| PID | Region | Sharpe | IS_LADDER | PC | 信号 |
|-----|--------|--------|-----------|-----|------|
| MPQVZRnk | USA | 2.230 | 2.12 | — | institutions18 ret_z42_d4 |
| O0ZgzM0Y | USA | 2.180 | 2.03 | — | institutions18 ret_z42_d5 |
| gJMLdzGM | USA | 2.090 | 2.02 | — | institutions18 ret_z21_d6 |
| blqg2NLM | USA | 2.160 | 2.12 | — | institutions18 z168_ret_z42_d4 |
| O0ZXmlLp | USA | 2.170 | PASS | — | gz_industry_z189_z21_w0.35_d5 |
| akn9Wrpx | USA | 2.220 | PASS | — | gz_industry_z189_z21_w0.35_d4 |
| 1YzLbZzQ | IND | 1.810 | 2.69 | 0.6928 | analyst39 eps_ttm_vs_q_gzi_r21_w0.45_d3 |
| pwKEAzKj | IND | 1.750 | 2.56 | 0.6978 | analyst39 eps_ttm_vs_q_gzi_r21_w0.5_d5 |

## 五、全区域挖掘结论

| 区域 | Universe | 数据集 | 最佳 S | 状态 |
|------|----------|--------|--------|------|
| USA | TOP200 | institutions18 | 2.23 | ✅ 6 PPA |
| IND | TOP500 | analyst39 | 1.81 | ✅ 2 PPA |
| ASI | MINVOL1M | ai_news_scores | 0.68 | ❌ 信号无效 |
| CHN | TOP2000U | continuation_score | 0.62 | ❌ 信号弱 |
| KOR | TOP600 | pattern_scores | 0.57 | ❌ 信号弱 |
| EUR | TOP400 | — | — | ❌ 无未点亮 |
| HKG | TOP800 | — | — | ❌ 无未点亮 |
| MEA | TOP300 | — | — | ❌ 无未点亮 |
| GLB | TOP3000 | — | — | ❌ 无数据 |

**结论**: 只有 USA (institutions18) 和 IND (analyst39) 能产出有效 PPA。其他区域信号太弱或已全部点亮。

## 六、经验教训

### 信号构建
- **returns 反转 >> close 反转**: IS_LADDER 从 1.58→2.12, 因为 returns 日频变化 vs close 太粘性
- **纯 returns 信号 TVR 天然过高** (27-83%), 无法不损害信号降到 <20%; 必须与基金信号组合
- **纯 close 信号 Sharpe 过低** (S≤0.58); 必须与基金信号组合
- **group_zscore 消除行业偏差** 但可能增加 SELF_CORRELATION; weight≥0.35 可通过 SC
- **ts_delta 动量信号 Fitness 天然偏低** (0.92-0.98), 难以达到 1.0 阈值

### 数据集选择
- **MATRIX 字段优先**: 可直接 ts_backfill; VECTOR/event 字段需 vec_avg 转换
- **成熟数据集更有效**: analyst39 (12034 alphas) > 其他小众数据集
- **2字段需有经济意义**: 基金持仓 cur vs pre、EPS TTM vs 季度、利润率当前 vs 历史均值
- **coverage > 0.5**: 低覆盖率数据集信号太弱
- **institutions20 sq**: IS_LADDER PASS 但 Sharpe≤1.5, 近2年好但整体不够
- **fundamental6**: 纯财务指标 spread 信号弱 (S≤1.01)

### 参数调优
- **decay 是 TVR/LAD 权衡的核心**: 高 decay 降 TVR 但牺牲 Sharpe 和 IS_LADDER
- **weight 0.35 是甜点**: 0.30 时 SC 容易 FAIL, 0.40+ 时 TVR 可能超标
- **z21 returns 通常优于 z42**: IS_LADDER 更高 (2.19 vs 2.05)

## 七、用户规则
- ⚠️ **挖出 alpha 后只罗列候选, 不自动提交, 由用户手动提交** (2026-07-22 起)
- 可设属性 (GREEN/tags READY_MANUAL)，但绝不平台 Submit
- PC 未出或 PC≥0.70 禁止纳入 ready；彼此相关 &lt;0.4
- ⚠️ **每类回测任务都要建立每小时进度汇报自动化** (2026-07-23 起)
- ⚠️ **进度汇报必须带 ETA**（各进程 batch、预计结束时刻；舰队会续补，整体终点=ready 10/10）(2026-07-25)
- 不要使用 trade_when / add / multiply 操作符（含二元 + *）
- 操作符数量 &lt;6
- ⚠️ **回测必须真 multi-sim + submit_gate；永远保证 8 路进程有任务** (2026-07-25，`fleet_keeper.py`)
- 每10轮回测进行 alpha 表达式多样性评估
- ⚠️ **终端/日志禁止中文乱码** (2026-07-25 起)：Windows 默认 stdout=GBK，Cursor 按 UTF-8 读 → `淘汰` 变 `��̭`。已在 `submit_gate._force_utf8_stdio()` 统一修复；新独立脚本须在打日志前 `sys.stdout/stderr.reconfigure(encoding="utf-8")`。规则见 `windows-utf8-logging.mdc`。改完需重启进程才生效。

## 八、并发/舰队经验 (2026-07-25 定稿)

1. 探针报告：Token-Bucket C≈7，间隔≥15–20s，禁齐射
2. 实现：`submit_gate.py` 跨进程 18s 匀速；`multi_sim`/`wd_lib_wrapper` 全覆盖
3. 单进程=浪费；V46–V53 共 **8 路**错峰+共享闸门实测可正常回测、观察窗无 429
4. 不稳则阶梯降级 8→7→6→5→4（`fleet_scale.py`）
5. 工具：`scan_tri_job.py` / `launch_tri_fleet.py` / `fleet_scale.py` / `tri_track.py`

## 九、日志编码 (2026-07-25)

- **现象**：`PC=0.9523 ��̭`、`WqApiSimple ��֤�ɹ�`（实为「淘汰」「认证成功」）
- **根因**：Windows Python `stdout=gbk`，Cursor 终端按 UTF-8 捕获
- **修复**：`submit_gate.py` 模块加载时 `_force_utf8_stdio()`；经 multi_sim / wd_lib_wrapper 的脚本自动生效
- **用户要求**：以后看到的日志都不允许有乱码；勿用删中文躲问题
