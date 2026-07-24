import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))
from wd_lib_wrapper import WqApiSimple, API_BASE

api = WqApiSimple()
pid = "YPgAa3WR"
r = api.session.get(f"{API_BASE}/alphas/{pid}", timeout=60)
print("STATUS", r.status_code)
if r.status_code == 200:
    d = r.json()
    # Print only the meaningful fields
    keys_of_interest = ["id", "name", "regular", "settings", "is", "type", "color", "tags", "status", "dateCreated", "dateSubmitted"]
    out = {k: d.get(k) for k in keys_of_interest if k in d}
    # expression lives inside 'regular' or 'settings'; also top-level 'expression'
    expr = d.get("expression") or (d.get("regular") or {}).get("code") or (d.get("settings") or {}).get("expression")
    print("EXPRESSION:", expr)
    print("REGULAR:", json.dumps(d.get("regular"), ensure_ascii=False)[:500])
    print(json.dumps(out, ensure_ascii=False, indent=2)[:3000])
else:
    print(r.text[:500])
