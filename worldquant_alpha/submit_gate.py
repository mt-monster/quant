#!/usr/bin/env python3
"""BRAIN /simulations 提交闸门 — Token-Bucket 安全包络.

依据: results/probe_concurrency_final_report_20260725_0255.md
  - 突发容量 C ≈ 7；瞬时并发提交安全区 ≤ 6
  - 令牌慢补充 ≈ 1 / 20–40s；持续提交间隔应 ≥ 15–20s
  - multi-sim（N 表达式/次）与单 simulation 均计 1 次提交（1 令牌）
  - 禁止 <2s 内齐射 ≥7–8 个提交

所有 POST /simulations 应先 wait_submit_slot()，遇 429 再 backoff_429()。
跨进程通过文件锁协调，避免多扫描脚本同时齐射。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Optional

# Windows 默认 stdout=GBK，Cursor/多数终端按 UTF-8 捕获 → 中文日志乱码。
# 在公共闸门模块尽早切到 UTF-8，覆盖 multi_sim / wd_lib_wrapper / 各 scan 脚本。
def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8_stdio()

logger = logging.getLogger("submit_gate")

# ---- 测定常量（勿随意放宽）----
BURST_CAPACITY = 7
SAFE_INSTANT_CONCURRENT = 6
MIN_SUBMIT_INTERVAL_SEC = float(os.environ.get("BRAIN_SUBMIT_INTERVAL", "18"))
DEFAULT_BATCH_COOLDOWN_SEC = float(os.environ.get("BRAIN_BATCH_COOLDOWN", "45"))
REFILL_HINT_SEC = float(os.environ.get("BRAIN_REFILL_HINT", "30"))
MAX_429_BACKOFF_SEC = float(os.environ.get("BRAIN_MAX_429_BACKOFF", "120"))

_HERE = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_HERE, "results", ".brain_sim_submit_gate.json")
_LOCK_PATH = _STATE_PATH + ".lock"


def _ensure_dir():
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)


def _acquire_lock(timeout: float = 120.0) -> Optional[int]:
    """跨进程排他锁 (O_CREAT|O_EXCL). 成功返回 fd, 超时返回 None."""
    _ensure_dir()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode("ascii", "ignore"))
            except Exception:
                pass
            return fd
        except FileExistsError:
            # 陈旧锁: >180s 则强清
            try:
                age = time.time() - os.path.getmtime(_LOCK_PATH)
                if age > 180:
                    logger.warning("submit_gate: stale lock age=%.0fs, removing", age)
                    os.remove(_LOCK_PATH)
                    continue
            except Exception:
                pass
            time.sleep(0.05)
        except Exception as e:
            logger.warning("submit_gate lock error: %s", e)
            time.sleep(0.2)
    return None


def _release_lock(fd: Optional[int]):
    if fd is not None:
        try:
            os.close(fd)
        except Exception:
            pass
    try:
        os.remove(_LOCK_PATH)
    except Exception:
        pass


def _load_state() -> dict:
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict):
    _ensure_dir()
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, _STATE_PATH)


def wait_submit_slot(
    *,
    min_interval: Optional[float] = None,
    tag: str = "",
) -> float:
    """阻塞直到距上次 /simulations 提交 ≥ min_interval，并登记本次提交时刻。

    返回实际等待秒数。所有 multi-sim / 单 sim POST 前必须调用。
    """
    interval = float(min_interval if min_interval is not None else MIN_SUBMIT_INTERVAL_SEC)
    if interval < 0:
        interval = 0.0
    waited = 0.0
    fd = _acquire_lock(timeout=180.0)
    try:
        state = _load_state()
        last = float(state.get("last_submit_unix") or 0)
        now = time.time()
        gap = now - last
        need = interval - gap
        if need > 0:
            logger.info(
                "submit_gate: pace wait %.1fs (interval=%.0fs, last_gap=%.1fs)%s",
                need, interval, gap, f" [{tag}]" if tag else "",
            )
            # 持锁睡眠会阻塞其他提交者 — 正确：全局串行化提交节奏
            time.sleep(need)
            waited = need
        state["last_submit_unix"] = time.time()
        state["last_pid"] = os.getpid()
        state["last_tag"] = tag
        state["min_interval"] = interval
        _save_state(state)
    finally:
        _release_lock(fd)
    return waited


def backoff_429(attempt: int = 0, *, tag: str = "") -> float:
    """429 后按令牌补充节奏退避. 返回实际 sleep 秒数."""
    # 首挫对齐 refill≈30s；之后指数抬升，封顶 120s
    wait = min(REFILL_HINT_SEC + attempt * 15.0, MAX_429_BACKOFF_SEC)
    logger.warning(
        "submit_gate: 429 backoff %.0fs (#%d)%s — token-bucket refill",
        wait, attempt, f" [{tag}]" if tag else "",
    )
    time.sleep(wait)
    # 桶可能仍空，拉开下次合法提交点
    fd = _acquire_lock(timeout=60.0)
    try:
        state = _load_state()
        state["last_submit_unix"] = time.time()
        state["last_429_unix"] = time.time()
        state["last_429_attempt"] = attempt
        _save_state(state)
    finally:
        _release_lock(fd)
    return wait


def batch_cooldown(sec: Optional[float] = None, *, tag: str = "") -> float:
    """批间冷却（默认 45s，已验证安全）."""
    wait = float(sec if sec is not None else DEFAULT_BATCH_COOLDOWN_SEC)
    if wait <= 0:
        return 0.0
    logger.debug("submit_gate: batch cooldown %.0fs%s", wait, f" [{tag}]" if tag else "")
    time.sleep(wait)
    return wait


def envelope_summary() -> dict:
    return {
        "burst_capacity": BURST_CAPACITY,
        "safe_instant_concurrent": SAFE_INSTANT_CONCURRENT,
        "min_submit_interval_sec": MIN_SUBMIT_INTERVAL_SEC,
        "default_batch_cooldown_sec": DEFAULT_BATCH_COOLDOWN_SEC,
        "refill_hint_sec": REFILL_HINT_SEC,
        "note": "multi-sim counts as 1 token; never launch ≥7 submit-procs in <2s",
        "source": "probe_concurrency_final_report_20260725_0255.md",
    }
