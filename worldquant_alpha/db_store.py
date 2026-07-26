"""Local MySQL store for fleet scan backtest results (soft-fail, dual-write with JSON)."""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_CURRENT_DIR, ".env"))

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "worldquant_alpha")

Base = declarative_base()

_engine = None
_SessionLocal = None
_engine_ok = False
_last_fail_ts = 0.0
_last_warn_ts = 0.0
_RETRY_SEC = 30.0
_WARN_EVERY_SEC = 60.0


class ScanBacktestResult(Base):
    __tablename__ = "scan_backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), nullable=False)
    dataset = Column(String(100), nullable=True)
    label = Column(String(255), nullable=False)
    pid = Column(String(100), nullable=True)
    status = Column(String(40), nullable=True)
    track = Column(String(40), nullable=True)
    sharpe = Column(Float, nullable=True)
    fitness = Column(Float, nullable=True)
    tvr = Column(Float, nullable=True)
    margin = Column(Float, nullable=True)
    fails = Column(JSON, nullable=True)
    expr = Column(Text, nullable=True)
    settings = Column(JSON, nullable=True)
    style = Column(String(100), nullable=True)
    field = Column(String(200), nullable=True)
    expr_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("job_id", "label", name="uq_scan_bt_job_label"),
        Index("idx_scan_bt_pid", "pid"),
        Index("idx_scan_bt_expr_hash", "expr_hash"),
        Index("idx_scan_bt_dataset", "dataset"),
    )


class ScanFoundAlpha(Base):
    __tablename__ = "scan_found_alphas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), nullable=True)
    dataset = Column(String(100), nullable=True)
    style = Column(String(100), nullable=True)
    track = Column(String(40), nullable=True)
    pid = Column(String(100), nullable=False)
    label = Column(String(255), nullable=True)
    expr = Column(Text, nullable=True)
    settings = Column(JSON, nullable=True)
    sharpe = Column(Float, nullable=True)
    fitness = Column(Float, nullable=True)
    tvr = Column(Float, nullable=True)
    margin = Column(Float, nullable=True)
    margin_bp = Column(Float, nullable=True)
    prod_corr = Column(Float, nullable=True)
    pair_corr_vs = Column(JSON, nullable=True)
    risk_neut = Column(JSON, nullable=True)
    robust = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    submitted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("pid", name="uq_scan_found_pid"),
        Index("idx_scan_found_job", "job_id"),
        Index("idx_scan_found_dataset", "dataset"),
    )


def expr_hash(expr: Optional[str]) -> Optional[str]:
    if not expr:
        return None
    return hashlib.sha256(str(expr).encode("utf-8")).hexdigest()


def _database_url() -> str:
    return f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def _warn_throttled(msg: str, *args: Any) -> None:
    global _last_warn_ts
    now = time.time()
    if now - _last_warn_ts >= _WARN_EVERY_SEC:
        _last_warn_ts = now
        logger.warning(msg, *args)


def _ensure_engine() -> bool:
    global _engine, _SessionLocal, _engine_ok, _last_fail_ts
    if _engine_ok and _engine is not None:
        return True
    now = time.time()
    if _last_fail_ts and (now - _last_fail_ts) < _RETRY_SEC:
        return False
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
        _engine = None
        _SessionLocal = None
    try:
        _engine = create_engine(
            _database_url(),
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
        )
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _SessionLocal = sessionmaker(bind=_engine)
        _engine_ok = True
        _last_fail_ts = 0.0
        return True
    except Exception as e:
        _warn_throttled("db_store: MySQL engine unavailable: %s", e)
        _engine = None
        _SessionLocal = None
        _engine_ok = False
        _last_fail_ts = now
        return False


def init_db() -> bool:
    """Create tables. Returns True on success."""
    reset_engine()
    if not _ensure_engine():
        return False
    try:
        Base.metadata.create_all(_engine)
        logger.info("db_store: tables ready on %s/%s", DB_HOST, DB_NAME)
        return True
    except Exception as e:
        logger.warning("db_store: init_db failed: %s", e)
        return False


