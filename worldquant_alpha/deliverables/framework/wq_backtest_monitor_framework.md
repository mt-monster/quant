# WQ PPA 挖掘 · 监控 / 验证 / 并发 经验框架

> 本框架归纳自 2026-07-25 一整轮 WQ BRAIN PPA alpha 挖掘监控与提交验证实战。
> 目标：把零散经验固化为**可复用的分析框架 + 产出物分类标准**，下次"盯回测 / 盘点任务 / 看效率"直接套用，不再从零推导。
> 配套工具：`deliverables/tools/gen_report.py`（监控报告生成器）、`deliverables/tools/lint_submit_gate.py`（并发纪律 linter）、`deliverables/tools/probe_*.py` + `measure_*.py`（并发上限探针）。

---

## 〇、产出物分类标准（本次已落盘）

所有"我的产出物"统一收口到 `deliverables/`，与用户的 `scan_*.py`（挖掘脚本）、`results/`（checkpoint/CSV 数据）严格分离：

```
worldquant_alpha/
├── deliverables/                  # 我的产出物（分类存放）
│   ├── reports/                   # 时点快照 / 专题分析 .md
│   │   ├── backtest_monitor_report_*.md     # 全链路监控报告（10 章节）
│   │   ├── process_audit_*.md               # Python 进程视角审计
│   │   ├── probe_concurrency_final_report_*.md  # 并发上限专题
│   │   ├── v34_status_report_*.md / status_report_*.md / historical_backtest_inventory_*.md
│   │   └── v39b_pass_cheap_candidates.md
│   ├── tools/                     # 我构建的可复用脚本
│   │   ├── gen_report.py          # 监控报告生成器（OUT→deliverables/reports/，输入仍读 results/）
│   │   ├── lint_submit_gate.py    # 并发纪律 linter（_HERE 指回项目根）
│   │   ├── probe_concurrency.py / measure_L*.py / measure_rate.py / probe_quota*.py
│   │   └── _bench_v34_sim_speed.py # multi(8) vs single 吞吐基准
│   └── framework/                 # 本框架文档
├── results/                       # 数据（不动）：*_checkpoint.json、*.csv、*_progress_*.log
├── scan_*.py                      # 用户的挖掘脚本（26 个，非我的产出物）
└── (基础设施) multi_sim.py / wd_lib_wrapper.py / submit_gate.py / config.py ...
```

**分类判定规则**：
- 报告 `.md`（含 "report"/"audit"/"status"/"inventory"/"candidates"）= 进 `deliverables/reports/`
- 我写的、可复跑的 `.py`（gen_report / lint / probe / measure / bench）= 进 `deliverables/tools/`
- 用户的 `scan_*.py`、平台 `results/` 数据、基础设施 `*.py` = **不归类、原地保留**
- **红线**：绝不动在跑进程的 checkpoint 与脚本（如 v52b 的 `results/v52b_hiring_margin_checkpoint.json` 与 `scan_v52b_hiring_margin.py`），移动只针对静态产出物

---

## 一、WQ 挖掘监控框架（Python 进程第一视角）

> 铁律：**发现入口 = 机器级全量 Python 进程枚举**，v 系列日志 / CSV 仅作 scan 脚本明细补充，绝不能作为任务发现入口。

### 第一步 · 机器级进程枚举与分类
```
Get-CimInstance Win32_Process -Filter "Name='python.exe'"
```
按命令行正则分类（**必须先枚举、再分类**，不能倒过来）：

| 分类 | 正则 | 性质 | 是否挖 alpha |
|------|------|------|--------------|
| **SCAN** | `scan_v\d+` | 主账号挖掘脚本 | ✅ |
| **MINING** | 非 scan_v 但真在挖（见陷阱②） | 独立账号/三轨挖掘 | ✅ |
| **MCP-SVC** | `platform_functions\|mcp\|brain` | WQ BRAIN 交互后端 = **服务端回测宿主**（本机不跑计算、不写本地日志） | ⚠️ 闲挂占槽 |
| **WATCHDOG/TRACKER** | `watchdog\|tri_track\|tracker` | 监控辅助进程 | ❌（但见陷阱②） |
| **EDITOR** | `jedi\|ms-python\|language-server` | IDE 语言服务 | ❌ |
| **OTHER** | 其余 | — | 视情况 |

