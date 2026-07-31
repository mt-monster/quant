# -*- coding: utf-8 -*-
import requests
try:
    r = requests.get("https://api.worldquantbrain.com/authentication", timeout=20)
    print("STATUS", r.status_code)
except Exception as e:
    print("ERR", repr(e))
