# -*- coding: utf-8 -*-
"""wd_lib.gate — 仓库内托管的机器级提交闸门代码.

`wq_global_gate.py` 是 C:\\Users\\<user>\\.wq_submit_gate\\wq_global_gate.py 的
受版本控制副本 (vendored copy), 二者应保持字节一致.

运行时仍优先使用机器级目录里的副本 (锁/状态文件与其它项目共享);
本目录只保证代码可审查、可恢复: 新机器缺少机器级副本时,
submit_gate.py 会回退到这里, 并通过 WQ_GATE_DIR 把状态固定在机器级目录.

同步约定: 修改闸门逻辑时先改这里, 再复制到机器级目录 (或反向), 保持哈希一致.
"""
