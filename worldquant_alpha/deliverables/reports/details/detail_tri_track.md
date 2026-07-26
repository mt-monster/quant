# tri_track 独立账号详情

> ML88164 独立账号 α 产出与回测指标
> 来源：原报告对应章节自动提取

## 六、tri_track 独立账号详情 (🛡️ ML88164)

| 维度 | 数值 |
|---|---|
| 账号 | **ML88164** (独立 gmail/tabbit 体系，与主账号 mthyzx@126.com **令牌互不干扰**) |
| 并发模型 | CONCURRENCY=3，三轨并行 |
| 任务结构 | 8 分片 × 10 任务 = **80 变体**，每片约 10 任务 |
| 三轨方向 | **explore** (option8/fundamental2/pv13 低占用)、**improve** (SubU FAIL 数据)、**misc** (analyst4 低占用) |
| 已提交 alpha | **71** 个  |
| 提交结果 | ✅ submitted=71 / ❌ failed=0 |
| 最佳 Sharpe | **3.54** |
| 分轨分布 | explore 23 / improve 25 / misc 0 |
| 时间范围 | ? ~ ? |
| 结果文件 | `tri_track_undug_results.csv` + `tri_track_undug_checkpoint.json` |
| 进度日志 | `tri_track_undug_progress.log` (存在) |
| 分片进度 | shard 4/8 已完成 (56→80), shard 5/8 已完成 (57→80), 其余分片在飞 |
| 预期完成 | **07-28 06:20** (基于每分片 ~300s × 6 剩余 / CONCURRENCY=3, 粗估) |
| 信号举例 | `unsystematic_risk_last_90_days` zscore × subindustry / `correlation_last_360_days_spy` flip / `pcr_vol_60` 救援 |

> ✅ **回测指标已接入**：`tri_track_undug_checkpoint.json` 含每个 alpha 的 IS 详情。

---