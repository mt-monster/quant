import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for a in data.get("results") or []:
    is_ = a.get("is") or {}
    s = a.get("settings") or {}
    code = (a.get("regular") or {}).get("code", "")
    print(
        f"{a.get('id')}\t{a.get('dateCreated','')[:19]}\t"
        f"neut={s.get('neutralization')}\tdecay={s.get('decay')}\t"
        f"S={is_.get('sharpe')}\tF={is_.get('fitness')}\t{code[:85]}"
    )
