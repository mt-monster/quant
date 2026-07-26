# 候选因子提交核查

> ACTIVE / 拒绝 / 待验证，逐项审计
> 来源：原报告对应章节自动提取

## 九、候选因子提交核查（逐项审计）

| 分类 | 数量 | 说明 |
|---|---|---|
| ✅ 已正式提交 | **2** | `YPgAa3WR`, `j2rrpVzO` |
| ❌ 平台拒绝 | **45** | 提交后被静默拒绝（同集群PROD_CORRELATION/SELF_CORRELATION FAIL） |
| 🔶 仍需进一步验证 | **0** | 缺生产仿真(OOS)+submittable+submit |

> ⚠️ **实话实说**：全部 47 个候选，**2 个已提交、45 个不可提交**。已提交者均过 IS + 生产相关性 + 风险中性 + 稳健性。其余缺平台 OOS 硬闸门或 PROD_CORRELATION/SELF_CORR FAIL。

**逐候选核查（按提交状态分级）**：

### ✅ 已正式提交 (2 个)

| pid | 任务 | S | 验证链 | 提交时间 |
|---|---|---:|---|---|
| **YPgAa3WR** | v39b_sub_micro            | **2.08** | IS✅ 产验✅ 风险中性✅ 稳健性✅ | 2026-07-24T01:30 |
| **j2rrpVzO** | v52_tri_hiring_trends     | **2.19** | IS✅ 产验✅ 风险中性✅ 稳健性✅ | 2026-07-26T09:41 |

### ❌ 平台拒绝 (45 个)

| pid | 任务 | S | 拒绝原因 |
|---|---|---:|
| e7xQoWZM | rescue_r3_web_lift        | **1.74** | 未跑OOS—提交后被静默拒绝 |
| 1YzZvLKm | rescue_r3_web_lift        | **1.74** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| xAdbQKYb | rescue_r3_web_lift        | **1.74** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| xAdbQKYp | rescue_r3_web_lift        | **1.74** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| GreOMmnQ | rescue_r3_web_lift        | **1.71** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| le30awQe | v39b_sub_micro            | **2.07** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| j2rgVd0E | v39b_sub_micro            | **2.18** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| zqRWAJmX | v39b_sub_micro            | **2.17** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| QP9QNw8G | v39b_sub_micro            | **2.00** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| RR1rlGge | v39b_sub_micro            | **1.99** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| KPELQn7l | v39b_sub_micro            | **1.67** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| e7xrvnzJ | v39b_sub_micro            | **1.67** | 未跑OOS—提交后被静默拒绝 |
| N1RO8rLL | v39b_sub_micro            | **2.13** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| np8Wr2ml | v39b_sub_micro            | **2.12** | 平台闸门 FAIL: SELF_CORRELATION — 信号被占/自相关过高 |
| Xg8720b0 | v52b_hiring_margin        | **2.31** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| zqRkPVbX | v52b_hiring_margin        | **2.33** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| 1YzwaMZz | v52b_hiring_margin        | **2.32** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| WjV7a5eo | v52b_hiring_margin        | **2.32** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| pwKj7Rd3 | v52b_hiring_margin        | **2.31** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| RR17rbe0 | v52b_hiring_margin        | **2.33** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| e7xzrba6 | v52b_hiring_margin        | **2.32** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| vRvjmrY3 | v52b_hiring_margin        | **2.32** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| wpEjaENp | v52b_hiring_margin        | **1.94** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| E5elGemr | v52b_hiring_margin        | **1.94** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| d5RjZR9K | v52b_hiring_margin        | **1.91** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| 88elpeGW | v52b_hiring_margin        | **1.92** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| gJ9jZxnM | v52b_hiring_margin        | **1.79** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| kqZjgQzO | v52b_hiring_margin        | **1.81** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| qM6j0XKK | v52b_hiring_margin        | **1.80** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| 9q7XWRzK | v52b_hiring_margin        | **1.81** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| rKPj7WWd | v52b_hiring_margin        | **1.90** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| N1R7POpX | v52b_hiring_margin        | **1.90** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| 78njYdwQ | v52b_hiring_margin        | **1.91** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| xAdjvnxN | v52b_hiring_margin        | **1.92** | 未跑OOS—提交后被静默拒绝 |
| E5el82OG | v52b_hiring_margin        | **2.30** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| wpEjPZ5l | v52b_hiring_margin        | **2.30** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| le3jNVV5 | v52b_hiring_margin        | **1.91** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| qM6jwAlK | v52b_hiring_margin        | **1.89** | 未跑OOS—提交后被静默拒绝 |
| bldj1LvZ | v52b_hiring_margin        | **1.75** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| xAdjpxRn | v52b_hiring_margin        | **1.77** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| 9q7XOwJd | v52b_hiring_margin        | **1.76** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| 88elxznW | v52b_hiring_margin        | **1.76** | 平台闸门 FAIL: PROD_CORRELATION+LOW_2Y_SHARPE — 信号被占/自相关过高 |
| RR11Gzbd | v52_tri_hiring_trends     | **1.63** | 未跑OOS—提交后被静默拒绝 |
| A17GR6Wd | v52_tri_hiring_trends     | **1.94** | 平台闸门 FAIL: PROD_CORRELATION — 信号被占/自相关过高 |
| YPgvjZrJ | v52_tri_hiring_trends     | **1.79** | 未跑OOS—提交后被静默拒绝 |


> 📋 **提交流程**：① 研究仿真 IS 闸门通过(本地) → ② `POST /alphas/{pid}/submit` 自动触发 OOS+PROD_CORR+SELF_CORR → ③ `GET /check` 返回全量闸门 → ④ PASS 则 ACTIVE。已用 `verify_candidates.py` + `submit_and_verify.py` 验证全部 47 候选。

---