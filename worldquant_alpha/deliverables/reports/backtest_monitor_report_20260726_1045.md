# 回测任务监控报告 · 2026-07-26 10:45 (GMT+8)

> 发现入口 = 机器级全量 Python 进程枚举（`Get-CimInstance Win32_Process`）+ checkpoint / progress 日志实算。
> 本报告手工核编，已捕获自动工具易漏的「死亡作业 + 文件锁根因」。

---

## 🚨 0. 关键告警（先读）

| # | 告警 | 影响 | 严重度 |
|---|------|------|--------|
| A | **`ds` 舰队整体 ~100% 提交报错**（status=error, pid=null） | 0 个候选产出，吞吐名存实亡 | 🔴 高 |
| B | **`fundamental65`(PID 38896) 与 `chart_cnn_alpha`(PID 51492) 进程已死** | 这两路数据集停摆，未自动重启 | 🔴 高 |
| C | **根因 = WinError 32 文件锁冲突**：多进程并发写共享状态文件 `.brain_sim_submit_gate.json` 原子 rename 失败 | 所有 `scan_tri_job` 探索进程 + rescue 互相踩踏 | 🔴 高 |
| D | **Token-Bucket 429 风暴**：rescue 车道 + chart_cnn 退避飙到 120s（#11） | 提交令牌被耗尽，进一步拉低有效吞吐 | 🟠 中 |
| E | **0 个 alpha 真正提交**（仅 1 个进入 `manual_submit_ready` 且 `submitted=False`） | 研究仿真候选未跨过生产关 | 🟠 中 |

---

## 1. 进程枚举与分类（机器级，TOTAL=28）

