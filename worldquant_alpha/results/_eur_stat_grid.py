"""STAT grid for EUR search_interest — boost Fitness/SUB/ROBUST while keeping 2Y."""
import json
import time
from wd_lib.client import WorldQuantClient

EXPRS = [
    "signed_power(group_rank(ts_rank(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 126), industry), 3.0)",
    "signed_power(group_rank(ts_rank(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 126), industry), 2.5)",
    "signed_power(group_rank(ts_decay_linear(ts_rank(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 126), 5), industry), 3.0)",
    "signed_power(group_rank(ts_rank(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 150), industry), 3.0)",
    "signed_power(group_rank(ts_zscore(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 126), industry), 3.0)",
    "ts_decay_linear(signed_power(group_rank(ts_rank(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 126), industry), 3.0), 5)",
    "signed_power(group_rank(ts_rank(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 126), country), 3.0)",
    "signed_power(group_rank(ts_rank(divide(ts_backfill(vec_avg(relative_interest_score_7), 22), ts_backfill(vec_avg(trend_estimation_confidence_score_4), 22)), 126), subindustry), 3.0)",
]

SETTINGS_LIST = [
    {"decay": 16, "truncation": 0.05, "neutralization": "STATISTICAL"},
    {"decay": 20, "truncation": 0.05, "neutralization": "STATISTICAL"},
    {"decay": 24, "truncation": 0.08, "neutralization": "STATISTICAL"},
    {"decay": 16, "truncation": 0.05, "neutralization": "SLOW"},
    {"decay": 16, "truncation": 0.05, "neutralization": "FAST"},
    {"decay": 16, "truncation": 0.05, "neutralization": "COUNTRY"},
    {"decay": 16, "truncation": 0.05, "neutralization": "SLOW_AND_FAST"},
    {"decay": 16, "truncation": 0.05, "neutralization": "REVERSION_AND_MOMENTUM"},
]


def submit_multi(session, expressions, settings):
    payload = {
        "type": "MULTI",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "EUR",
            "universe": "TOPCS1600",
            "delay": 1,
            "decay": settings["decay"],
            "neutralization": settings["neutralization"],
            "truncation": settings["truncation"],
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "ON",
            "maxTrade": "OFF",
            "language": "FASTEXPR",
            "visualization": False,
        },
        # BRAIN multi uses children simulations
    }
    # Prefer batch of regular simulations via /simulations with list
    children = []
    for expr in expressions:
        children.append(
            {
                "type": "REGULAR",
                "settings": payload["settings"],
                "regular": expr,
            }
        )
    # Try multi endpoint
    r = session.post(
        "https://api.worldquantbrain.com/simulations",
        json={
            "type": "MULTI",
            "settings": payload["settings"],
            "children": [{"type": "REGULAR", "regular": e} for e in expressions]
            if False
            else None,
        },
    )
    # Fallback: use documented multi format from MCP — create one by one if needed
    return r


def create_regular(session, expr, settings):
    body = {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "EUR",
            "universe": "TOPCS1600",
            "delay": 1,
            "decay": settings["decay"],
            "neutralization": settings["neutralization"],
            "truncation": settings["truncation"],
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "ON",
            "maxTrade": "OFF",
            "language": "FASTEXPR",
            "visualization": False,
        },
        "regular": expr,
    }
    r = session.post("https://api.worldquantbrain.com/simulations", json=body)
    return r