- 对每个真挖掘进程报：**PID / 启动时间 / 线程数 / 内存 / 累计 CPU 时间**（CPU 占比极低 = 网络等待型，典型回测进程）。

### 第二步 · 逐任务并发模型 + 进度
- 读脚本确认：`BATCH_SIZE`（multi-sim 一次 POST 提 N 条）/ `ThreadPool CONCURRENCY`（并行单模拟）/ `COOLDOWN` / 数据集 / 账号（是否独立）
- 读 checkpoint / CSV 确认：done 数、候选数、最佳 Sharpe；吞吐 = done / 已运行分钟

### 第三步 · 回测效率结论（必须给，越详细越好）
- 实测吞吐 vs 基准（`_bench_v34_sim_speed`：multi(8)=86.1 α/hr vs single=54.3 α/hr，speedup 1.59×）
- 该任务是否跑在其账号/配置的最大并发档
- 平台整体并发利用率：同时跑几个作业、槽位是否闲置、多账号并行能否提升总吞吐
- 提吞吐杠杆排序

### ⚠️ 反复踩坑的"发现盲区"分类（必须逐类排查）
1. **硬编码任务列表**：只列 V33–V46 会漏掉 V47–V53 新拉起的并发批次 → 改进度日志 + checkpoint **自动发现**
2. **服务端 / WQ-BRAIN 任务无本地日志**：如 `set_RR11jN_`（mlh 账号、服务端仿真、本机零日志）→ 仅能经 WQ 控制台 / MCP 对话 / `query_wq_simulations()` 桥接可见
3. **账号维度盲区**：不同账号（主账号 mthyzx vs mlh vs tabbit）的任务互不可见于对方视角
4. **只写 checkpoint、不写进度日志的 scan 任务**：如 v52b（写 checkpoint 不写 `*_progress_*.log`）→ 加 catch-all 发现（扫描 `results/*checkpoint*.json` 未登记者，若近期更新且命中在飞 scan 线索则标"在飞扫描"）
5. **陷阱②（最阴）非 scan_v 命名的真实挖掘任务**：如 `tabbit_option9.py`、`tri_track_undug.py`（命令行含 `tri_track` 会被初版正则误判为 TRACKER，实为三轨挖掘、独立账号、CONCURRENCY=3）→ **必须人工改判单列**，不能漏

---

## 二、WQ 提交验证 · 四关层级（PASS_CHEAP ≠ 可提交）

> 2026-07-25 重大纠正：此前称"可提交 alpha"是过度声明。仿真**跑了 IS 指标** ≠ 满足提交标准。

| 关卡 | 内容 | 验证方式 | 本链现状 |
|------|------|----------|----------|
| **① 研究仿真 IS 廉价闸门** | S>1.58 / F>1.0 / TVR∈[0.05,0.30] / M>10bp / Ret>0.05 + 近闸 IS_LADDER/LOW_2Y | `cheap_gates`（本地，快） | ✅ 26 个 PASS/PASS_CHEAP |
| **② 生产仿真 OOS** | 样本外稳健性 | 生产 sim（平台，慢） | ❌ 未跑 |
| **③ 生产相关性 PROD_CORRELATION + 自相关** | WQ 真正提交闸门 | `wait_pc()`，仅进 `found_alphas` 者记录 prod_corr | ✅ 仅 **1** 个 `YPgAa3WR`(v39b, prod_corr=0.5325) 跨过；其余 25 个 **无 prod_corr 字段 = 生产关从未验** |
| **④ 平台 submittable + 真实提交** | 平台判定可提交 + 实际落平台 | 平台 API | ❌ 0 个（no_submit=True） |

