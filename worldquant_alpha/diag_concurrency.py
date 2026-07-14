# -*- coding: utf-8 -*-
"""并发上限诊断 v2：复用挖掘脚本的真实 SETTINGS（language=FASTEXPR），
阶梯式提交 rank(close)，统计 t0 接受数并捕获 429 报文。"""
import sys, os, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
# 安全导入：SETINGS 为模块级常量，import 不触发网络
from mine_usa_ppa_multi import SETTINGS
import requests
from urllib.parse import urljoin

API = "https://api.worldquantbrain.com/"
U, P = os.environ["WQ_USERNAME"], os.environ["WQ_PASSWORD"]
s = requests.Session(); s.auth = (U, P)
s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
r = s.post(urljoin(API, "authentication"), timeout=60); r.raise_for_status()
print("AUTH OK", flush=True)

# SETTINGS 真实副本
SET = dict(SETTINGS)
print("SETTINGS language=%s neut=%s decay=%s trunc=%s testPeriod=%s" % (
    SET.get("language"), SET.get("neutralization"),
    SET.get("decay"), SET.get("truncation"), SET.get("testPeriod")), flush=True)

data_tmpl = {"type": "REGULAR", "settings": SET, "regular": "rank(close)"}

print("\n=== 阶梯式提交 12 条（间隔 0.3s，观察接受窗口）===", flush=True)
res = []
for i in range(12):
    try:
        rr = s.post(urljoin(API, "simulations"), json=data_tmpl, timeout=120)
        body = rr.text[:400]
        res.append((i, rr.status_code, body))
        tag = "ACCEPT" if rr.status_code in (200, 201) else "REJECT"
        print(f"  #{i:02d} -> {rr.status_code} [{tag}]", flush=True)
        if rr.status_code == 429:
            print("    >>> 429 报文:", body, flush=True)
    except Exception as e:
        res.append((i, "ERR", str(e)[:200]))
        print(f"  #{i:02d} -> ERR {e}", flush=True)
    time.sleep(0.3)

accepted = [x for x in res if x[1] in (200, 201)]
rejected = [x for x in res if x[1] != 200 and x[1] != 201]
print(f"\n汇总: 接受 {len(accepted)} | 拒绝 {len(rejected)}", flush=True)
# t0 接受窗口：连续接受段长度（去除后续因释放而接受的情况，仅看首批连续 2xx）
run = 0; best = 0
for x in res:
    if x[1] in (200, 201):
        run += 1; best = max(best, run)
    else:
        run = 0
print("首批连续接受数（≈ 可用槽位数 = C - 孤儿数）:", best, flush=True)
print("DIAG_DONE", flush=True)
