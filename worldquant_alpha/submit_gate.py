#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v53 提交闸门 — 委托到机器级 wq_global_gate.

本文件仅为兼容层: multi_sim / scan_v53 仍 `from submit_gate import ...`,
实际逻辑全部走机器级共享闸门 wq_global_gate, 使 v53 与 fw (及未来脚本)
共享同一把锁 + 同一全局退避状态.

加载顺序 (保证可复现):
  1. 优先加载机器级副本 C:\Users\MENGTAO\.wq_submit_gate\wq_global_gate.py,
     锁/状态与其它客户端共享 -> 429 退避跨进程/跨客户端传播.
  2. 机器级副本缺失时 (如新机器/CI), 回退到仓库内受版本控制的
     wd_lib.gate.wq_global_gate, 并把 WQ_GATE_DIR 固定到机器级目录,
     使锁/状态仍落在机器级固定位置 (若该目录可创建).
  3. 两者都不可用时抛出带明确指引的 ImportError, fail fast.

v53 仍保持 BRAIN_SUBMIT_INTERVAL=32 的偏保守间隔 (向后兼容).
"""
from __future__ import annotations

import importlib
import os
import sys

_GLOBAL_DIR = r"C:\Users\MENGTAO\.wq_submit_gate"
_VENDORED_MODULE = "wd_lib.gate.wq_global_gate"


def _load_gate():
    """按加载顺序解析机器级闸门模块, 全部失败时抛出可执行指引的 ImportError."""
    machine_copy = os.path.join(_GLOBAL_DIR, "wq_global_gate.py")

    # 1. 机器级副本 (与其它客户端共享锁/状态)
    if os.path.isfile(machine_copy):
        if _GLOBAL_DIR not in sys.path:
            sys.path.insert(0, _GLOBAL_DIR)
        return importlib.import_module("wq_global_gate")

    # 2. 回退到仓库内受版本控制的副本; 状态仍固定到机器级目录
    try:
        gate = importlib.import_module(_VENDORED_MODULE)
    except Exception as exc:  # noqa: BLE001
        raise ImportError(
            "wq_global_gate 不可用: 机器级副本缺失 (" + machine_copy + "), "
            "且仓库内副本 " + _VENDORED_MODULE + " 导入失败: " + repr(exc) + ". "
            "请从 worldquant_alpha/wd_lib/gate/wq_global_gate.py 复制到 "
            + _GLOBAL_DIR + " 或修复 wd_lib 包路径."
        ) from exc

    # 仓库副本默认把锁/状态放在自身目录; 显式固定到机器级目录, 保持跨客户端共享.
    if not os.environ.get("WQ_GATE_DIR"):
        try:
            os.makedirs(_GLOBAL_DIR, exist_ok=True)
            os.environ["WQ_GATE_DIR"] = _GLOBAL_DIR
            importlib.reload(gate)
        except OSError:
            # 机器级目录不可创建 (如受限 CI): 退而使用仓库副本自带目录, 不阻塞导入.
            pass
    return gate


_g = _load_gate()

# v53 沿用更保守的 32s 间隔 (scan_v53 设了 BRAIN_SUBMIT_INTERVAL=32)
_V53_INTERVAL = float(os.environ.get("BRAIN_SUBMIT_INTERVAL", "32"))


def wait_submit_slot(*, min_interval: float = None, tag: str = "") -> float:
    return _g.wait_submit_slot(
        min_interval=min_interval if min_interval is not None else _V53_INTERVAL, tag=tag
    )


def backoff_429(attempt: int = 0, *, tag: str = "") -> float:
    return _g.backoff_429(attempt, tag=tag)


def note_429(resp=None, attempt: int = 0, *, tag: str = "") -> float:
    return _g.note_429(resp, attempt, tag=tag)


def batch_cooldown(sec=None, *, tag: str = "") -> float:
    return _g.batch_cooldown(sec, tag=tag)


def envelope_summary() -> dict:
    return _g.envelope_summary()


DEFAULT_BATCH_COOLDOWN_SEC = _g.DEFAULT_BATCH_COOLDOWN_SEC
MIN_SUBMIT_INTERVAL_SEC = _V53_INTERVAL
BURST_CAPACITY = _g.BURST_CAPACITY
SAFE_INSTANT_CONCURRENT = _g.SAFE_INSTANT_CONCURRENT

__all__ = [
    "DEFAULT_BATCH_COOLDOWN_SEC",
    "MIN_SUBMIT_INTERVAL_SEC",
    "BURST_CAPACITY",
    "SAFE_INSTANT_CONCURRENT",
    "wait_submit_slot",
    "backoff_429",
    "note_429",
    "batch_cooldown",
    "envelope_summary",
]
