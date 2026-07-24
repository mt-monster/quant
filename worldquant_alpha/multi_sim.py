#!/usr/bin/env python3
"""BRAIN 真 multi-simulation 公共模块.

约定 (见 .cursor/rules/brain-multi-sim.mdc):
- 批量回测必须 POST list 到 /simulations (一次占 1 令牌跑 N 子任务)
- 禁止用 ThreadPool 对每个 alpha 单独 create_simulation 冒充 multi
- 推荐每批填满 8 条; 批间冷却 ≥45s; 提交间隔 ≥18s (Token-Bucket)
- 遇 429 按 refill 节奏退避 (submit_gate.backoff_429)

用法::

    from multi_sim import run_multi_batch
    results = run_multi_batch(api, batch)  # batch=[{label, expr, settings}, ...]
    # results=[{label, pid, ok, error?}, ...]
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from submit_gate import (
    DEFAULT_BATCH_COOLDOWN_SEC,
    backoff_429,
    batch_cooldown,
    envelope_summary,
    wait_submit_slot,
)

logger = logging.getLogger("multi_sim")

API_BASE = "https://api.worldquantbrain.com"
DEFAULT_BATCH_SIZE = 8
DEFAULT_COOLDOWN_SEC = DEFAULT_BATCH_COOLDOWN_SEC


def submit_multi_sim(session, sim_data_list: List[Dict], api, max_retries: int = 12) -> Optional[str]:
    """POST 一批仿真. 成功返回 progress Location; 400 返回 'BAD_REQUEST'; 失败返回 None.

    提交前经 submit_gate 跨进程匀速；429 按令牌桶 refill 退避。
    """
    n = len(sim_data_list)
    for attempt in range(max_retries):
        try:
            wait_submit_slot(tag=f"multi-sim n={n}")
            r = session.post(f"{API_BASE}/simulations", json=sim_data_list, timeout=120)
            if r.ok:
                loc = r.headers.get("Location") or ""
                if not loc:
                    try:
                        loc = (r.json() or {}).get("location", "") or ""
                    except Exception:
                        pass
                if loc:
                    return loc
                logger.error("multi-sim: no Location. body=%s", r.text[:200])
                return None
            if r.status_code == 429:
                backoff_429(attempt, tag="multi-sim")
                continue
            if r.status_code == 401:
                logger.warning("multi-sim 401, re-auth...")
                if hasattr(api, "_reauth"):
                    api._reauth()
                    session.cookies.clear()
                    session.cookies.update(api.session.cookies)
                continue
            if r.status_code == 400:
                logger.error("multi-sim 400: %s", r.text[:300])
                return "BAD_REQUEST"
            logger.warning("multi-sim HTTP %s, retry...", r.status_code)
            time.sleep(15)
        except Exception as e:
            logger.warning("multi-sim network: %s", e)
            time.sleep(15)
    return None


def poll_multi_sim(session, prog_url: str, max_wait: float = 900) -> Optional[List]:
    """轮询 multi-sim. 返回 children 列表; 超时 None; ERROR 返回 []."""
    started = time.monotonic()
    while time.monotonic() - started < max_wait:
        try:
            pr = session.get(prog_url, timeout=60)
            try:
                ra_val = float(pr.headers.get("Retry-After", "0") or 0)
            except Exception:
                ra_val = 0
            if ra_val > 0:
                time.sleep(ra_val)
                continue
            try:
                data = pr.json()
            except Exception:
                time.sleep(5)
                continue
            status = data.get("status", "")
            children = data.get("children") or []
            if status == "ERROR":
                logger.error("multi-sim ERROR: %s", str(data)[:200])
                return []
            if status == "COMPLETE" or children:
                return children
            time.sleep(5)
        except Exception as e:
            logger.warning("multi-sim poll: %s", e)
            time.sleep(10)
    logger.warning("multi-sim timeout after %ss", max_wait)
    return None


def get_child_alpha(session, child_id, api, max_retries: int = 8) -> Optional[str]:
    child_url = child_id if str(child_id).startswith("http") else f"{API_BASE}/simulations/{child_id}"
    for _ in range(max_retries):
        try:
            r = session.get(child_url, timeout=60)
            if r.ok:
                alpha_id = (r.json() or {}).get("alpha")
                if alpha_id:
                    return alpha_id
                try:
                    ra = float(r.headers.get("Retry-After", "0") or 0)
                except Exception:
                    ra = 0
                if ra > 0:
                    time.sleep(ra)
                    continue
            if r.status_code == 401 and hasattr(api, "_reauth"):
                api._reauth()
                session.cookies.clear()
                session.cookies.update(api.session.cookies)
                continue
            time.sleep(3)
        except Exception:
            time.sleep(5)
    return None


def build_sim_payload(expr: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "REGULAR", "settings": settings, "regular": expr}


def _fallback_single_paced(api, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """BAD_REQUEST 回退: 单条提交，但严格经 submit_gate 匀速，禁止齐射."""
    logger.error("Multi-sim BAD_REQUEST -> paced single fallback (interval gate ON)")
    out = []
    for i, b in enumerate(batch):
        try:
            # run_backtest 内部也会 wait_submit_slot；此处仅打日志区分
            logger.info("fallback single %d/%d %s", i + 1, len(batch), b.get("label"))
            res = api.run_backtest(b["expr"], settings=b["settings"])
            pid = res.get("platform_id") if res else None
            out.append({"label": b["label"], "pid": pid, "ok": bool(pid), "error": None if pid else "no_pid"})
        except Exception as e:
            out.append({"label": b["label"], "pid": None, "ok": False, "error": str(e)[:80]})
    return out


def run_multi_batch(
    api,
    batch: List[Dict[str, Any]],
    *,
    session=None,
    max_wait: float = 900,
    fallback_single: bool = True,
) -> List[Dict[str, Any]]:
    """对一批 alpha 做真 multi-sim.

    batch 元素: {"label", "expr", "settings"}
    返回: [{"label", "pid", "ok", "error"?}, ...] 顺序尽量与 batch 对齐.
    """
    if not batch:
        return []
    session = session or api.session
    labels = [b["label"] for b in batch]
    sim_data_list = [build_sim_payload(b["expr"], b["settings"]) for b in batch]

    prog_url = submit_multi_sim(session, sim_data_list, api)
    if prog_url == "BAD_REQUEST":
        if not fallback_single:
            return [{"label": lb, "pid": None, "ok": False, "error": "BAD_REQUEST"} for lb in labels]
        return _fallback_single_paced(api, batch)
    if not prog_url:
        return [{"label": lb, "pid": None, "ok": False, "error": "submit_failed"} for lb in labels]

    children = poll_multi_sim(session, prog_url, max_wait=max_wait)
    if children is None:
        return [{"label": lb, "pid": None, "ok": False, "error": "poll_timeout"} for lb in labels]
    if not children:
        return [{"label": lb, "pid": None, "ok": False, "error": "no_children"} for lb in labels]

    out = []
    for i, child in enumerate(children):
        label = labels[i] if i < len(labels) else f"child{i}"
        pid = get_child_alpha(session, child, api)
        out.append({"label": label, "pid": pid, "ok": bool(pid), "error": None if pid else "no_alpha_id"})
    for j in range(len(out), len(labels)):
        out.append({"label": labels[j], "pid": None, "ok": False, "error": "missing_child"})
    return out


def chunked(items: List[Any], size: int = DEFAULT_BATCH_SIZE) -> List[List[Any]]:
    size = max(1, int(size))
    return [items[i : i + size] for i in range(0, len(items), size)]


def after_batch_cooldown(sec: Optional[float] = None) -> float:
    """批间冷却辅助，供扫描脚本统一调用."""
    return batch_cooldown(sec)


__all__ = [
    "API_BASE",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_COOLDOWN_SEC",
    "submit_multi_sim",
    "poll_multi_sim",
    "get_child_alpha",
    "build_sim_payload",
    "run_multi_batch",
    "chunked",
    "after_batch_cooldown",
    "envelope_summary",
]
