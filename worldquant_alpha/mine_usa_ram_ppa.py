#!/usr/bin/env python3
"""
EUR / delay=1 / neutralization=REVERSION_AND_MOMENTUM (RAM) PPA Alpha mining.
"""
from __future__ import annotations
import argparse, hashlib, json, logging, os, random, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import combinations
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from wd_lib_wrapper import get_api
    from database import save_alpha, alpha_exists
except ImportError:
    from worldquant_alpha.wd_lib_wrapper import get_api
    from worldquant_alpha.database import save_alpha, alpha_exists

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SEARCH_SCOPE = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "delay": 1,
    "universe": "TOP3000",
}

DEFAULT_RAM_FIELD = os.environ.get("WQ_RAM_NEUTRAL_FIELD", "sta1_top3000c50")

BACKTEST_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 4,
    "neutralization": "NONE",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P0Y",
}

MAX_PROD_CORR = 0.7
TARGET_COUNT = 2
_PROD_CORR_NAMES = (
    "PRODUCTION_CORRELATION",
    "PROD_CORRELATION",
    "MAX_PRODUCTION_CORRELATION",
    "PRODUCTION_CORR",
)


def _unwrap_session(api) -> Any:
    return api.session


def field_wrap(f: str) -> str:
    return f"ts_backfill({f}, 5)"


def apply_ram_neutralization(expr: str, ram_field: str = DEFAULT_RAM_FIELD) -> str:
    if "group_neutralize(" in expr:
        return expr
    return f"group_neutralize({expr}, {ram_field})"


def build_two_field_expressions(f1: str, f2: str) -> List[str]:
    a, b = field_wrap(f1), field_wrap(f2)
    out = [
        f"rank(subtract({a}, {b}))",
        f"zscore(subtract({a}, {b}))",
        f"rank(divide({a}, abs({b}) + 0.01))",
    ]
    return out


def parse_production_correlation(check_payload: Dict[str, Any]) -> Optional[float]:
    if not check_payload:
        return None
    checks = (check_payload.get("is") or {}).get("checks") or []
    for c in checks:
        name = (c.get("name") or "").upper()
        if any(k in name for k in _PROD_CORR_NAMES):
            v = c.get("value")
            if v is None:
                return None
            try:
                return abs(float(v))
            except (TypeError, ValueError):
                return None
    for c in checks:
        if "PRODUCTION" in (c.get("name") or "").upper():
            v = c.get("value")
            if v is not None:
                try:
                    return abs(float(v))
                except (TypeError, ValueError):
                    pass
    return None


def wait_for_production_correlation(
    api, platform_alpha_id: str, max_wait_s: int = 1800, poll_s: int = 25
) -> Optional[float]:
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        ch = api.get_alpha_check(platform_alpha_id)
        corr = parse_production_correlation(ch)
        if corr is not None:
            return corr
        logger.info(
            "Production correlation not ready, %ss retry... (%s)",
            poll_s,
            platform_alpha_id,
        )
        time.sleep(poll_s)
    return None


def passes_submission_shape(
    api, platform_alpha_id: str, min_sharpe: float, min_fitness: float
) -> Tuple[bool, float, float]:
    det = api.get_alpha_details(platform_alpha_id)
    is_ = det.get("is") or {}
    try:
        sharpe = float(is_.get("sharpe") or 0)
        fitness = float(is_.get("fitness") or 0)
    except (TypeError, ValueError):
        return False, 0.0, 0.0
    if sharpe < min_sharpe or fitness < min_fitness:
        return False, sharpe, fitness
    return True, sharpe, fitness


def fetch_matrix_fields(api, dataset_id: str, limit: int = 50) -> List[str]:
    from wd_lib.api.datasets import get_datafields
    df = get_datafields(
        search_scope=SEARCH_SCOPE,
        dataset_id=dataset_id,
        field_type="MATRIX",
        session=_unwrap_session(api),
    )
    if df is None or df.empty:
        return []
    ids = df[df["type"] == "MATRIX"]["id"].tolist()
    return ids[:limit]


_found_lock = Lock()


def backtest_one(api, expr, dataset_id, sn, min_sharpe, min_fitness, prod_corr_wait):
    ram_expr = apply_ram_neutralization(expr)
    logger.info("SIM #%d [%s] %s...", sn, dataset_id, ram_expr[:80])
    try:
        res = api.run_backtest(ram_expr, settings=BACKTEST_SETTINGS.copy())
    except Exception as e:
        logger.warning("bt err: %s", e)
        return None
    if not res:
        return None
    pid = res.get("platform_id")
    if not pid:
        return None
    ok, sharpe, fitness = passes_submission_shape(api, pid, min_sharpe, min_fitness)
    if not ok:
        logger.info("IS fail S=%.3f F=%.3f", sharpe, fitness)
        return None
    logger.info("IS ok S=%.3f F=%.3f, waiting prod corr...", sharpe, fitness)
    pc = wait_for_production_correlation(api, pid, max_wait_s=prod_corr_wait)
    if pc is None:
        logger.warning("no prod corr for %s", pid)
        return None
    if pc > MAX_PROD_CORR:
        logger.info("prod corr %.4f > %.2f, skip", pc, MAX_PROD_CORR)
        return None
    rec = {
        "platform_alpha_id": pid,
        "dataset_id": dataset_id,
        "expression": expr,
        "sharpe": sharpe,
        "fitness": fitness,
        "production_correlation": pc,
        "found_at": datetime.now().isoformat(),
        "simulation_number": sn,
    }
    return rec


