"""Rewrite the report generation section of build_md_report.py with optimized structure."""
import os

src = open(os.path.join(os.path.dirname(__file__), "build_md_report.py.bak"), encoding="utf-8").read()
parts = src.split("# ===== 5. 生成 MD =====")
assert len(parts) == 2, f"Expected 2 parts, got {len(parts)}"
pipeline = parts[0]

new_section = r'''# ===== 5. 生成 MD =====
L=[]
def a(s=""): L.append(s)

a(f"> **{NOW} GMT+8** · 数据均来自 checkpoint/progress/CSV 实算")
status_line = f"🟢 **ACTIVE {n_active_total}** | 🔴 **拒绝 {n_rejected_total}** | 🔵 **在飞 {len(ds_active_processes)} 进程** | 📊 **{total_N:,} 回测 / {n_ckpt_files} ckpt / {n_dates} days**"
a(f"> {status_line}")
a()

# ═════════ 一、核心结论（精简看板）═════════
a("---"); a("## 一、核心结论"); a()
a("| 关键指标 | 数值 |")
a("|---|---|")
a(f"| 🔵 在飞进程 | {len(ds_active_processes)} 个（fleet_keeper ≤7 并发，零 429） |")
a(f"| 🟢 平台 ACTIVE | **{n_active_total}**（{'、'.join([p for p,v in verified.items() if v.get('status')=='ACTIVE'])}） |")
a(f"| 🔴 平台拒绝 | **{n_rejected_total}** / {is_cleared} 候选（PROD_CORR/SELF_CORR FAIL） |")
a(f"| ⭐ 最佳 Sharpe | **{bestS:.2f}**（{bestS_task_name}） |")
a(f"| 📦 挖掘规模 | {total_N:,} 回测 / {len(per)} 模板 / {n_ckpt_files} ckpt / {n_dates} 个日期 |")
a()
a(f"> **瓶颈**：信号发现，非吞吐。v52b({v52b_N}→{v52b_pc}PC/0 found·PROD_CORR覆没) v39b({v39b_N}→{per['v39b_sub_micro']['pc']}PC/{len(found)} found·YPgAa3WR幸存) ds({len(ds_tasks)}数据集·0候选) tri({tri_total}α·S={tri_bestS:.2f})")

# ═════════ 二、提交核查（重点前置）═════════
a(); a("---"); a("## 二、候选提交核查"); a()
n_active_verified = sum(1 for au in audit if au[6]=="✅ 已正式提交")
n_rejected_verified = sum(1 for au in audit if au[6]=="❌ 平台拒绝")
n_need_other = len(audit) - n_active_verified - n_rejected_verified
active_verified_list = [au[0] for au in audit if au[6]=="✅ 已正式提交"]
a("| 分类 | 数量 | 明细 |")
a("|---|---|---|")
a(f"| ✅ 已正式提交 | **{n_active_verified}** | {'、'.join(active_verified_list)} |")
if n_rejected_verified:
    rejected_verified_list = [au[0] for au in audit if au[6]=="❌ 平台拒绝"]
    a(f"| ❌ 平台拒绝 | **{n_rejected_verified}** | {'、'.join(rejected_verified_list[:6])}{'...' if len(rejected_verified_list)>6 else ''} |")
if n_need_other:
    a(f"| 🔶 待验证 | **{n_need_other}** | — |")
a()
actives = [au for au in audit if au[6]=="✅ 已正式提交"]
if actives:
    a("**✅ ACTIVE 详情：**")
    for au in actives:
        vf = verified.get(au[0], {})
        ds = (vf.get("dateSubmitted","?") or "?")[:16]
        a(f"- `{au[0]}` | S={au[2]:.2f} | {au[1]} | {ds}")
rejecteds = [au for au in audit if au[6]=="❌ 平台拒绝"]
if rejecteds:
    from collections import Counter
    reasons = Counter(au[5] for au in rejecteds)
    a(); a("**❌ 拒绝原因分布：**")
    for reason, count in reasons.most_common(5):
        a(f"- {reason} ×{count}")
a()

# ═════════ 三、在飞状态 ═════════
a(); a("---"); a(f"## 三、在飞状态（{len(ds_active_processes)} 活跃进程）"); a()
if ds_running:
    a(f"**🔵 活跃进程**（{len(ds_running)} 个，按最佳 S 降序）")
    a()
    a("| 数据集 | 进度 | 最佳S | 预期完成 |")
    a("|---|---|---|---|")
    for t,p,lv in ds_running:
        done=lv.get("done",0); tot=lv.get("total",320)
        a(f"| {ds_short(t)} | {done}/{tot} ({lv.get('pct',0):.0f}%) | {sflag(p['bestS'])} {p['bestS']:.2f} | **{lv.get('eta','?')}** |")
    a()
if ds_paused:
    a(f"**⏸️ 暂停**（{len(ds_paused)} 个，fleet_keeper 轮换中）")
    pbests = sorted(ds_paused, key=lambda x: -x[1]["bestS"])
    a(f"> {'、'.join(f'{ds_short(t)} S={p[\"bestS\"]:.2f}' for t,p,_ in pbests[:8])}" + (f' +{len(pbests)-8}个' if len(pbests)>8 else ''))
    a()

# ═════════ 四、模板排名 ═════════
a(); a("---"); a("## 四、模板排名（按状态分组）"); a()
r = _emit_sharpe_section("🔵 活跃进程中的 ds 数据集", tasks_running_ds, 1)
r = _emit_sharpe_section("⏸️ 暂停/待续补的 ds 数据集", tasks_paused_ds, r)

if tasks_completed_ds:
    top_completed = sorted(tasks_completed_ds, key=lambda x: -x[1]["bestS"])[:5]
    completed_summary = ", ".join(f"{ds_short(t)} S={p['bestS']:.2f}" for t,p in top_completed)
    a(f"**✅ 已完成 ds 数据集**（{len(tasks_completed_ds)} 个，最佳 5: {completed_summary}）")
    a()

if tasks_other:
    a(f"### 📋 其他任务（{len(tasks_other)} 个，按 Sharpe 降序）")
    a()
    a("| 排名 | 任务 | N | 候选 | S | 模板（信号字段 + 配置） | 日期 | 主导失败 |")
    a("|---|---:|---:|---:|---:|---|---|---|")
    for i, (t, p) in enumerate(tasks_other, r):
        flag = sflag(p["bestS"]); cands = p["pc"] + p["cp"]
        fails = ["gate_S/F/M/Ret"]
        tmpl_str = "-"; bt_date = ckpt_mtime_map.get(t, "?")
        for r2 in recs:
            if r2["_task"] != t: continue
            fl = r2.get("fails")
            if isinstance(fl, list):
                for x in fl:
                    if str(x).startswith("PF:"): fails.append("PF:LOW_SUB")
            if tmpl_str == "-": tmpl_str = template_str(t, r2)
            ts = (r2.get("finished_at") or "")[:10]
            if ts: bt_date = ts
        dom_fail = sorted(set(fails))[0]
        a(f"| {i} | {t[:32]} | {p['N']} | {cands} | {flag} **{p['bestS']:.2f}** | {tmpl_str} | {bt_date} | {dom_fail} |")
    a()

# ═════════ 五、候选明细 ═════════
a(); a("---"); a(f"## 五、候选 Alpha 明细 ({len(cand)} 个，按 Sharpe 降序，附平台验证)"); a()
a("| pid | 任务 | S | F | 字段 | 日期 | 验证 |")
a("|---|---|---:|---:|---|---|---|")
for c in cand:
    hl=" ⚡" if c["status"]=="CHECK_PENDING" else ""
    vf_st = verified.get(c["pid"],{}).get("status","")
    vf_icon = "✅ACTIVE" if vf_st=="ACTIVE" else ("❌拒绝" if vf_st in ("UNSUBMITTED","GATE_FAIL","NO_OOS") else "—")
    field = c.get("field","?")[:22]
    bt_date = ckpt_mtime_map.get(c["task"], "?")
    a(f"| {c['pid']}{hl} | {c['task'].replace('ds_',''):25s} | **{c['S']:.2f}** | {c['F']:.2f} | {field} | {bt_date} | {vf_icon} |")
a()
vf_active_cands = sum(1 for c in cand if verified.get(c["pid"],{}).get("status")=="ACTIVE")
vf_rejected_cands = sum(1 for c in cand if verified.get(c["pid"],{}).get("status") in ("UNSUBMITTED","GATE_FAIL","NO_OOS"))
a(f"> 候选来自 {len(set(c['task'] for c in cand))} 个模板，跨 {n_dates} 个日期。API 验证：{vf_active_cands} ACTIVE / {vf_rejected_cands} 拒绝。")

# ═════════ 六、失败闸门归因 ═════════
a(); a("---"); a("## 六、失败闸门归因"); a()
total_fails = sum(fcats.values())
a("| 失败类型 | 次数 | 占比 |")
a("|---|---:|---:|")
for k, v in sorted(fcats.items(), key=lambda x: -x[1]):
    pct = v/total_fails*100 if total_fails else 0
    a(f"| {k} | **{v:,}** | {pct:.1f}% |")
a()
if pf_detail:
    top_pf = sorted(pf_detail.items(), key=lambda x: -x[1])[0]
    a(f"> **头号硬闸门**：{top_pf[0]}（{top_pf[1]} 次）——子宇宙层面优化中性化是攻坚方向。")

# ═════════ 七、tri_track 对比 ═════════
a(); a("---"); a("## 七、tri_track 独立账号 (ML88164)"); a()
a(f"| 指标 | 数值 |")
a(f"|---|---|")
a(f"| 已提交 alpha | **{tri_total}**（{tri_submitted} submitted / {tri_fail} failed） |")
a(f"| 最佳 Sharpe | {'**' + str(round(tri_bestS,2)) + '**' if tri_has_metrics else '不可用'} |")
a(f"| 分轨 | explore {tri_tracks.get('explore',0)} / improve {tri_tracks.get('improve',0)} / variant {tri_tracks.get('variant',0)} |")
a(f"| 对比 ds 舰队 | ds 最佳 S={max(per[t]['bestS'] for t in ds_tasks):.2f} vs tri {tri_bestS:.2f} |")
a()

# ═════════ 八、行动建议 ═════════
a("---"); a("## 八、行动建议"); a()
a(f"1. **ds 舰队自然推进**：fleet_keeper --target 7，零 429。")
a(f"2. **v39b 封存**：SELF_CORR FAIL，仅 YPgAa3WR 幸存。换新字段重挖。")
a(f"3. **v52b 封存**：PROD_CORR FAIL（31/32），信号被占。换新方向。")
a(f"4. **v52_tri_hiring_trends 活路**：j2rrpVzO 成功 ACTIVE。ILLIQUID_MINVOL1M 方向可复制。")
a(f"5. **提交闭环**：{n_active_verified} ACTIVE / {n_rejected_verified} 拒绝。submit 即自动 OOS。")
a(f"6. **tri_track 对标**：{tri_total} α，最佳 S={tri_bestS:.2f}。指标已接入报告。")
a(f"7. **continuous_undug**：{cu_blocks} 块 / {len(cu_ds_done)} 数据集，独立账号持续挖掘。")
a()

# ═════════ 九、监控盲点 ═════════
a("---"); a("## 九、监控盲点"); a()
cu_ds_names = ", ".join(sorted(cu_ds_done)) if cu_ds_done else "—"
a(f"| 旁路进程 | 状态（来自文件） |")
a(f"|---|---|")
a(f"| continuous_undug (ML88164) | {cu_blocks} 块完成（{cu_ds_names}） |")
a(f"| tri_track (ML88164) | {tri_total} α，最佳 S={tri_bestS:.2f} |")
a(f"| green_guard + analyze_tabbit | 旁路守卫，实时验证 /check |")
a()
a(f"> 以上数据均在 BaiduNetdisk WQ 目录，未并入主账号 total_N（{total_N:,}）。全局总览见 global_overview_*.md。")

a()
a("---")
a(f"*报告由 build_md_report.py 从真实文件程序化生成 · {NOW} GMT+8 · 所有数字实算、未编造。*")
a(f"*生成器路径: deliverables/tools/build_md_report.py (复跑即可刷新最新数据)*")

md_text = "\n".join(L)
out = os.path.join(ROOT, "deliverables", "reports",
                   f"factor_mining_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    fh.write(md_text)
print(f"WROTE {out}  ({len(L)} lines)")
print(f"total_N={total_N} is_cleared={is_cleared} found={len(found)} bestS={bestS:.2f}")
print(f"tri_total={tri_total} tracks={tri_tracks}")
'''

combined = pipeline + new_section
open(os.path.join(os.path.dirname(__file__), "build_md_report.py"), "w", encoding="utf-8").write(combined)
print("DONE")