**结论**：`PASS_CHEAP` = "廉价研究仿真闸门通过"，**不是"可提交"**。报告里这类候选必须标注「研究仿真 IS 闸通过、提交未验证」，不得称"可提交 alpha"。取证函数 `collect_verified_pids()`（取 `found_alphas` 的 pid = 真过生产相关性者）。

---

## 三、并发模型 · Token-Bucket（C=7，非固定槽位）

> 推翻"固定 2 槽"假设；关键认知：平台限速是**令牌桶**，不是静态并发槽。

- **令牌桶**：突发容量 **C≈7**，慢补充 ~1 令牌/20–40s。
- **安全包络**：瞬时并发提交 **≤6 绝对安全**；持续高频需 **≥15–20s 间隔一个**。
- **危险区**：同账号 ≥8 提交在 <2s 内并发必 429。
- **实测上限**：错峰 + 每进程闸门下曾安全跑过 **≤10 路并发零 429**（L≥10 确证但靠错峰）。
- **方案层最佳实践**（gen_report §4 评级基准）：
  ① multi-sim 批量提交（**1 令牌换 8 回测**，令牌效率 8×）；② 显式 `submit_gate`（瞬时≤6 / 批间≥45s / 429 退避）；③ 429 backoff；④ 禁齐射（同账号并发进程≤6）；⑤ 断点续跑 checkpoint。
- **统一架构**：`submit_gate.py` 跨进程文件锁 + 磁盘状态；`multi_sim.submit_multi_sim` 与 `wd_lib_wrapper.run_backtest` 两条提交路径都调 `wait_submit_slot()` → V34–V53 全部显式 gate（lint 25/25 通过）。
- **吞吐基准**：单进程 multi(8) ≈ 86 α/hr；8 进程错峰聚合 ≈ 4228 α/hr（7.5×，接近线性）→ **当前真正瓶颈 = 信号发现不是吞吐**（并发批次首步 Sharpe 远低于闸门）。

---

## 四、工作纪律（跨项目铁律）

1. **转向时机**：每轮验证超过 **10 种不同结构**（变体/字段/模板/信号构建）仍无满意效果，才考虑转向；不得只测 1–2 字段就下"信号方向无解"结论。
2. **断点续跑**：所有回测脚本必须 checkpoint / resume，只把拿到 pid 的确定结果算"已完成"，exception/no_pid 下次重试。
3. **label 碰撞 bug**：截断 label（如 `field[:20]`）会让不同字段同名覆盖 → 用完整字段名（v34 教训：324 唯一 label）。
4. **universe 合法性**：TOP500/TOP1000/TOP2000/TOP3000 合法；TOP800/1500/2500/5000 非法（平台 400 拒）。
5. **提交标准**：报告里 PASS_CHEAP 候选**不得称可提交**（见第二节四关）。
6. **监控第一视角**：必须机器级进程枚举为发现入口，日志只作明细（见第一节 + 盲区 5 类）。

---

## 五、工具速查

| 工具 | 作用 | 运行 |
|------|------|------|
| `gen_report.py` | 全链路监控报告（10 章节：进程盘点/并发/效率/候选验证） | `python deliverables/tools/gen_report.py`（从项目根运行） |
| `lint_submit_gate.py` | 检查全部 scan_*.py 是否经 submit_gate 统一限速 | `python deliverables/tools/lint_submit_gate.py` |
| `probe_concurrency.py` / `measure_L*.py` / `measure_rate.py` | 钉令牌桶 C 与上限 L 的探针（已证 C=7、L≥10） | 一次性调查用，勿常驻 |
| `_bench_v34_sim_speed.py` | multi(8) vs single 吞吐基准 | 基准参考 |

---
*固化日期：2026-07-25 · 关联记忆：项目 MEMORY.md ⑥ WQ 提交验证层级；用户级 MEMORY.md「WQ Alpha 提交标准/验证层级」铁律。*
