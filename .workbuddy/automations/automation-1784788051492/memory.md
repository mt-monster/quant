# V34 insider_matrix PPA 挖掘进度汇报 — 自动化记忆

## 最近执行 (2026-07-24 12:02)
- 最新日志: `v34_progress_20260723_162553.log`（无新增日志，状态与 11:05 一致）
- 进程状态: ⏹️ **仍停止**（无 scan_v34 进程），自 07-23 17:59 起约 18 小时未运行
- 合并 3 日志: 82 个含 sharpe 唯一结果 / **0 PASS** 候选（未提交任何 alpha）
- Top: S=1.95/F=1.36/LAD=1.98(PASS) ~ LAD=2.17(PASS)，但全卡 LOW_SUB_UNIVERSE_SHARPE 结构化瓶颈
- 结论: 状态冻结，无需重启即可复验；已再次提醒用户按需重启

## 最近执行 (2026-07-24 11:05)
- 最新日志: `v34_progress_20260723_162553.log`（无新增日志，状态与 10:04 一致）
- 进程状态: ⏹️ **仍停止**（无 scan_v34 进程），自 07-23 17:59 起约 18 小时未运行
- checkpoint: 存在，72/72 done → 重启将续跑剩余 ~252/324
- 合并 3 日志: 170 唯一 label / 82 含 sharpe / **0 PASS**（未提交任何 alpha）
- 未变化: 仍是 LOW_SUB_UNIVERSE_SHARPE 结构化瓶颈，最高 S=1.95/LAD=2.17 但全卡该闸
- 结论: 状态冻结，无需重启即可复验；已再次提醒用户按需重启

## 最近执行 (2026-07-24 10:04)
- 最新日志: `v34_progress_20260723_162553.log`（16:25 启动的新一轮，跑到 65/324 后于 17:59 停止）
- 进程状态: ⏹️ **已停止 ~16 小时**（无 scan_v34 进程）
- checkpoint: `v34_insider_matrix_checkpoint.json` 现已存在（72/324 done）→ 重启会**续跑**剩余 ~252，而非重跑全部
- 合并 3 日志: 170 唯一 label / 82 含 sharpe / **0 PASS**（未提交任何 alpha）
- 失败闸首杀: LOW_SUB_UNIVERSE_SHARPE(49) ＞ LOW_SHARPE(20)=LOW_FITNESS(20) ＞ IS_LADDER_SHARPE(15)
- 28 个变体 IS_LADDER 通过但只卡 LOW_SUB_UNIVERSE_SHARPE（S=1.80~1.95, LAD=1.80~2.17, subU 0.01~0.23）→ 平台真实拒绝，非误判
- 结论: EUR insider_matrix 方向整体指标好但**子宇宙 Sharpe 不足**是结构化瓶颈；若仅复验无需重启（15:33 那轮已跑满 324/0 PASS）。已提醒用户按需重启。
- 报告: `results/v34_status_report_20260724_1004.md`

## 最近执行 (2026-07-23 15:50)
- 最新日志: `results/v34_progress_20260723_152946.log`（mtime 15:33，与上轮 15:36 一致，无新增）
- 进程状态: ⏹️ **未运行**（无 scan_v34 进程），已完成 done=324/324，无需重启
- 结果: 33 个 sharpe（全 FAIL），0 个 PASS 候选 → 未提交任何 alpha
- checkpoint 仍缺失（`v34_insider_matrix_checkpoint.json` 不存在），全 324 结果无法重建，仅 recent 窗口可查
- 结论: 状态未变化，维持上轮分析（11 个高指标变体疑似 check_alpha_gates 误判；待人工复核 7 个 PID + 修复 save_checkpoint/check 处理）

## 最近执行 (2026-07-23 15:36)
- 最新日志: `results/v34_progress_20260723_152946.log`
- 进程状态: ⏹️ **已自然完成并退出**（无 scan_v34 进程），done=324/324 (100%)，ETA 15:33:42 → 无需重启
- 结果: 33 个产出 sharpe（全 FAIL），88 个 backtest error，**0 个 PASS 候选** → 未提交任何 alpha
- 关键发现: 33 个 FAIL 全部 `platform_FAIL`，其中 **11 个高指标变体（7 个唯一 PID）疑似误判**
  - IS_LADDER 全 PASS，S=1.73~1.95，F=1.13~1.36，margin 11~16bp，TVR 7~11%
  - 根因: `check_alpha_gates` 在 `/check` 拉取返回 None 时返回 (False,{})，日志 checks={} 无具体失败闸门 → 疑似 API 拉取失败导致误判 FAIL
  - 代表 PID: e7xn7ng6(1.95), QP9nZvXQ(1.90), ZYKjYOgY(1.88), zqR5q71E(1.82), pwKnmmpv(1.80), mLVqLOk2(1.77), wpE5p2zQ(1.73)
  - 真实失败: `delta_reversal_*` 系列 IS_LADDER FAIL(F<1, TVR~30%)；`rank_momentum_d5` F=0.47
- 数据完整性告警: checkpoint 文件 `v34_insider_matrix_checkpoint.json` **缺失**（save_checkpoint 静默失败），全 324 结果无法重建，仅 recent 窗口(121)可查；下次重跑将当全新
- 建议: ①人工到 WQ 后台对 7 个 PID 复核 /check；②修复 check_alpha_gates 对 ch is None 的处理（待复核而非直接 FAIL）；③修复 save_checkpoint 持久化
- 报告文件: `results/v34_status_report_20260723_1536.md`
