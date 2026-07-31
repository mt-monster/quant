"""scan 子包: scan_v* 家族共享的三轨 multi-sim job runner.

轻量子包 — 仅依赖仓库根目录模块 (multi_sim / progress_logger / tri_track /
wd_lib_wrapper), 不引入 wd_lib 其他重依赖 (pandas 等)。
"""
from .tri_runner import (
    ScanConfig,
    base_settings,
    make_variant_adder,
    run_tri_scan,
    variant_key,
)

__all__ = [
    "ScanConfig",
    "base_settings",
    "make_variant_adder",
    "run_tri_scan",
    "variant_key",
]
