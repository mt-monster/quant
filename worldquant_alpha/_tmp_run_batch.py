import json
import sys
import time

from wd_lib.client import WorldQuantClient

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
exprs = cfg["exprs"]
settings = cfg["settings"]

c = WorldQuantClient()
c.login()
print("auth", c.session.get("https://api.worldquantbrain.com/users/self").status_code, flush=True)

payload = [{"type": "REGULAR", "settings": settings, "regular": e} for e in exprs]


def post():
    return c.session.post("https://api.worldquantbrain.com/simulations", json=payload)


loc = None
for attempt in range(10):
    r = post()
    code = r.status_code
    loc = r.headers.get("Location")
    print("post", attempt, code, "loc", loc, "ra", r.headers.get("Retry-After"), (r.text or "")[:100], flush=True)
    if code in (200, 201) and loc:
        break
    if code == 401:
        c.login()
        continue
    wait = float(r.headers.get("Retry-After") or (40 + 20 * attempt))
    time.sleep(min(wait, 120))
else:
    raise SystemExit("failed to create multi after retries")

js = None
for _ in range(200):
    g = c.session.get(loc)
    if g.headers.get("Retry-After"):
        time.sleep(float(g.headers["Retry-After"]) + 0.5)
        continue
    js = g.json()
    if js.get("status") in ("COMPLETE", "ERROR", "FAIL", "WARNING", None):
        break
    if js.get("children"):
        break
    time.sleep(3)
print("multi", js.get("status"), flush=True)

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
        print("FAIL", kd.get("status"), kd.get("message"), flush=True)
        continue
    ad = c.session.get(f"https://api.worldquantbrain.com/alphas/{aid}").json()
    is_ = ad.get("is") or {}
    checks = {ch.get("name"): ch for ch in (is_.get("checks") or [])}
    y2 = (checks.get("LOW_2Y_SHARPE") or {}).get("value")
    code = (ad.get("regular") or {}).get("code", "")
    print(
        f"{aid}\tS={is_.get('sharpe')}\tF={is_.get('fitness')}\t"
        f"T={is_.get('turnover')}\t2Y={y2}\t{code}",
        flush=True,
    )
