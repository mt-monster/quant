import sys
import time

from wd_lib.client import WorldQuantClient

mid = sys.argv[1]
c = WorldQuantClient()
c.login()


def get(url, tries=8):
    for _ in range(tries):
        try:
            r = c.session.get(url, timeout=30)
        except Exception as e:
            print("retry", type(e).__name__, flush=True)
            time.sleep(3)
            continue
        if r.headers.get("Retry-After"):
            time.sleep(float(r.headers["Retry-After"]) + 0.3)
            continue
        return r
    return None


r = get(f"https://api.worldquantbrain.com/simulations/{mid}")
js = r.json()
print("status", js.get("status"), flush=True)
kids = js.get("children") or []
print("children", len(kids), flush=True)
for kid in kids:
    kg = get(f"https://api.worldquantbrain.com/simulations/{kid}")
    if kg is None:
        print(kid, "unreachable", flush=True)
        continue
    kd = kg.json()
    aid = kd.get("alpha")
    if not aid:
        print(kid, "FAIL", kd.get("status"), kd.get("message"), flush=True)
        continue
    ad = get(f"https://api.worldquantbrain.com/alphas/{aid}").json()
    is_ = ad.get("is") or {}
    checks = {ch.get("name"): ch for ch in (is_.get("checks") or [])}
    y2 = (checks.get("LOW_2Y_SHARPE") or {}).get("value")
    code = (ad.get("regular") or {}).get("code", "")
    print(
        f"{aid}\tS={is_.get('sharpe')}\tF={is_.get('fitness')}\t"
        f"T={is_.get('turnover')}\t2Y={y2}\t{code}",
        flush=True,
    )
