#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机器级 WQ 提交闸门 (wq_global_gate).

根治 429 的核心: 让同 IP 上所有提交者 (v53 / fw / 未来脚本) 共享
同一把锁 + 同一个全局退避状态, 任一客户端收到 429 都把全局
`backoff_until` 推后, 所有提交者遵守 -> 退避可跨进程/跨客户端传播.

设计依据 (probe_concurrency_final_report_20260725_0255.md):
  - 令牌桶限 POST /simulations 的瞬时集中度, 突发容量 C≈7, 安全区 ≤6
  - 令牌慢补充 ≈ 1/20-40s; 持续提交间隔应 ≥15-20s
  - multi-sim 与单 sim 均计 1 次提交 (1 令牌)
  - 禁止 <2s 内齐射 ≥7-8 个提交

本模块提供:
  - wait_submit_slot(min_interval, tag): 阻塞到距上次提交 ≥interval 且过了全局 backoff_until;
    在锁内预留"计划提交时刻"并落盘, 再释放锁去睡 -> 并发进程自动排到其后, 杜绝齐射.
  - note_429(resp, attempt, tag): 把全局 backoff_until 推后 (优先服务端 Retry-After), 不睡眠,
    让调用方自己的重试循环处理等待.
  - backoff_429(attempt, tag): 兼容旧调用 (v53 multi_sim) -> 睡眠 + note_429.
  - patch_requests(): monkey-patch requests.Session.request, 对 POST …/simulations 与 …/submit
    自动走闸门. 供 sitecustomize 加载, 零逐文件改业务代码.

锁/状态文件位于本模块同目录 (机器级固定位置), 不依赖任何项目目录.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger("wq_global_gate")

# ---- 可调常量 (环境变量可覆盖) ----
MIN_SUBMIT_INTERVAL_SEC = float(os.environ.get("WQ_GLOBAL_INTERVAL", "20"))
DEFAULT_BATCH_COOLDOWN_SEC = float(os.environ.get("WQ_GLOBAL_BATCH_COOLDOWN", "45"))
REFILL_HINT_SEC = float(os.environ.get("WQ_GLOBAL_REFILL", "30"))
MAX_429_BACKOFF_SEC = float(os.environ.get("WQ_GLOBAL_MAX_BACKOFF", "120"))
MAX_INFLIGHT = int(os.environ.get("WQ_GLOBAL_MAX_INFLIGHT", "4"))

BURST_CAPACITY = 7
SAFE_INSTANT_CONCURRENT = 6

_HERE = os.environ.get("WQ_GATE_DIR") or os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_HERE, ".wq_global_submit_gate.json")
_LOCK_PATH = _STATE_PATH + ".lock"

# 在途并发计数 (进程内); 跨进程靠 last_submit_unix + backoff_until 协调
_inflight = 0
_inflight_lock = threading.Lock()
_inflight_cv = threading.Condition(_inflight_lock)


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8_stdio()


def _ensure_dir():
    os.makedirs(_HERE, exist_ok=True)


def _acquire_lock(timeout: float = 180.0) -> Optional[int]:
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
            try:
                age = time.time() - os.path.getmtime(_LOCK_PATH)
                if age > 180:
                    logger.warning("wq_global_gate: stale lock age=%.0fs, removing", age)
                    os.remove(_LOCK_PATH)
                    continue
            except Exception:
                pass
            time.sleep(0.05)
        except Exception as e:
            logger.warning("wq_global_gate lock error: %s", e)
            time.sleep(0.2)
    return None


def _release_lock(fd: Optional[int]):
    # 仅在真正持有锁 (fd 有效) 时才删除锁文件; fd=None 表示获取超时,
    # 此时锁属于别的进程, 绝不能误删 (否则并发进程会双双"持锁"导致齐射).
    if fd is None:
        return
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


