#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可配置的实时进度日志模块 (JSON Lines 格式)"""
import os, json, time, logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

class ProgressLogger:
    def __init__(self, total_steps, log_path="progress.log", task_name="task", emit_interval_sec=10.0, max_recent=5):
        self.total_steps = int(total_steps)
        self.log_path = Path(log_path)
        self.task_name = task_name
        self.emit_interval_sec = float(emit_interval_sec)
        self.max_recent = max_recent
        self.done = 0
        self.start_ts = None
        self.last_emit_ts = 0.0
        self.recent = []
        self._ensure_dir()

    def _ensure_dir(self):
        if self.log_path.parent:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _now_iso(self):
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    def _write(self, record):
        line = json.dumps(record, ensure_ascii=False, default=str)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n"); f.flush(); os.fsync(f.fileno())
        except Exception as e:
            logging.getLogger("ProgressLogger").warning("写入进度日志失败 %s: %s", self.log_path, e)

    def start(self, meta=None):
        self.start_ts = time.time()
        self.last_emit_ts = self.start_ts
        record = {"ts": self._now_iso(), "event": "start", "task": self.task_name, "total_steps": self.total_steps, "pid": os.getpid()}
        if meta: record["meta"] = meta
        self._write(record)

    def _compute_eta(self):
        if self.done <= 0 or self.start_ts is None: return None
        elapsed = time.time() - self.start_ts
        avg = elapsed / self.done
        return (self.total_steps - self.done) * avg

    def _should_emit(self):
        return time.time() - self.last_emit_ts >= self.emit_interval_sec

    def step(self, done=1, extra=None, force_emit=False):
        self.done += int(done)
        if self.done > self.total_steps: self.done = self.total_steps
        if extra:
            entry = {"ts": self._now_iso(), "step": self.done}
            entry.update(extra)
            self.recent.append(entry)
            if len(self.recent) > self.max_recent: self.recent.pop(0)
        if force_emit or self._should_emit() or self.done >= self.total_steps:
            self._emit()

    def _emit(self):
        if self.start_ts is None: return
        now = time.time()
        elapsed = now - self.start_ts
        pct = (self.done / self.total_steps * 100.0) if self.total_steps > 0 else 0.0
        avg = elapsed / self.done if self.done > 0 else 0.0
        eta_sec = self._compute_eta()
        record = {"ts": self._now_iso(), "event": "progress", "task": self.task_name, "done": self.done, "total": self.total_steps, "pct": round(pct, 2), "elapsed_sec": round(elapsed, 1), "avg_sec_per_step": round(avg, 2), "eta_sec": round(eta_sec, 1) if eta_sec is not None else None, "eta": (datetime.now() + timedelta(seconds=eta_sec)).strftime("%Y-%m-%dT%H:%M:%S") if eta_sec is not None else None, "recent": list(self.recent)}
        self._write(record)
        self.last_emit_ts = now

    def finish(self, summary=None):
        if self.start_ts is None: self.start_ts = time.time()
        self.done = self.total_steps
        self._emit()
        elapsed = time.time() - self.start_ts
        record = {"ts": self._now_iso(), "event": "finish", "task": self.task_name, "done": self.done, "total": self.total_steps, "pct": 100.0, "elapsed_sec": round(elapsed, 1), "avg_sec_per_step": round(elapsed / self.total_steps, 2) if self.total_steps > 0 else 0.0}
        if summary: record["summary"] = summary
        self._write(record)

    @staticmethod
    def tail(log_path, n=10):
        p = Path(log_path)
        if not p.exists(): return []
        lines = []
        try:
            with open(p, "r", encoding="utf-8") as f: lines = f.readlines()
        except: return []
        records = []
        for line in lines[-n:]:
            line = line.strip()
            if not line: continue
            try: records.append(json.loads(line))
            except: continue
        return records