def reset_engine() -> None:
    """Force re-connect on next use (tests / credential change)."""
    global _engine, _SessionLocal, _engine_ok, _last_fail_ts, _last_warn_ts
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = None
    _SessionLocal = None
    _engine_ok = False
    _last_fail_ts = 0.0
    _last_warn_ts = 0.0


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _row_backtest(job_id: str, dataset: Optional[str], r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    label = r.get("label")
    if not label:
        return None
    now = datetime.now()
    margin = _as_float(r.get("margin"))
    return {
        "job_id": job_id,
        "dataset": dataset or r.get("dataset"),
        "label": str(label)[:255],
        "pid": r.get("pid"),
        "status": r.get("status"),
        "track": r.get("track"),
        "sharpe": _as_float(r.get("sharpe")),
        "fitness": _as_float(r.get("fitness")),
        "tvr": _as_float(r.get("tvr")),
        "margin": margin,
        "fails": r.get("fails"),
        "expr": r.get("expr"),
        "settings": r.get("settings"),
        "style": r.get("style"),
        "field": (str(r["field"])[:200] if r.get("field") is not None else None),
        "expr_hash": expr_hash(r.get("expr")),
        "created_at": now,
        "updated_at": now,
    }


def _row_found(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pid = r.get("pid")
    if not pid:
        return None
    margin = _as_float(r.get("margin"))
    margin_bp = _as_float(r.get("margin_bp"))
    if margin_bp is None and margin is not None:
        margin_bp = margin * 10000.0
    now = datetime.now()
    return {
        "job_id": r.get("job") or r.get("job_id"),
        "dataset": r.get("dataset"),
        "style": r.get("style"),
        "track": r.get("track"),
        "pid": str(pid)[:100],
        "label": (str(r["label"])[:255] if r.get("label") is not None else None),
        "expr": r.get("expr"),
        "settings": r.get("settings"),
        "sharpe": _as_float(r.get("sharpe")),
        "fitness": _as_float(r.get("fitness")),
        "tvr": _as_float(r.get("tvr")),
        "margin": margin,
        "margin_bp": margin_bp,
        "prod_corr": _as_float(r.get("prod_corr")),
        "pair_corr_vs": r.get("pair_corr_vs"),
        "risk_neut": r.get("risk_neut"),
        "robust": r.get("robust"),
        "tags": r.get("tags"),
        "submitted": bool(r.get("submitted", False)),
        "created_at": now,
        "updated_at": now,
    }


def upsert_backtest_results(
    job_id: str,
    dataset: Optional[str],
    rows: Iterable[Dict[str, Any]],
) -> int:
    """Upsert full scan results by (job_id, label). Soft-fail → 0."""
    try:
        if not _ensure_engine():
            return 0
        payloads: List[Dict[str, Any]] = []
        for r in rows or []:
            row = _row_backtest(job_id, dataset, r)
            if row:
                payloads.append(row)
        if not payloads:
            return 0

        # Batch upserts to avoid huge packets
        written = 0
        session = _SessionLocal()
        try:
            for i in range(0, len(payloads), 200):
                chunk = payloads[i : i + 200]
                for row in chunk:
                    stmt = mysql_insert(ScanBacktestResult).values(**row)
                    update_cols = {
                        c: stmt.inserted[c]
                        for c in row
                        if c not in ("job_id", "label")
                    }
                    # Preserve created_at on conflict
                    update_cols.pop("created_at", None)
                    stmt = stmt.on_duplicate_key_update(**update_cols)
                    session.execute(stmt)
                    written += 1
                session.commit()
            return written
        except Exception as e:
            session.rollback()
            logger.warning("db_store: upsert_backtest_results failed: %s", e)
            return 0
        finally:
            session.close()
    except Exception as e:
        logger.warning("db_store: upsert_backtest_results error: %s", e)
        return 0


def upsert_found_alphas(rows: Iterable[Dict[str, Any]]) -> int:
    """Upsert found/ready alphas by pid. Soft-fail → 0."""
    try:
        if not _ensure_engine():
            return 0
        payloads: List[Dict[str, Any]] = []
        for r in rows or []:
            row = _row_found(r)
            if row:
                payloads.append(row)
        if not payloads:
            return 0

        written = 0
        session = _SessionLocal()
        try:
            for i in range(0, len(payloads), 100):
                chunk = payloads[i : i + 100]
                for row in chunk:
                    stmt = mysql_insert(ScanFoundAlpha).values(**row)
                    update_cols = {c: stmt.inserted[c] for c in row if c != "pid"}
                    update_cols.pop("created_at", None)
                    stmt = stmt.on_duplicate_key_update(**update_cols)
                    session.execute(stmt)
                    written += 1
                session.commit()
            return written
        except Exception as e:
            session.rollback()
            logger.warning("db_store: upsert_found_alphas failed: %s", e)
            return 0
        finally:
            session.close()
    except Exception as e:
        logger.warning("db_store: upsert_found_alphas error: %s", e)
        return 0


def sync_checkpoint_to_db(
    job_id: str,
    dataset: Optional[str],
    ckpt_results: Iterable[Dict[str, Any]],
    found_alphas: Iterable[Dict[str, Any]],
) -> None:
    """Convenience: dual-write both layers; never raises."""
    try:
        n1 = upsert_backtest_results(job_id, dataset, ckpt_results)
        n2 = upsert_found_alphas(found_alphas)
        if n1 or n2:
            logger.debug("db_store: synced job=%s results=%d found=%d", job_id, n1, n2)
    except Exception as e:
        logger.warning("db_store: sync_checkpoint_to_db error: %s", e)


def main(argv: Optional[List[str]] = None) -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            if hasattr(_s, "reconfigure"):
                _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = argv if argv is not None else sys.argv[1:]
    cmd = (args[0] if args else "init").lower()
    if cmd == "init":
        ok = init_db()
        print("init_db:", "OK" if ok else "FAILED")
        return 0 if ok else 1
    print("Usage: python db_store.py init")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
