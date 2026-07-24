#!/usr/bin/env python3
"""三轨 multi-sim 批装填: Explore / Improve / Settings-Rescue.

约定 (concurrency=8):
  - Explore  3: 新字段 / 未试骨架
  - Improve  3: 对历史 Top 候选做表达式突变 (窗口/符号/group)
  - Rescue   2: 近关候选仅改 settings (decay/neut/trunc/universe)

每批仍走一次真 multi-sim POST list, 不另开并行 multi。
提交节奏遵循 submit_gate（间隔≥18s / 批间≥45s / 瞬时≤6），见 probe 并发报告。
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger("tri_track")

# 默认槽位分配 (合计 8)
SLOT_EXPLORE = 3
SLOT_IMPROVE = 3
SLOT_RESCUE = 2

MAX_OPS_DEFAULT = 6


def count_operators(expr: str) -> int:
    low = expr.lower().replace(" ", "")
    if "trade_when(" in low or "add(" in low or "multiply(" in low:
        return 999
    if "*" in expr or re.search(r"(?<![eE])\+", expr):
        return 999
    return len(re.findall(r"[a-z_]+\(", expr.lower()))


def _key(v: Dict[str, Any]) -> Tuple:
    s = v.get("settings") or {}
    return (
        v.get("expr"),
        s.get("universe"),
        s.get("decay"),
        s.get("neutralization"),
        s.get("truncation"),
    )


def mix_batch(
    explore_q: List[Dict[str, Any]],
    improve_q: List[Dict[str, Any]],
    rescue_q: List[Dict[str, Any]],
    *,
    n_explore: int = SLOT_EXPLORE,
    n_improve: int = SLOT_IMPROVE,
    n_rescue: int = SLOT_RESCUE,
    batch_size: int = 8,
    seen: Optional[Set[Tuple]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """从三条队列各取若干条, 不足时用其他队列补满到 batch_size。"""
    seen = seen if seen is not None else set()
    batch: List[Dict[str, Any]] = []
    taken = {"explore": 0, "improve": 0, "rescue": 0}

    def take_from(q: List[Dict[str, Any]], track: str, n: int):
        while n > 0 and q and len(batch) < batch_size:
            v = q.pop(0)
            k = _key(v)
            if k in seen:
                continue
            seen.add(k)
            item = dict(v)
            item["track"] = track
            batch.append(item)
            taken[track] += 1
            n -= 1

    take_from(explore_q, "explore", n_explore)
    take_from(improve_q, "improve", n_improve)
    take_from(rescue_q, "rescue", n_rescue)

    # 补满: improve → explore → rescue
    for q, track in ((improve_q, "improve"), (explore_q, "explore"), (rescue_q, "rescue")):
        while len(batch) < batch_size and q:
            take_from(q, track, 1)

    return batch, taken


def select_top_candidates(
    results: Sequence[Dict[str, Any]],
    *,
    top_k: int = 8,
    min_abs_sharpe: float = 0.35,
) -> List[Dict[str, Any]]:
    """按 |Sharpe| 取 Top, 去重 expr (保留最佳 settings)。"""
    scored = []
    for r in results:
        s = r.get("sharpe")
        if s is None:
            continue
        try:
            sf = float(s)
        except Exception:
            continue
        if abs(sf) < min_abs_sharpe:
            continue
        if not r.get("expr"):
            continue
        scored.append(r)
    scored.sort(key=lambda x: abs(float(x.get("sharpe") or 0)), reverse=True)
    best_by_expr: Dict[str, Dict[str, Any]] = {}
    for r in scored:
        e = r["expr"]
        if e not in best_by_expr:
            best_by_expr[e] = r
        if len(best_by_expr) >= top_k:
            break
    return list(best_by_expr.values())


def _parse_int_windows(expr: str) -> List[int]:
    return [int(x) for x in re.findall(r"\b(\d+)\b", expr)]


def mutate_expr_windows(expr: str, max_ops: int = MAX_OPS_DEFAULT) -> List[Tuple[str, str]]:
    """窗口突变: 替换表达式中的整数窗口。"""
    out: List[Tuple[str, str]] = []
    wins = _parse_int_windows(expr)
    if not wins:
        return out
    # 常见替换表
    remap_sets = [
        {22: 10, 189: 126},
        {22: 44, 189: 252},
        {22: 10, 189: 252},
        {22: 5, 189: 126},
        {126: 63, 189: 126},
        {10: 5, 22: 10},
        {66: 22, 189: 126},
        {66: 120, 189: 252},
    ]
    for rm in remap_sets:
        new = expr
        changed = False
        for a, b in rm.items():
            # 只替换函数参数中的整数字面量 (简单: 逗号/括号旁)
            pat = re.compile(rf"(?<=[,(\s]){a}(?=[,)\s])")
            if pat.search(new):
                new2 = pat.sub(str(b), new)
                if new2 != new:
                    new = new2
                    changed = True
        if changed and new != expr and count_operators(new) < max_ops:
            tag = "w" + "_".join(f"{a}to{b}" for a, b in rm.items() if re.search(rf"(?<=[,(\s]){a}(?=[,)\s])", expr))
            out.append((tag[:40], new))
    return out


def mutate_expr_structure(expr: str, max_ops: int = MAX_OPS_DEFAULT) -> List[Tuple[str, str]]:
    """结构突变 (保持 ops<6, 禁 +/- 二元与 add/multiply)。"""
    cands: List[Tuple[str, str]] = []
    e = expr.strip()

    # 符号翻转
    if e.startswith("-"):
        cands.append(("unflip", e[1:]))
    else:
        cands.append(("flip", f"-{e}"))

    # industry -> sector / subindustry (若存在)
    for old, new, tag in (
        ("industry", "sector", "gsec"),
        ("industry", "subindustry", "gsub"),
        ("sector", "industry", "gind"),
        ("subindustry", "industry", "gind2"),
    ):
        if re.search(rf"\b{old}\b", e) and not re.search(rf"\b{new}\b", e):
            cands.append((tag, re.sub(rf"\b{old}\b", new, e, count=1)))

    # ts_mean(x, w) <-> ts_backfill 外包一层要小心 ops; 改为替换 ts_mean->ts_rank
    if "ts_mean(" in e:
        cands.append(("tsrank", e.replace("ts_mean(", "ts_rank(", 1)))
    if "ts_zscore(" in e and "ts_rank(" not in e:
        # ts_zscore -> ts_rank (同窗口)
        cands.append(("z2rank", e.replace("ts_zscore(", "ts_rank(", 1)))

    # 去最外层 rank(...)
    m = re.fullmatch(r"rank\((.*)\)", e)
    if m and count_operators(m.group(1)) < max_ops:
        cands.append(("norank", m.group(1)))

    # 加最外层 rank (若没有)
    if not e.startswith("rank(") and not e.startswith("-rank("):
        wrapped = f"rank({e})" if not e.startswith("-") else f"-rank({e[1:]})"
        if count_operators(wrapped) < max_ops:
            cands.append(("addrank", wrapped))

    # group_zscore 外包 / 去掉已有时改用 ts_zscore only — 仅当 ops 允许
    if "group_zscore(" not in e and "ts_zscore(" in e:
        # rank(ts_zscore(...)) -> rank(group_zscore(ts_zscore(...), industry))
        inner = e
        if inner.startswith("rank(") and inner.endswith(")"):
            core = inner[5:-1]
            neo = f"rank(group_zscore({core}, industry))"
            if count_operators(neo) < max_ops:
                cands.append(("addgz", neo))

    out = []
    seen = set()
    for tag, neo in cands:
        if neo == e or neo in seen:
            continue
        if count_operators(neo) >= max_ops:
            continue
        seen.add(neo)
        out.append((tag, neo))
    return out


def build_improve_variants(
    tops: Sequence[Dict[str, Any]],
    *,
    base_settings_fn: Optional[Callable] = None,
    max_ops: int = MAX_OPS_DEFAULT,
    max_per_parent: int = 12,
    label_prefix: str = "imp",
) -> List[Dict[str, Any]]:
    """对 Top 候选生成表达式改进变体 (继承父 settings 为主)。"""
    variants: List[Dict[str, Any]] = []
    seen: Set[Tuple] = set()
    for i, parent in enumerate(tops):
        expr0 = parent.get("expr") or ""
        s0 = copy.deepcopy(parent.get("settings") or {})
        if not expr0 or not s0:
            continue
        muts = mutate_expr_windows(expr0, max_ops) + mutate_expr_structure(expr0, max_ops)
        n = 0
        for tag, neo in muts:
            if n >= max_per_parent:
                break
            item = {
                "label": f"{label_prefix}_{i}_{tag}_{n}",
                "expr": neo,
                "settings": s0,
                "style": f"improve_{tag}",
                "field": parent.get("field") or parent.get("label"),
                "ops": count_operators(neo),
                "parent_label": parent.get("label"),
                "parent_sharpe": parent.get("sharpe"),
                "track": "improve",
            }
            k = _key(item)
            if k in seen:
                continue
            seen.add(k)
            variants.append(item)
            n += 1
    logger.info("improve pool: %d from %d tops", len(variants), len(tops))
    return variants


def build_rescue_variants(
    near: Sequence[Dict[str, Any]],
    *,
    max_per_parent: int = 10,
    label_prefix: str = "rsc",
) -> List[Dict[str, Any]]:
    """近关候选: 固定表达式, 扫 settings 抬 TVR/SUB/S。"""
    decays = [1, 2, 4, 6, 8]
    neuts = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET"]
    unis = ["TOP3000", "TOP2000", "TOP1000", "ILLIQUID_MINVOL1M"]
    truncs = [0.01, 0.02, 0.05, 0.08, 0.1]
    variants: List[Dict[str, Any]] = []
    seen: Set[Tuple] = set()
    for i, parent in enumerate(near):
        expr = parent.get("expr") or ""
        s0 = parent.get("settings") or {}
        if not expr or not s0:
            continue
        n = 0
        # 优先: 低 decay (抬 TVR) + 换 neut/uni
        grid = []
        for d in decays:
            for neut in neuts:
                for uni in unis:
                    for trunc in truncs:
                        if (
                            d == s0.get("decay")
                            and neut == s0.get("neutralization")
                            and uni == s0.get("universe")
                            and trunc == s0.get("truncation")
                        ):
                            continue
                        # 稀疏采样: 一次只改 1–2 维
                        diffs = (
                            int(d != s0.get("decay"))
                            + int(neut != s0.get("neutralization"))
                            + int(uni != s0.get("universe"))
                            + int(trunc != s0.get("truncation"))
                        )
                        if diffs > 2:
                            continue
                        grid.append((d, neut, uni, trunc, diffs))
        grid.sort(key=lambda x: (x[4], x[0]))  # 少改优先, 低 decay 优先
        for d, neut, uni, trunc, _ in grid:
            if n >= max_per_parent:
                break
            settings = copy.deepcopy(s0)
            settings.update({"decay": d, "neutralization": neut, "universe": uni, "truncation": trunc})
            item = {
                "label": f"{label_prefix}_{i}_d{d}_{neut[:3]}_{uni[:6]}_t{int(trunc*100)}_{n}",
                "expr": expr,
                "settings": settings,
                "style": "settings_rescue",
                "field": parent.get("field") or parent.get("label"),
                "ops": count_operators(expr),
                "parent_label": parent.get("label"),
                "parent_sharpe": parent.get("sharpe"),
                "track": "rescue",
            }
            k = _key(item)
            if k in seen:
                continue
            seen.add(k)
            variants.append(item)
            n += 1
    logger.info("rescue pool: %d from %d near", len(variants), len(near))
    return variants


def refill_queues_from_results(
    results: Sequence[Dict[str, Any]],
    explore_q: List[Dict[str, Any]],
    improve_q: List[Dict[str, Any]],
    rescue_q: List[Dict[str, Any]],
    *,
    seen: Set[Tuple],
    top_k: int = 6,
) -> None:
    """每批后用新结果补充 improve/rescue 队列 (explore 不动)。"""
    tops = select_top_candidates(results, top_k=top_k, min_abs_sharpe=0.35)
    if not tops:
        return
    new_imp = build_improve_variants(tops, label_prefix="impR")
    new_rsc = build_rescue_variants(tops, label_prefix="rscR")
    for v in new_imp:
        if _key(v) not in seen:
            improve_q.append(v)
    for v in new_rsc:
        if _key(v) not in seen:
            rescue_q.append(v)