def wait_submit_slot(*, min_interval: Optional[float] = None, tag: str = "") -> float:
    """阻塞直到距上次提交 ≥ interval 且过了全局 backoff_until; 预留并登记提交时刻.

    返回实际等待秒数. 所有 POST /simulations (及 /alphas/.../submit) 前必须调用.

    关键设计 (修复竞态/冷启动齐射):
      - 在锁内把 last_submit_unix 写为"计划提交时刻 earliest"并落盘, 再释放锁去睡.
        并发进程抢到锁时会看到已预留的槽, 自动排到其后, 杜绝两客户端齐射.
      - 冷启动 last=0 时钳制为 now-interval, 强制首对也间隔 interval.
      - 睡眠在锁外进行, 故并发的 note_429 可随时更新全局 backoff_until.
      - 睡醒后二次复查 backoff_until, 若睡眠期间被推后则延长.
    """
    interval = float(min_interval if min_interval is not None else MIN_SUBMIT_INTERVAL_SEC)

    # 进程内在途并发上限
    with _inflight_cv:
        while _inflight >= MAX_INFLIGHT:
            _inflight_cv.wait(timeout=5.0)

    t_begin = time.time()
    for _round in range(100):  # 正常 1 轮; 睡眠期间全局退避被推后才会多轮
        # ---- 第一步: 锁内决策 + 预留槽 ----
        fd = _acquire_lock(timeout=180.0)
        try:
            state = _load_state()
            now = time.time()
            last_raw = float(state.get("last_submit_unix") or 0)
            # 冷启动保护: last 从未写或过于陈旧 -> 视为刚刚提交过, 强制本客户端等 interval
            last = last_raw if (last_raw > 0 and (now - last_raw) <= interval * 4) else (now - interval)
            backoff_until = float(state.get("backoff_until") or 0)
            earliest = max(last + interval, backoff_until)
            if earliest < now:
                earliest = now
            state["last_submit_unix"] = earliest
            state["last_pid"] = os.getpid()
            state["last_tag"] = tag
            state["min_interval"] = interval
            _save_state(state)
            if os.environ.get("WQ_GATE_DEBUG") == "1":
                print(f"[DBG {os.getpid()}] round={_round} lock_fd={fd} last_raw={last_raw:.3f} last={last:.3f} earliest={earliest:.3f} backoff={backoff_until:.3f}", flush=True)
        finally:
            _release_lock(fd)

        # ---- 第二步: 锁外睡眠到预留时刻 (期间他人 note_429 可推后全局退避) ----
        sleep_for = earliest - time.time()
        if sleep_for > 0:
            logger.info(
                "wq_global_gate: pace wait %.1fs (interval=%.0fs)%s",
                sleep_for, interval, f" [{tag}]" if tag else "",
            )
            time.sleep(sleep_for)

        # ---- 第三步: 复查全局退避. 若睡眠期间被推后, 本槽作废 -> 重新预留 ----
        bu_now = float(_load_state().get("backoff_until") or 0)
        if bu_now <= earliest:
            return time.time() - t_begin
        logger.info(
            "wq_global_gate: slot %.3f voided by global backoff (until %.3f), re-reserving%s",
            earliest, bu_now, f" [{tag}]" if tag else "",
        )
    return time.time() - t_begin


def note_429(resp=None, attempt: int = 0, *, tag: str = "") -> float:
    """记录一次 429: 把全局 backoff_until 推后 (优先服务端 Retry-After). 不睡眠.

    返回实际推后的秒数. 调用方自己的重试循环按服务端 Retry-After 等待即可.
    """
    now = time.time()
    pen = None
    if resp is not None:
        try:
            ra = float(resp.headers.get("Retry-After", 0) or 0)
        except Exception:
            ra = 0
        if ra > 0:
            pen = ra
    if pen is None:
        pen = min(REFILL_HINT_SEC + attempt * 15.0, MAX_429_BACKOFF_SEC)
    until = now + pen
    fd = _acquire_lock(timeout=60.0)
    try:
        state = _load_state()
        prev = float(state.get("backoff_until") or 0)
        state["backoff_until"] = max(prev, until)
        state["last_429_unix"] = now
        state["last_429_tag"] = tag
        state["last_429_attempt"] = attempt
        _save_state(state)
        logger.warning(
            "wq_global_gate: 429 noted -> backoff_until +%.0fs (global, max so far +%.0fs)%s",
            pen, state["backoff_until"] - now, f" [{tag}]" if tag else "",
        )
    finally:
        _release_lock(fd)
    return pen