def mine_dataset(api, dataset_id, fields, max_pairs=20, max_workers=4, min_sharpe=1.58, min_fitness=1.0, prod_corr_wait=1800):
    rng = random.Random(42)
    found = []
    tried = set()
    total_sim = 0
    pairs = list(combinations(fields, 2))
    rng.shuffle(pairs)
    exprs = []
    for f1, f2 in pairs[:max_pairs]:
        for e in build_two_field_expressions(f1, f2):
            if e not in tried:
                tried.add(e)
                exprs.append((e, f1, f2))
    rng.shuffle(exprs)
    logger.info("dataset %s: %d expressions from %d pairs", dataset_id, len(exprs), min(max_pairs, len(pairs)))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="W") as ex:
        futs = {}
        for e, f1, f2 in exprs:
            with _found_lock:
                if len(found) >= TARGET_COUNT:
                    break
                total_sim += 1
                sn = total_sim
            futs[ex.submit(backtest_one, api, e, dataset_id, sn, min_sharpe, min_fitness, prod_corr_wait)] = (e, f1, f2)
        for fut in as_completed(futs):
            try:
                rec = fut.result()
            except Exception as e:
                logger.warning("future err: %s", e)
                continue
            if rec:
                with _found_lock:
                    found.append(rec)
                    logger.info(
                        "HIT #%d/%d id=%s corr=%.4f S=%.3f F=%.3f",
                        len(found),
                        TARGET_COUNT,
                        rec["platform_alpha_id"],
                        rec["production_correlation"],
                        rec["sharpe"],
                        rec["fitness"],
                    )
                try:
                    save_alpha(
                        rec["expression"],
                        f"USA_RAM_PPA_{dataset_id}",
                        {
                            **BACKTEST_SETTINGS,
                            "dataset_id": dataset_id,
                        },
                    )
                except Exception as ex:
                    logger.warning("save db err: %s", ex)
            with _found_lock:
                if len(found) >= TARGET_COUNT:
                    for fc in futs:
                        fc.cancel()
                    break
    return found, total_sim


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="risk62", help="dataset id")
    parser.add_argument("--fields-file", type=str, default=None, help="json file with fields list")
    parser.add_argument("--max-pairs", type=int, default=20, help="max field pairs")
    parser.add_argument("--max-workers", type=int, default=4, help="concurrent workers")
    parser.add_argument("--min-sharpe", type=float, default=1.58, help="IS Sharpe threshold")
    parser.add_argument("--min-fitness", type=float, default=1.0, help="IS Fitness threshold")
    parser.add_argument("--prod-corr-wait", type=int, default=1800, help="max wait for prod corr")
    args = parser.parse_args()

    logger.info("=" * 72)
    logger.info("USA D1 RAM PPA mining | dataset=%s | target=%d", args.dataset, TARGET_COUNT)
    logger.info("=" * 72)

    api = get_api()
    if args.fields_file:
        with open(args.fields_file, "r") as f:
            fields = json.load(f)
    else:
        fields = fetch_matrix_fields(api, args.dataset, limit=50)
    if len(fields) < 2:
        logger.error("fields < 2, abort")
        return
    logger.info("dataset %s has %d fields", args.dataset, len(fields))

    found, total_sim = mine_dataset(
        api,
        args.dataset,
        fields,
        max_pairs=args.max_pairs,
        max_workers=args.max_workers,
        min_sharpe=args.min_sharpe,
        min_fitness=args.min_fitness,
        prod_corr_wait=args.prod_corr_wait,
    )

    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)
    p = os.path.join(
        rdir,
        f"eur_ram_ppa_{args.dataset}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(p, "w", encoding="utf-8") as fout:
        json.dump(
            {
                "target": TARGET_COUNT,
                "found": len(found),
                "max_prod_corr": MAX_PROD_CORR,
                "dataset_id": args.dataset,
                "total_simulations": total_sim,
                "alphas": found,
            },
            fout,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("saved to %s", os.path.abspath(p))
    for i, a in enumerate(found, 1):
        logger.info(
            "  Alpha #%d: %s S=%.3f F=%.3f PC=%.4f",
            i,
            a["platform_alpha_id"],
            a["sharpe"],
            a["fitness"],
            a["production_correlation"],
        )


if __name__ == "__main__":
    main()
