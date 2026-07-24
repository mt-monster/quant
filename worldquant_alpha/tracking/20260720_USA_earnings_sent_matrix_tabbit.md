## 提交记录 (USA/D1, earnings_sent_matrix, tabbit 模板)

- 数据集: earnings_sent_matrix
- 区域/宇宙/延迟: USA / ILLIQUID_MINVOL1M / D1
- 中性化/衰减: STATISTICAL；decay=0；trunc=0.08
- 模板: `ts_op(ts_backfill(field, days1), 252)` + `group_rank(..., industry)`
- 经验: reference/global_mining_experience.md
- 吞吐: multi 满 8、串行、批间冷却

### 已提交
| Alpha ID | Expression | Sharpe | Fitness | ProdCorr | Status |
|---|---|---|---|---|---|
| **vRvg7NzA** | group_rank(ts_zscore(ts_backfill(overall_sentiment_score,252),252),industry) STAT | 2.66 | 1.82 | 0.675 | **OS/ACTIVE**（2026-07-20） |

旁注：PPA `O0xagXjd`（fnd93）亦已 OS/ACTIVE。

### 明日优先队列（本地 PnL SelfCorr vs vRvg7NzA；平台 corr API 当前异常）
| Priority | Alpha ID | Expression | S / F | Self vs vRvg | 备注 |
|---|---|---|---|---|---|
| **1** | **bld3p6Al** | signed_power(group_rank(-ts_rank(method1),industry),0.5) | **2.74 / 1.94** | **0.622** | 最低 Self；标签 next_submit |
| 2 | ZYKLGVex | group_rank(-ts_rank(method1),industry) | 2.91 / 2.05 | 0.637 | 更高 S/F |
| 3 | pwKg0dGv | group_rank(-ts_quantile(method1),industry) | 2.91 / 2.05 | 0.641 | 同量级 |
| 4 | vRvVg73w | group_rank(-ts_av_diff(method1),industry) | 2.81 / 1.95 | 0.660 | backup |
| 5 | omge2EJb | group_rank(-ts_rank(method2),industry) | 3.00 / 2.15 | 0.664 | method2 |
| — | le3XmkYn | group_rank(-ts_zscore(method1)) | 2.67 / 1.85 | **0.747 FAIL** | 提交后失效 |
| — | gJ9p2wVe | group_rank(ts_av_diff(overall)) | 2.80 / 1.93 | **0.874 FAIL** | 与已提交过近 |

### 本轮废弃/弱信号
- 裸 tabbit INDUSTRY：IS 强、ProdCorr 0.83–0.95
- `likelihood_of_neutral_tone`：低竞争但 S≪1.5
- CROWDING+decay2：IS 可过但 ProdCorr 仍高（例 np8bR8Nx≈0.82）且 Self 贴 vRvg7NzA

### 关键发现
1. **group_rank + STATISTICAL** 是 ProdCorr 过闸关键路径。
2. 提交一支后必须用 PnL 复检 SelfCorr；同数据集 `ts_zscore` 变体易 >0.7。
3. **换 ts_op（ts_rank / ts_av_diff）+ 翻转 method1** 比换字段更能降 SelfCorr。
4. 每日 REGULAR 额度约 1；今日已用在 vRvg7NzA。
5. 平台 `check_correlation` / `/correlations/*` 偶发空响应；用 recordsets/pnl 本地相关作筛。