def backoff_429(attempt: int = 0, *, tag: str = "") -> float:
    """兼容旧调用 (v53 multi_sim): 睡眠 + 全局退避传播."""
    pen = note_429(attempt=attempt, tag=tag)
    logger.warning(
        "wq_global_gate: 429 backoff %.0fs (#%d)%s — token-bucket refill",
        pen, attempt, f" [{tag}]" if tag else "",
    )
    time.sleep(pen)
    # 桶可能仍空, 拉开下次合法提交点
    fd = _acquire_lock(timeout=60.0)
    try:
        state = _load_state()
        state["last_submit_unix"] = time.time()
        _save_state(state)
    finally:
        _release_lock(fd)
    return pen


def batch_cooldown(sec: Optional[float] = None, *, tag: str = "") -> float:
    wait = float(sec if sec is not None else DEFAULT_BATCH_COOLDOWN_SEC)
    if wait <= 0:
        return 0.0
    logger.debug("wq_global_gate: batch cooldown %.0fs%s", wait, f" [{tag}]" if tag else "")
    time.sleep(wait)
    return wait


def envelope_summary() -> dict:
    return {
        "burst_capacity": BURST_CAPACITY,
        "safe_instant_concurrent": SAFE_INSTANT_CONCURRENT,
        "min_submit_interval_sec": MIN_SUBMIT_INTERVAL_SEC,
        "default_batch_cooldown_sec": DEFAULT_BATCH_COOLDOWN_SEC,
        "refill_hint_sec": REFILL_HINT_SEC,
        "max_inflight": MAX_INFLIGHT,
        "note": "machine-wide shared gate; 429 backoff propagates globally across all clients",
        "state_path": _STATE_PATH,
    }


def _is_submit_url(url: str) -> bool:
    u = (url or "").lower()
    if "/simulations" in u:
        return True
    # /alphas/{id}/submit
    if "/alphas/" in u and u.rstrip("/").endswith("/submit"):
        return True
    return False


_PATCHED = False


def patch_requests() -> bool:
    """monkey-patch requests.Session.request: 对 POST …/simulations 与 …/submit 自动走闸门.

    返回是否成功打补丁. 幂等.
    """
    global _PATCHED
    if _PATCHED:
        return True
    try:
        import requests
    except Exception as e:
        logger.warning("wq_global_gate: requests not available, skip patch: %s", e)
        return False

    orig_request = requests.Session.request

    @functools.wraps(orig_request)
    def _gated_request(self, method, url, *args, **kwargs):
        global _inflight
        if str(method).upper() == "POST" and _is_submit_url(url):
            with _inflight_cv:
                while _inflight >= MAX_INFLIGHT:
                    _inflight_cv.wait(timeout=5.0)
                _inflight += 1
            try:
                wait_submit_slot(tag="monkey")
                resp = orig_request(self, method, url, *args, **kwargs)
                if getattr(resp, "status_code", None) == 429:
                    note_429(resp, tag="monkey")
                return resp
            finally:
                with _inflight_cv:
                    _inflight -= 1
                    _inflight_cv.notify_all()
        return orig_request(self, method, url, *args, **kwargs)

    requests.Session.request = _gated_request
    _PATCHED = True
    logger.info("wq_global_gate: requests.Session.request patched (submit gate active)")
    return True


__all__ = [
    "MIN_SUBMIT_INTERVAL_SEC",
    "DEFAULT_BATCH_COOLDOWN_SEC",
    "REFILL_HINT_SEC",
    "MAX_429_BACKOFF_SEC",
    "MAX_INFLIGHT",
    "wait_submit_slot",
    "note_429",
    "backoff_429",
    "batch_cooldown",
    "envelope_summary",
    "patch_requests",
    "BURST_CAPACITY",
    "SAFE_INSTANT_CONCURRENT",
]
