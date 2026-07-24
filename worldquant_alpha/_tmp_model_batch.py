import time
from wd_lib.client import WorldQuantClient

c = WorldQuantClient()
c.login()
print("auth", c.session.get("https://api.worldquantbrain.com/users/self").status_code)

exprs = [
    "group_rank(ts_zscore(ts_backfill(vec_avg(visual_price_path_shape_score), 120), 252), industry)",
    "group_rank(ts_zscore(ts_backfill(vec_avg(visual_price_path_shape_score), 120), 63), industry)",
    "group_rank(ts_rank(ts_backfill(vec_avg(visual_price_path_shape_score), 120), 252), industry)",
    "signed_power(group_rank(ts_zscore(ts_backfill(vec_avg(visual_price_path_shape_score), 120), 252), industry), 0.3)",
    "group_rank(ts_zscore(ts_backfill(vec_avg(earnings_financial_event_score_2), 120), 252), industry)",
    "group_rank(-ts_zscore(ts_backfill(vec_avg(earnings_financial_event_score_2), 120), 252), industry)",
    "group_rank(ts_zscore(ts_backfill(vec_avg(corporate_structure_event_score_2), 120), 252), industry)",
    "group_rank(ts_zscore(ts_backfill(vec_avg(earnings_financial_event_score), 120), 252), industry)",
]
settings = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 40,
    "neutralization": "FAST",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "maxTrade": "OFF",
}
payload = [{"type": "REGULAR", "settings": settings, "regular": e} for e in exprs]


def post():
    return c.session.post("https://api.worldquantbrain.com/simulations", json=payload)


for attempt in range(6):
    r = post()
    print("post", attempt, r.status_code, r.headers.get("Location"), r.headers.get("Retry-After"), (r.text or "")[:120])
    if r.status_code in (200, 201) and r.headers.get("Location"):
        break
    if r.status_code == 401:
        c.login()
        continue
    wait = float(r.headers.get("Retry-After") or (45 * (attempt + 1)))
    time.sleep(min(wait, 120))
else:
    raise SystemExit("failed to create multi")

loc = r.headers.get("Location")
js = None
for _ in range(150):
    g = c.session.get(loc)
    if g.headers.get("Retry-After"):
        time.sleep(float(g.headers["Retry-After"]) + 0.5)
        continue
    js = g.json()
    print("multi", js.get("status"))
    break

for kid in js.get("children") or []:
    url = kid if str(kid).startswith("http") else f"https://api.worldquantbrain.com{kid}"
    while True:
        kg = c.session.get(url)
        if kg.headers.get("Retry-After"):
            time.sleep(float(kg.headers["Retry-After"]) + 0.3)
            continue
        break
    kd = kg.json()
    aid = kd.get("alpha")
    if not aid:
        print("FAIL", kd.get("status"), kd.get("message"))
        continue
    ad = c.session.get(f"https://api.worldquantbrain.com/alphas/{aid}").json()
    is_ = ad.get("is") or {}
    code = (ad.get("regular") or {}).get("code", "")
    print(f"{aid}\tS={is_.get('sharpe')}\tF={is_.get('fitness')}\tT={is_.get('turnover')}\t{code}")
