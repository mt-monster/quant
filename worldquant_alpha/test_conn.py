import sys, os, time, json
sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv()
from wd_lib_wrapper import WqApiSimple
t0=time.time()
try:
    api = WqApiSimple()
    print("AUTH OK in %.1fs" % (time.time()-t0))
    s = api.session
    r = s.get("https://api.worldquantbrain.com/datasets?limit=1")
    print("datasets status:", r.status_code)
    if r.status_code==200:
        d=r.json()
        results = d.get("results", [])
        print("sample dataset:", json.dumps(results[0], ensure_ascii=False)[:500] if results else "none")
except Exception as e:
    print("ERROR:", repr(e))