def wait_sim(session, loc, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = session.get(loc)
        ra = r.headers.get("Retry-After")
        if r.status_code == 200 and r.text:
            j = r.json()
            if j.get("status") in ("COMPLETE", "WARNING", "ERROR") or j.get("alpha"):
                return j
        time.sleep(float(ra) if ra else 3)
    return None


def summarize(alpha):
    iso = alpha.get("is") or {}
    checks = {c["name"]: c for c in iso.get("checks", [])}

    def gv(n):
        c = checks.get(n, {})
        return c.get("result"), c.get("value"), c.get("limit")

    return {
        "id": alpha.get("id"),
        "S": iso.get("sharpe"),
        "F": iso.get("fitness"),
        "TVR": iso.get("turnover"),
        "Ret": iso.get("returns"),
        "SUB": gv("LOW_SUB_UNIVERSE_SHARPE"),
        "ROB": gv("LOW_ROBUST_UNIVERSE_SHARPE"),
        "2Y": gv("LOW_2Y_SHARPE"),
        "code": (alpha.get("regular") or {}).get("code"),
        "neut": (alpha.get("settings") or {}).get("neutralization"),
        "decay": (alpha.get("settings") or {}).get("decay"),
        "trunc": (alpha.get("settings") or {}).get("truncation"),
    }


def main():
    c = WorldQuantClient()
    assert c.login()
    results = []
    # Batch 1: same base expr across settings
    base = EXPRS[0]
    for st in SETTINGS_LIST:
        print("SIM", st)
        r = create_regular(c.session, base, st)
        if r.status_code not in (200, 201, 202):
            print(" fail create", r.status_code, r.text[:200])
            time.sleep(5)
            continue
        loc = r.headers.get("Location")
        if not loc:
            print(" no location", r.status_code, r.text[:200])
            continue
        if loc.startswith("/"):
            loc = "https://api.worldquantbrain.com" + loc
        sim = wait_sim(c.session, loc)
        if not sim:
            print(" timeout")
            continue
        aid = sim.get("alpha")
        if not aid:
            print(" no alpha", sim.get("status"), str(sim)[:200])
            continue
        det = c.session.get(f"https://api.worldquantbrain.com/alphas/{aid}").json()
        s = summarize(det)
        results.append(s)
        print(
            s["id"],
            s["neut"],
            "d",
            s["decay"],
            "S",
            s["S"],
            "F",
            s["F"],
            "SUB",
            s["SUB"],
            "ROB",
            s["ROB"],
            "2Y",
            s["2Y"],
        )
        time.sleep(2)

    # Batch 2: expression variants with best-looking setting STAT decay20 trunc0.05
    st = {"decay": 20, "truncation": 0.05, "neutralization": "STATISTICAL"}
    for expr in EXPRS[1:]:
        print("SIM expr", expr[:60])
        r = create_regular(c.session, expr, st)
        if r.status_code not in (200, 201, 202):
            print(" fail", r.status_code, r.text[:200])
            time.sleep(8)
            continue
        loc = r.headers.get("Location")
        if loc.startswith("/"):
            loc = "https://api.worldquantbrain.com" + loc
        sim = wait_sim(c.session, loc)
        aid = (sim or {}).get("alpha")
        if not aid:
            print(" no alpha", sim)
            continue
        det = c.session.get(f"https://api.worldquantbrain.com/alphas/{aid}").json()
        s = summarize(det)
        results.append(s)
        print(s["id"], "S", s["S"], "F", s["F"], "SUB", s["SUB"], "ROB", s["ROB"], "2Y", s["2Y"])
        time.sleep(2)

    out = "results/_eur_stat_grid_out.json"
    json.dump(results, open(out, "w", encoding="utf-8"), indent=2)
    print("Wrote", out, "n=", len(results))
    # rank by how close to passing
    for s in results:
        ok = 0
        if (s["S"] or 0) >= 1.58:
            ok += 1
        if (s["F"] or 0) >= 1.0:
            ok += 1
        if s["SUB"][0] == "PASS":
            ok += 1
        if s["ROB"][0] == "PASS":
            ok += 1
        y = s["2Y"][1]
        if y is not None and y >= 1.58:
            ok += 1
        elif y is not None and y >= 1.4:
            ok += 0.5
        s["_score"] = ok
    results.sort(key=lambda x: x.get("_score", 0), reverse=True)
    print("\nTOP:")
    for s in results[:8]:
        print(s["_score"], s["id"], s["neut"], s["decay"], s["S"], s["F"], s["SUB"], s["ROB"], s["2Y"])


if __name__ == "__main__":
    main()
