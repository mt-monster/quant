import json
from pathlib import Path
p = Path(r"C:\Users\MENGTAO\.cursor\projects\c-Users-MENGTAO-Desktop-E3-quant-worldquant-alpha\agent-tools\91ff136b-6a1b-4f71-b51c-2e0eb50d0fad.txt")
d = json.loads(p.read_text(encoding="utf-8"))
rows = d.get("results", [])
print("count", d.get("count"), len(rows))
for r in rows:
    id_ = r.get("id", "")
    name = r.get("name", "")
    blob = (id_ + " " + name).lower()
    if any(k in blob for k in ("earn", "sent", "matrix", "call")):
        print(f"{id_:35s} ac={r.get('alphaCount'):5} uc={r.get('userCount'):4} cov={r.get('coverage')}  {name[:70]}")
