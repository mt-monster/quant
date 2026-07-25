# WQ PPA 历史回测任务盘点

- 生成时间：2026-07-24 17:50 (GMT+8)
- 扫描范围：`Desktop/E3/quant/worldquant_alpha` 下全部 `scan_v*.py` 脚本 + `results/*checkpoint.json`
- 口径说明：「已完成回测量」= checkpoint 中实际落盘的变体数；「候选」含 `submitted`（已提交）与 `candidate` 标记。

---

## 1. 总览

| 指标 | 数值 |
|------|------|
| 扫描脚本总数 | 18（V31–V42，含 v2/v3 变体） |
| 有 checkpoint 的任务 | 12 |
| 累计已完成回测量（checkpoint 合计） | **~1835 条** |
| 历史提交成功（ACTIVE） | **1**（V39b） |
| 当前运行中 | **1**（V42 social_sent） |
| 已暂停 | 1（V33 HKG，07-23 14:20） |
| 零候选任务 | 11/12（仅 V39b 出 1 候选） |

---

## 2. 逐任务明细

| # | 脚本 | 数据集 | 批大小 | 状态 | 已完成回测 | 候选 |
|---|------|--------|--------|------|-----------|------|
| V31 | scan_v31_chnkor.py | （未解析） | — | 历史脚本，无 checkpoint | 0 | 0 |
| V32 | scan_v32_kor.py | （未解析） | — | 历史脚本，无 checkpoint | 0 | 0 |
| V33 | scan_v33_hkg_anl10.py / _v2 | （未解析） | —— | **暂停**（07-23 14:20） | 59 | 0 |
| V33 | scan_v33_hkg_anl10_v3.py | （未解析） | 10 | 未启用 | 0 | 0 |
| V33 | scan_v33_kor.py | （未解析） | — | 历史脚本，无 checkpoint | 0 | 0 |
| V34 | scan_v34_insider_matrix.py / _v2 | insider_matrix | 8 | 已完成 / 弃用 | 72* | 0 |
| V35 | scan_v35_news_nlp.py | （未解析） | 8 | 已完成 | 24 | 0 |
| V36 | scan_v36_stock_cluster_dl.py | stock_cluster_dl | 8 | 已完成 | 157 | 0 |
| V37 | scan_v37_other545.py | other545 | 8 | 已完成 | 187 | 0 |
| V38 | scan_v38_sust_profit.py | sustainable_profit | 8 | 已完成 | 278 | 0 |
| V38b | scan_v38b_sust_rescue.py | sustainable_profit | 8 | 已完成 | 270 | 0 |
| V39 | scan_v39_insider_rescue.py | insider_matrix | 8 | 已完成 | 240 | 0 |
| V39b | scan_v39b_sub_micro.py | insider_matrix | 8 | 已提交 | 160 | **1 (ACTIVE)** |
| V40 | scan_v40_cre_exposure.py | cre_exposure_model | 8 | 已完成 | 200 | 0 |
| V41 | scan_v41_earn_risk.py | earnings_risk | 8 | 刚完成（~17:36） | 180 | 0 |
| V42 | scan_v42_social_sent.py | social_sent_score | 8 | **运行中**（PID 42076，17:40 起） | 8（进行中） | 0 |

> *V34 注：当前 checkpoint 落盘 72 条；历史记录显示曾以 v2 跑过全量 324 变体（TOP3000），该轮 checkpoint 未以同名文件留存，故此处仅显示 72。
> V39b 注：checkpoint 落盘 160 条；提交成功的候选 `gz_t2_b66z189_TOP3000_d3_SEC_t1`（pid YPgAa3WR）来自此任务，状态 ACTIVE。

---

## 3. 范式演进脉络（按时间）

1. **V31–V33（区域/动量早期）**：港股/韩股/行业动量方向，止步廉价闸门（Sharpe/Fitness 不达标）。V33 HKG 因 0 候选被手动暂停。
2. **V34–V39（内部人/insider 家族）**：核心投入方向。insider_matrix 数据集，行业中性动量 Sharpe 1.8–2.3，但被平台 `LOW_SUB_UNIVERSE_SHARPE` 子宇宙跷跷板结构性卡死（约 57% 触发），累计 288 结构零通过。
3. **V37–V38（可持续/其他 545 字段）**：换字段探索，仍 0 候选。
4. **V39b（insider 微观子集）**：唯一产出可提交候选并成功上线 ACTIVE。
5. **V40（商业/住宅地产暴露）**：cre_exposure_model，200 变体全 FAIL。
6. **V41（盈利风险/IV spread）**：earnings_risk，180 变体全 FAIL（刚刚跑完）。
7. **V42（社交舆情）**：social_sent_score，新方向，当前运行中。

---

## 4. 关键结论

- **吞吐不是瓶颈，信号是瓶颈**：累计 ~1835 条回测，仅 1 条（V39b）过闸门并上线。V31–V42 整体零平台通过率（除 V39b 外）≈ 0/1834。
- **insider 家族已充分证伪**：子宇宙 Sharpe 跷跷板是平台硬闸门，结构性不可行，应停止在该范式的边际投入。
- **当前方向上**：V41 刚以 0 候选收尾，V42 社交舆情刚起步（首批 8 条已过），是接下来最值得盯的方向。
- **V33 HKG 长期暂停**：自 07-23 14:20 起未动，建议明确是否彻底弃用或重启。

---

## 5. 待办 / 建议

- 盯 V42 social_sent 进度（~180 变体，预计 2–2.5 小时跑完），关注是否出现可提交候选。
- 若 V42 仍 0 候选，正式决策范式转向（换 region / 换数据集家族 / 回到 V39b 低自相关风格做扩展扫描）。
- 决定 V33 HKG 去留（暂停超过 24 小时）。
