# -*- coding: utf-8 -*-
"""拆分 factor_mining_report 为主摘要文档 + 独立明细文档。
解析现有 MD 文件，提取数据段，生成带链接的主摘要版。"""
import re, os

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "deliverables", "reports", "factor_mining_report_20260727_0155.md")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "deliverables", "reports", "details")
os.makedirs(OUT_DIR, exist_ok=True)

text = open(SRC, encoding="utf-8").read()
lines = text.split("\n")

# --- find all ## section boundaries ---
h2_positions = []  # [(line_idx, title)]
for i, line in enumerate(lines):
    m = re.match(r"^## (.+)", line)
    if m:
        h2_positions.append((i, m.group(1)))

# extract section content: [start, end)
sections = {}
for idx in range(len(h2_positions)):
    start = h2_positions[idx][0]
    end = h2_positions[idx+1][0] if idx+1 < len(h2_positions) else len(lines)
    sections[h2_positions[idx][1]] = (start, end)

# --- define which sections are "detail-heavy" (extract) vs "summary" (keep) ---
# sections to EXTRACT as standalone files:
extract_sections = {
    "四、ds 舰队实时详情 (7 活跃进程 / 14 数据集记录在档)": {
        "file": "detail_ds_fleet.md",
        "title": "DS 舰队实时详情",
        "desc": "活跃进程 / 暂停 / 已完成 / ETA 汇总",
        "summary": "{n_running} 活跃进程，{n_paused} 暂停，{n_completed} 已完成。",
    },
    "五、主账号全任务最佳 Sharpe 排名 (含 ds 舰队)": {
        "file": "detail_sharpe_ranking.md",
        "title": "全任务 Sharpe 排名",
        "desc": "按状态分组：活跃 / 暂停 / 已完成 / 其他，含模板信号字段+配置+日期",
        "summary": "{n_templates} 个模板，按 Sharpe 降序分组展示。",
    },
    "六、tri_track 独立账号详情 (🛡️ ML88164)": {
        "file": "detail_tri_track.md",
        "title": "tri_track 独立账号详情",
        "desc": "ML88164 独立账号 α 产出与回测指标",
        "summary": "独立账号 ML88164 产出与指标详情。",
    },
    "七、失败闸门分析": {
        "file": "detail_failure_gates.md",
        "title": "失败闸门归因分析",
        "desc": "各类失败闸门的分布及占比",
        "summary": "各类失败闸门分布及头号瓶颈。",
    },
    "八、候选 Alpha 明细 (47 个，按 Sharpe 降序)": {
        "file": "detail_candidates.md",
        "title": "候选 Alpha 详细列表",
        "desc": "47 个候选的 Sharpe/Fitness/字段/配置/日期/平台验证状态",
        "summary": "47 个候选，2 ACTIVE / 45 拒绝。",
    },
    "九、候选因子提交核查（逐项审计）": {
        "file": "detail_submission_audit.md",
        "title": "候选因子提交核查",
        "desc": "ACTIVE / 拒绝 / 待验证，逐项审计",
        "summary": "2 ACTIVE / 45 拒绝。提交即自动 OOS。",
    },
}

# sections to KEEP as-is:
keep_sections = [
    "一、核心结论（结论先行）",
    "二、提交就绪漏斗",
    "三、ds 舰队 vs tri_track 独立账号（对比）",
    "十、问题说明（问题其次）",
    "十一、行动建议（方案最后）",
    "十二、监控盲点：独立账号旁路进程（数据驱动补充）",
    "十三、按维度逐层展开（账号 → 模板 → 日期）",
]

# --- extract sections to standalone files ---
extracted = {}
for sec_title, cfg in extract_sections.items():
    if sec_title in sections:
        start, end = sections[sec_title]
        content_lines = lines[start:end]
        
        # build detail doc with metadata header
        detail_content = [f"# {cfg['title']}", "", f"> {cfg['desc']}", f"> 来源：原报告对应章节自动提取", ""]
        detail_content.extend(content_lines)
        
        fpath = os.path.join(OUT_DIR, cfg["file"])
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("\n".join(detail_content))
        print(f"  WROTE {cfg['file']} ({len(content_lines)} lines)")

# --- also extract section 十三 as hierarchical drill-down ---
if "十三、按维度逐层展开（账号 → 模板 → 日期）" in sections:
    start, end = sections["十三、按维度逐层展开（账号 → 模板 → 日期）"]
    content_lines = lines[start:end]
    detail_content = ["# 三维层级钻取（账号 → 模板 → 日期）", "", "> 按账号 → 因子模板 → 回测日期递进展开", ""]
    detail_content.extend(content_lines)
    fpath = os.path.join(OUT_DIR, "detail_hierarchical_drilldown.md")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(detail_content))
    print(f"  WROTE detail_hierarchical_drilldown.md ({len(content_lines)} lines)")
    extracted["十三"] = True

# --- now build the main summary document ---
summary_parts = []

# add header metadata
summary_parts.append("> **因子挖掘综合摘要** · 快照 " + lines[0].split("GMT+8")[0].split(": ")[-1].strip() if "GMT+8" in lines[0] else "2026-07-27")
summary_parts.append("> 主文档仅含摘要与关键结论。完整明细数据请点击各章 `📎` 链接查看。")
summary_parts.append("")

# Note: the original line 0-1 have the snapshot metadata. The first bullet line is at 3.
# Let's reconstruct properly: keep the original metadata, add structure.
summary_parts.append(lines[0])  # 数据快照行
summary_parts.append("")

# Add the critical finding line
summary_parts.append(lines[3])  # "提交验证最重要结论"

# Now go through sections in order and either keep them or link them
link_index = 1

# Collect the actual section order from the report
ordered_titles = [h2[1] for h2 in h2_positions]

for title in ordered_titles:
    parts = title.split("。")[0].split("，")[0].split("（")[0].strip()
    
    if title in extract_sections:
        cfg = extract_sections[title]
        summary_parts.append("")
        summary_parts.append("---")
        summary_parts.append(f"## {title}")
        summary_parts.append("")
        
        # Extract key numbers from the section content
        start, _ = sections[title]
        # parse the first few lines after ## header to find key numbers
        stext = "\n".join(lines[start+1:start+15])
        
        # Build a compact summary from the data
        summary_parts.append(f"> 📊 {cfg['desc']}")
        summary_parts.append("")
        summary_parts.append(f"📎 [查看完整明细](details/{cfg['file']})")
        summary_parts.append("")
    elif title in keep_sections:
        start, end = sections[title]
        summary_parts.extend(lines[start:end])
    elif title.startswith("十三"):
        summary_parts.append("")
        summary_parts.append("---")
        summary_parts.append(f"## {title}")
        summary_parts.append("")
        summary_parts.append(f"> 按账号 → 因子模板 → 回测日期三层递进展开。")
        summary_parts.append("")
        summary_parts.append(f"📎 [查看完整层级钻取](details/detail_hierarchical_drilldown.md)")
        summary_parts.append("")

out_path = os.path.join(os.path.dirname(SRC), "factor_mining_summary.md")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(summary_parts))
print(f"\nWROTE summary: {out_path} ({len(summary_parts)} lines)")
print(f"Detail files in: {OUT_DIR}")
