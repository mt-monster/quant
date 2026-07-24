import sys, time, json
sys.path.insert(0, r"C:\Users\MENGTAO\Desktop\E3\quant\worldquant_alpha")
from wd_lib_wrapper import WqApiSimple
from urllib.parse import urljoin

a = WqApiSimple()
pid = "YPgAa3WR"
BASE = "https://api.worldquantbrain.com"
s = a.session

# 再次提交（WQ 对未提交 alpha 重复 submit 通常幂等/报错已提交，可据此判断是否已生效）
r = s.post(urljoin(BASE, f"alphas/{pid}/submit"))
print("re-SUBMIT http:", r.status_code, "| body:", r.text[:400])

time.sleep(8)
d = a.get_alpha_details(pid)
print("status:", d.get("status"), "| submission_status:", d.get("submission_status"),
      "| submitted_at:", d.get("submitted_at"))