| 分类 | 正则/判定 | PID | 说明 |
|------|-----------|-----|------|
| **EDITOR** | jedi language-server | 26396, 29284, 3720, 19140 | Cursor IDE 语言服务，非挖矿 |
| **MCP-SVC** ⚠️ | `cnhkmcp/.../platform_functions.py` | 38560, 35484, 60192, 6928, 59496, 58420 | WQ BRAIN 服务端回测宿主（本机不跑计算、不写本地日志、闲挂占槽）。其服务端仿真任务仅经 WQ 控制台 / MCP 对话可见（盲区②） |
| **SCAN（主账号·在飞）** | `scan_tri_job.py` | 36392 sentiment21 / 35332 analyst_earnings_ibes / 56624 shortinterest6 / 44632 shortinterest7 / 50432 expected_move / 59224 multi_horizon_alpha | 主账号 `mth***` 的 6 路探索（vnpystudio python） |
| **RESCUE（主账号）** | `scan_rescue_tvr.py` | 47480 | `dl_riskfree_returns` TVR 救援车道 |
| **KEEPER** | `fleet_keeper.py --target 6` | 37716 | 舰队守护，已主动降到 6 路 |
| **💀 已死（在 fleet_active 但进程列表缺失）** | — | ~~38896 fundamental65~~ / ~~51492 chart_cnn_alpha~~ | 见告警 B |
| **OTHER·独立项目** ⚠️ | `D:\BaiduNetdiskDownload\WQ第二三四节课代码\worldquant\` | continuous_undug(33472,47680) / _green_guard(31352,33328) / tri_track_undug(40684,48456) / analyze_tabbit_parallel(33788,48924) | **盲区⑤**：独立账号（tabbit/option9）挖掘，非本 E3/quant 舰队，互不可见。48924 线程=3 即 CONCURRENCY=3 |

---

## 2. 逐任务并发模型 + 进度

### 2.1 主账号 `ds` 舰队（Data Shop 数据集三轨挖掘）

并发模型：每路 `scan_tri_job.py` + `multi_sim n=8` + 共享 `submit_gate`（18s 间隔）；由 `fleet_keeper` 维持 6 探索 + 1 救援。

| 任务 | PID | 进度(实时) | total | 状态 | 实时 ETA | 吞吐 |
|------|-----|-----------|-------|------|----------|------|
| ds:sentiment21 | 36392 | **208/320 (65%)** | 320 | ✅ 在飞，但近期全 error | 07-26 14:14 | ~113s/步 |
| ds:analyst_earnings_ibes | 35332 | 25/40 批 (200) | 320 | ✅ 在飞 | 07-26 14:23 | — |
| ds:shortinterest6 | 56624 | 11/40 批 (88) | 320 | ✅ 在飞 | 07-27 00:30 | — |
| ds:shortinterest7 | 44632 | 9/40 批 (72) | 320 | ✅ 在飞 | 07-27 03:23 | — |
| ds:expected_move | 50432 | 2/40 批 (16) | 320 | ✅ 在飞，但 16 全 error | 07-27 06:03 | — |
| ds:multi_horizon_alpha | 59224 | 1/40 批 (8) | 320 | ✅ 在飞，8 全 error | 07-26 15:42 | — |
| ds:fundamental65 | ~~38896~~ | 40/320 (12.5%) | 320 | 💀 **已死**(末次活动 10:31) | — | — |
| ds:chart_cnn_alpha | ~~51492~~ | 8/320 (2.5%) | 320 | 💀 **已死**(末次活动 10:40) | — | — |

> 舰队总进度：45 数据集 `done`、8 在飞（现仅 6 活）、73 在 `queue`（待启动）。

### 2.2 救援车道

`scan_rescue_tvr.py --dataset dl_riskfree_returns`：1440 变体 → 裁剪 120，multi-sim n=8 / 18s 节奏提交。
日志显示 **429 退避逐级升级 30→45→60→75s（#0~#3）**——与 6 路探索抢同一令牌桶，已触发 429 风暴（告警 D）。

### 2.3 历史 `scan_v` 系列（v33–v54，独立 scan 脚本）

25 个任务，5787 变体，5035 拿到 pid，**42 个 PASS_CHEAP 候选**集中在新近三档：

| 任务 | 变体 | 最佳 S | 候选数 |
|------|------|--------|--------|
| v52b_hiring_margin | 160 | **2.66** | **28** |
| v39b_sub_micro | 160 | 2.58 | 10 |
| v52_tri_hiring_trends | 320 | 2.50 | 4 |
| 其余 v33–v54 | ~5347 | ≤2.3 | 0 |

`scan_v52b` 已把候选写入自身 checkpoint 并打标 `READY_MANUAL / NO_SUBMIT`，但**未汇总进 `manual_submit_ready.json`**（该文件仅 1 条旧记录）。

---

## 3. 回测效率结论（必须给）

- **基准对照**：`bench_v34` multi(8) = 86.1 α/hr vs single = 54.3 α/hr（1.59×）。
- **实测有效产出 ≈ 0**：6 路在飞名义提交量高（~113s/批 × 8 变体 ≈ 254 α/hr/路），但因 **WinError 32 文件锁冲突**（告警 C），绝大多数提交在 `os.replace` 原子写状态文件时失败 → `status=error`、`pid=null`。**真实拿到 pid 的通过率在当前批次接近 0%**（sentiment21 近期 100% error；fundamental65/chart_cnn 进程直接崩）。
- **并发利用率失真**：表面 6+1 路全开，实际只有"失败重试"在空转，令牌桶反而被 429 退避耗尽（rescue + chart_cnn）。**瓶颈是 submit_gate 跨进程文件锁，不是信号发现、也不是平台吞吐。**
- **提吞吐杠杆（按优先级）**：
  1. **修复 submit_gate 并发安全**（用文件锁 `msvcrt.locking` / `fcntl` 或命名互斥，或每进程独立 state 文件 + 中央限速器）→ 这是解除 100% error 的前提。
  2. 修复后恢复 8 路（keeper target=8），按基准可 ~86 α/hr/路。
  3. 关掉闲挂的 MCP-SVC 宿主释放主账号槽位（仅当其服务端无在飞任务时）。
  4. 独立账号（BaiduNetdisk tabbit）已并行，可保留。

---

## 4. 监控盲区排查（逐类）

1. **硬编码任务列表** — 否：本次以进程枚举 + checkpoint 自动发现，含 6 活 + 2 死 + 独立项目。
2. **服务端/WQ-BRAIN 无本地日志** — 6 个 `cnhkmcp` 宿主属此类，其服务端仿真仅经控制台/MCP 可见（已单列，不计入本地进度）。
3. **账号维度盲区** — `D:\BaiduNetdiskDownload\...` 为独立账号（tabbit/option9）挖掘，本机与主账号互不可见（已单列，盲区⑤）。
4. **只写 checkpoint 不写日志** — 不适用（本舰队均写 progress 日志）。
5. **陷阱②非 scan_v 命名真挖掘** — `analyze_tabbit_parallel.py` / `tri_track_undug.py` 命令行含 `tri_track` 易被误判为 TRACKER，实为独立账号三轨挖掘（已人工改判单列）。

---

## 5. 提交验证 · 四关层级

| 关 | 内容 | 现状 |
|----|------|------|
| ① 研究仿真 IS 廉价闸门 | S>1.58/F>1.0/TVR∈[0.05,0.30]/M>10bp/Ret>0.05 | ds 舰队 0 通过；scan_v 42 个 PASS_CHEAP |
| ② 生产仿真 OOS | 样本外稳健 | 未跑（0） |
| ③ 生产相关性 | PROD_CORRELATION<0.70 + SELF_CORRELATION<0.50 | 仅 `manual_submit_ready.json` 中 1 条通过（prod_corr<0.70）；v52b 28 候选虽算过 prod_corr 但未汇总核验 |
| ④ submittable + 真实提交 | 平台判定 + 落平台 | **0 个**（`no_submit=True`，用户规则不自动提交） |

**结论**：`PASS_CHEAP` = 研究仿真廉价闸门通过，**≠ 可提交**。当前 **42 个研究候选 + 1 个 manual_ready，0 已提交**。

---

## 6. 并发模型 · Token-Bucket（C≈7）

- 突发容量 **C≈7**，慢补充 ~1 令牌/20–40s；同账号 ≥8 在 <2s 内齐射必 429。
- 多进程共享 submit_gate 时，**Windows 下 `os.replace` 原子写对目标文件加锁失败（WinError 32）**——这是本次 100% error 的直接技术根因，需在 `submit_gate.py` 加跨进程文件锁或改为每进程独立 state + 中央限速。
- 429 backoff 已实现（30/45/60/75/120s 递增），但 rescue 与探索同桶仍相互挤占。

---

## 7. ETA 预期完成时间

> 置信度：运行 >60min 的 4 路 = 较高；刚启动/已死的 4 路 = 低（含 error 风暴，ETA 不可信）。

| 任务 | 进度 | 预期完成 | 置信度 | 备注 |
|------|------|----------|--------|------|
| ds:sentiment21 | 65% | 07-26 14:14 | 较高 | 实时日志 |
| ds:analyst_earnings_ibes | 62.5% | 07-26 14:23 | 较高 | snapshot |
| ds:shortinterest6 | 27.5% | 07-27 00:30 | 较高 | snapshot |
| ds:shortinterest7 | 22.5% | 07-27 03:23 | 较高 | snapshot |
| ds:expected_move | 5% | 07-27 06:03 | 低 | 仅 2 批且全 error |
| ds:multi_horizon_alpha | 2.5% | 07-26 15:42 | 低 | 刚启动，全 error |
| ds:fundamental65 | 12.5% | **无法完成** | — | 💀 进程已死 |
| ds:chart_cnn_alpha | 2.5% | **无法完成** | — | 💀 进程已死 |

**车队整体终点**：6 路存活中最早 ~07-26 15:42（multi_horizon，若它能跑通）、最晚 ~07-27 06:03（expected_move）；2 路死亡数据集**不会自行恢复**，除非修复文件锁后由 keeper 重启或手动拉起。

---

## 8. 产出物与工具

- 报告：`worldquant_alpha/deliverables/reports/backtest_monitor_report_20260726_1045.md`
- 数据：`worldquant_alpha/results/*_checkpoint.json`、`*_progress_*.log`、`fleet_keeper_state.json`、`fleet_eta_snapshot.json`
- 根因文件：`worldquant_alpha/results/.brain_sim_submit_gate.json`（共享状态，需加锁）
- 工具：`deliverables/tools/build_md_report.py`（自动生成）、`lint_submit_gate.py`（限速合规检查）

---

## 9. 下一步建议（按优先级）

1. **🔴 修复 `submit_gate.py` 跨进程文件锁**（WinError 32）——这是解除 100% error 的唯一前提；否则重开 8 路只会增加报错量。
2. **重启 fundamental65 / chart_cnn_alpha** 两路（修复后由 keeper 拉起或手动 `scan_tri_job.py --dataset ...`）。
3. **降 rescue 车道速率**：rescue 与探索共用令牌桶，建议 rescue 间隔提到 ≥45s 或错峰，避免 429 互相拖累。
4. **汇总候选**：把 v52b/v39b/v52 的 28+10+4=42 PASS_CHEAP 候选（含已算 prod_corr）统一汇入 `manual_submit_ready.json` 供你人工提交。
5. 修复并验证后，再考虑把 keeper 从 target=6 提回 target=8。
