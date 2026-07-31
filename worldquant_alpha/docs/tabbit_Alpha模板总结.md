总结模板

该帖子分享了一个针对 **Earnings（财报情绪）类数据**的低阶 Alpha 模板，核心理念是利用 `ts_backfill` 回填低频事件数据，配合时序算子构建低相关性的因子。以下是要点总结。

### **核心模板**

```
<time_series_operator/>(ts_backfill(<data_field/>,<days_1/>), <days_2/>)
```

### **参数说明**

- **data_field**：使用 `USA/D1/ILLIQUID_MINVOL1M/earnings_sent_matrix`（仅含 7 个数据，但 USA、GLB、EUR 三个区域均有覆盖）。
- **time_series_operator**：无严格限制，作者使用过的有 `ts_arg_max`、`ts_av_diff`、`ts_quantile`、`ts_scale`、`ts_zscore` 等。
- **days_1**：取 10 或 252。
- **days_2**：取 252。
- **Neutralization 与 Universe** 可自行选择。作者提示，USA 区域使用 `ILLIQUID_MINVOL1M` 作为 Universe 更易出货，且相关性更低。

### **变体思路**

作者在回测中发现 `ts_mean` 可以替换 `ts_backfill`（猜想 `ts_sum` 亦可），即：

```
<time_series_operator/>(ts_mean(<data_field/>,<days_1/>), <days_2/>)
```

由于这是低阶模板，回测后可能出现相关性偏高的情况，可以在外层再嵌套一个时序算子以降低相关性：

```
<time_series_operator/>(<time_series_operator/>(ts_backfill(<data_field/>,<days_1/>), <days_2/>),<days_2/>)
```

### **核心技巧：抢占新数据先机**

作者仅回测约 2000 次便轻松提交了 6 个 RA。其"出货"容易的关键在于选择了**新推出的数据集**——Global Earnings Call Sentiment Matrix 的 Alpha 数量为 0，大概率是平台新数据，相关性普遍很低，因此可轻松提交。

作者强调：由于相关性限制，同一个 Alpha 只有第一个人能提交，所以平台推出新数据时抢占先机十分重要。建议定期查看 Data 页面，留意其他区域类型的新数据，趁窗口期快速提交。

### **已验证区域与表现**

- USA（`positive_sentiment_probability_3`）和 EUR（`sentiment_weighting_method1`）各点亮了 Earnings 类别。
- GLB 区域模板通用，但因回测较慢尚未开始验证。
- 附赠了一个 PPA（IS 表现较好，但 Investability constrained 偏低，对 Combine 提升意义有限，可尝试调优）。

### **评论区关键讨论**

- **`ts_backfill` vs `ts_mean`**：earnings 数据是低频事件型，理论上 backfill 更合理（信息持续到下次发布），但 `ts_mean` 也能跑通，说明信号本身鲁棒性不错。
- **days_1 取值差异**：10 天窗口更灵敏但可能引入噪音，252 天窗口更平滑但滞后；earnings 一年仅四次，短窗口与长窗口对信号捕捉效果差异较大。
- **算子选择**：不同算子效果差异明显，可尝试 `ts_rank`、`ts_zscore` 等，并叠加多字段（如 `negative_sentiment_probability`）做多空组合。
- **单字段预处理**：评论区有用户反馈，对单字段先做预处理，出信号概率大幅增加。

*内容由 AI 生成仅供参考*