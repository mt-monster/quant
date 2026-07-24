from wd_lib.client import WorldQuantClient

c = WorldQuantClient()
c.login()
r = c.session.get(
    "https://api.worldquantbrain.com/data-fields",
    params={
        "instrumentType": "EQUITY",
        "region": "USA",
        "delay": 1,
        "universe": "TOP3000",
        "dataset.id": "forward_beta_risk",
        "type": "MATRIX",
        "limit": 50,
    },
)
js = r.json()
print("count", js.get("count"))
for f in js.get("results") or []:
    print(
        f"{f.get('id'):45s} alpha={f.get('alphaCount')} "
        f"cov={f.get('coverage')} | {(f.get('description') or '')[:50]}"
    )
