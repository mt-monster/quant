import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from dotenv import load_dotenv
load_dotenv()
from wd_lib_wrapper import WqApiSimple
api = WqApiSimple()
alphas = api.get_alphas(limit=10)
print(f"Found {len(alphas)} alphas")
for a in alphas[:10]:
    aid = a.get("id", "?")
    status = a.get("status", "?")
    atype = a.get("type", "?")
    print(f"  {aid} status={status} type={atype}")
