# V39b PASS_CHEAP 候选提交清单

> 生成时间：2026-07-24 12:22  |  来源：`v39b_sub_micro_checkpoint.json`
> 数据说明：scan_v39b 是「不提交」评估扫描；以下 10 个变体通过全部硬闸门，但 sub_universe 略超限制 → 被标 `PASS_CHEAP`。`sub_univ`/`sub_limit` 取自 WQ 模拟 API 返回的 `is` 字段（即 WQ 后台真实值），需人工确认后提交。

## 汇总（按 Sharpe 降序）

| # | label | field | W | neut | decay | trunc | S | F | tvr | sub_univ/lim | 超标 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gz_t2_b66z189_TOP3000_d2_SEC_t1 | eur_top_value_2 | 189 | SECTOR | 2 | 0.01 | 2.18 | 1.8 | 0.1187 | 1.08/0.94 | YES |
| 2 | gz_t2_b66z189_TOP3000_d2_SEC_t12 | eur_top_value_2 | 189 | SECTOR | 2 | 0.12 | 2.17 | 1.79 | 0.1193 | 1.08/0.94 | YES |
| 3 | gz_t2_b66z189_TOP3000_d2_IND_t1 | eur_top_value_2 | 189 | INDUSTRY | 2 | 0.01 | 2.13 | 1.75 | 0.1145 | 0.98/0.92 | YES |
| 4 | gz_t2_b66z189_TOP3000_d2_IND_t12 | eur_top_value_2 | 189 | INDUSTRY | 2 | 0.12 | 2.12 | 1.74 | 0.1153 | 0.99/0.92 | YES |
| 5 | gz_t2_b66z189_TOP3000_d3_SEC_t1 | eur_top_value_2 | 189 | SECTOR | 3 | 0.01 | 2.08 | 1.67 | 0.1059 | 1.0/0.9 | YES |
| 6 | gz_t2_b66z189_TOP3000_d3_SEC_t12 | eur_top_value_2 | 189 | SECTOR | 3 | 0.12 | 2.07 | 1.67 | 0.1065 | 1.0/0.9 | YES |
| 7 | gz_t2_b66z189_TOP3000_d3_IND_t1 | eur_top_value_2 | 189 | INDUSTRY | 3 | 0.01 | 2.0 | 1.59 | 0.1035 | 0.89/0.87 | YES |
| 8 | gz_t2_b66z189_TOP3000_d3_IND_t12 | eur_top_value_2 | 189 | INDUSTRY | 3 | 0.12 | 1.99 | 1.59 | 0.1042 | 0.9/0.86 | YES |
| 9 | gz_t2_b66z252_TOP3000_d2_SEC_t1 | eur_top_value_2 | 252 | SECTOR | 2 | 0.01 | 1.67 | 1.18 | 0.1144 | 0.87/0.72 | YES |
| 10 | gz_t2_b66z252_TOP3000_d2_SEC_t12 | eur_top_value_2 | 252 | SECTOR | 2 | 0.12 | 1.67 | 1.19 | 0.115 | 0.87/0.72 | YES |

## 各候选完整表达式与 sub_universe 明细

### 1. gz_t2_b66z189_TOP3000_d2_SEC_t1  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=2.18, Fitness=1.8, TVR=0.1187, Margin=0.001432
- **sub_universe 明细（WQ 真实值）**：sub_univ=1.08, sub_limit=0.94, 比值=1.149 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=2, neutralization=SECTOR, truncation=0.01, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 2. gz_t2_b66z189_TOP3000_d2_SEC_t12  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=2.17, Fitness=1.79, TVR=0.1193, Margin=0.001434
- **sub_universe 明细（WQ 真实值）**：sub_univ=1.08, sub_limit=0.94, 比值=1.149 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=2, neutralization=SECTOR, truncation=0.12, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 3. gz_t2_b66z189_TOP3000_d2_IND_t1  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=2.13, Fitness=1.75, TVR=0.1145, Margin=0.001465
- **sub_universe 明细（WQ 真实值）**：sub_univ=0.98, sub_limit=0.92, 比值=1.065 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=2, neutralization=INDUSTRY, truncation=0.01, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 4. gz_t2_b66z189_TOP3000_d2_IND_t12  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=2.12, Fitness=1.74, TVR=0.1153, Margin=0.001465
- **sub_universe 明细（WQ 真实值）**：sub_univ=0.99, sub_limit=0.92, 比值=1.076 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=2, neutralization=INDUSTRY, truncation=0.12, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 5. gz_t2_b66z189_TOP3000_d3_SEC_t1  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=2.08, Fitness=1.67, TVR=0.1059, Margin=0.001529
- **sub_universe 明细（WQ 真实值）**：sub_univ=1.0, sub_limit=0.9, 比值=1.111 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=3, neutralization=SECTOR, truncation=0.01, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 6. gz_t2_b66z189_TOP3000_d3_SEC_t12  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=2.07, Fitness=1.67, TVR=0.1065, Margin=0.00153
- **sub_universe 明细（WQ 真实值）**：sub_univ=1.0, sub_limit=0.9, 比值=1.111 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=3, neutralization=SECTOR, truncation=0.12, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 7. gz_t2_b66z189_TOP3000_d3_IND_t1  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=2.0, Fitness=1.59, TVR=0.1035, Margin=0.001519
- **sub_universe 明细（WQ 真实值）**：sub_univ=0.89, sub_limit=0.87, 比值=1.023 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=3, neutralization=INDUSTRY, truncation=0.01, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 8. gz_t2_b66z189_TOP3000_d3_IND_t12  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 189), industry))`
- **指标**：Sharpe=1.99, Fitness=1.59, TVR=0.1042, Margin=0.001522
- **sub_universe 明细（WQ 真实值）**：sub_univ=0.9, sub_limit=0.86, 比值=1.047 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=3, neutralization=INDUSTRY, truncation=0.12, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 9. gz_t2_b66z252_TOP3000_d2_SEC_t1  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 252), industry))`
- **指标**：Sharpe=1.67, Fitness=1.18, TVR=0.1144, Margin=0.001097
- **sub_universe 明细（WQ 真实值）**：sub_univ=0.87, sub_limit=0.72, 比值=1.208 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=2, neutralization=SECTOR, truncation=0.01, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY

### 10. gz_t2_b66z252_TOP3000_d2_SEC_t12  (PASS_CHEAP)
- **表达式**：`rank(group_zscore(ts_zscore(ts_backfill(eur_top_value_2, 66), 252), industry))`
- **指标**：Sharpe=1.67, Fitness=1.19, TVR=0.115, Margin=0.001101
- **sub_universe 明细（WQ 真实值）**：sub_univ=0.87, sub_limit=0.72, 比值=1.208 → **超标**
- **settings**：universe=TOP3000, delay=1, decay=2, neutralization=SECTOR, truncation=0.12, testPeriod=P6Y, pasteurization=ON, maxTrade=OFF, nanHandling=ON, unitHandling=VERIFY
