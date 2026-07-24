from wd_lib.client import WorldQuantClient

c = WorldQuantClient()
c.login()
for ds in [
    "board_network",
    "expected_move",
    "model307",
    "model144",
    "ai_factor_transfer",
]:
    r = c.session.get(
        "https://api.worldquantbrain.com/data-fields",
        params={
            "instrumentType": "EQUITY",
            "region": "USA",
            "delay": 1,
            "universe": "TOP3000",
            "dataset.id": ds,
            "limit": 15,
        },
    )
    js = r.json()
    print("===", ds, "count", js.get("count"))
    for f in js.get("results") or []:
        print(
            f"  {f.get('id'):40s} type={f.get('type')} "
            f"a={f.get('alphaCount')} cov={f.get('coverage')} "
            f"| {(f.get('description') or '')[:50]}"
        )
