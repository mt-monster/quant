import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(
    "created",
    data.get("total_created"),
    "id",
    data.get("multisimulation_id"),
)
for r in data.get("alpha_results") or []:
    d = r.get("details") or {}
    is_ = d.get("is") or {}
    code = (d.get("regular") or {}).get("code", "")
    err = r.get("error") or d.get("error")
    if err:
        print(f"{r.get('alpha_id')}\tERROR\t{err}")
        continue
    checks = {c.get("name"): c for c in (is_.get("checks") or [])}
    y2 = (checks.get("LOW_2Y_SHARPE") or {}).get("value")
    print(
        f"{r.get('alpha_id')}\tS={is_.get('sharpe')}\tF={is_.get('fitness')}\t"
        f"T={is_.get('turnover')}\t2Y={y2}\t{code}"
    )
