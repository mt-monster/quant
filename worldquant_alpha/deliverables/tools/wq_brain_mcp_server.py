#!/usr/bin/env python3
"""WQ BRAIN MCP Server — 暴露 WorldQuant Brain API 为 MCP 工具，供 WorkBuddy 调用。

工具列表：
  wq_check_alpha(alpha_id)      — 查详情 + IS 硬闸门
  wq_submit_alpha(alpha_id)     — 补描述 → 提交 → 轮询
  wq_list_candidates()          — 从所有 checkpoint 抽候选列表
  wq_get_status(alpha_id)       — 仅查 status/dateSubmitted
  wq_bulk_check(alpha_ids)      — 批量 IS 闸门检查
"""
import json, os, sys, time
from urllib.parse import urljoin

# 项目路径
PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)
os.chdir(PROJ)

from wd_lib_wrapper import WqApiSimple
from mcp.server.fastmcp import FastMCP

BASE = "https://api.worldquantbrain.com"
mcp = FastMCP("wq-brain")

api = None

def _api():
    global api
    if api is None:
        api = WqApiSimple()
    return api


def _load_checkpoints():
    """从 results/*_checkpoint.json 加载所有候选 alpha。"""
    import glob as _g
    cands = []
    for f in sorted(_g.glob(os.path.join(PROJ, "results", "*_checkpoint.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        task = os.path.basename(f).replace("_checkpoint.json", "")
        res = d.get("results", []) if isinstance(d, dict) else d
        for r in (res if isinstance(res, list) else []):
            st = str(r.get("status", ""))
            if st in ("PASS_CHEAP", "CHECK_PENDING"):
                cands.append({
                    "pid": r.get("pid", "?"),
                    "task": task,
                    "label": r.get("label", "?"),
                    "status": st,
                    "sharpe": r.get("sharpe"),
                    "fitness": r.get("fitness"),
                    "expr": r.get("expr", "")[:120],
                })
    cands.sort(key=lambda x: -(x["sharpe"] or 0))
    return cands


# ═══════════════ 工具定义 ═══════════════

@mcp.tool()
def wq_check_alpha(alpha_id: str) -> str:
    """检查单个 alpha 的平台状态和 IS 硬闸门。
    Args:
        alpha_id: WQ alpha ID (如 YPgAa3WR)
    Returns: JSON 格式 {status, dateSubmitted, is_checks, submittable}
    """
    a = _api()
    det = a.get_alpha_details(alpha_id)
    result = {
        "alpha_id": alpha_id,
        "status": det.get("status"),
        "dateSubmitted": det.get("dateSubmitted"),
        "is": {},
        "checks": [],
        "submittable": False,
    }
    is_ = det.get("is") or {}
    result["is"] = {
        "sharpe": is_.get("sharpe"),
        "fitness": is_.get("fitness"),
        "turnover": is_.get("turnover"),
        "margin": is_.get("margin"),
    }
    try:
        s = a.session
        chk = s.get(urljoin(BASE, f"alphas/{alpha_id}/check"), timeout=60)
        if chk.ok and chk.text.strip():
            cj = chk.json()
            checks = (cj.get("is") or {}).get("checks") or []
            fails = [c for c in checks if c.get("result") == "FAIL"]
            warns = [c for c in checks if c.get("result") == "WARNING"]
            result["checks"] = checks
            result["fail_count"] = len(fails)
            result["warn_count"] = len(warns)
            result["submittable"] = len(fails) == 0 and len(checks) > 0
            if fails:
                result["fail_details"] = [
                    f"{c['name']}={c.get('value')} (limit={c.get('limit')})" for c in fails
                ]
    except Exception as e:
        result["check_error"] = str(e)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def wq_submit_alpha(alpha_id: str) -> str:
    """提交 alpha 到 WQ BRAIN 平台。
    步骤：补 description → PATCH → POST /submit → 轮询 3min。
    Args:
        alpha_id: 要提交的 alpha ID
    Returns: JSON {success, status, dateSubmitted, message}
    """
    a = _api()
    s = a.session

    # 先查当前状态
    det = a.get_alpha_details(alpha_id)
    if det.get("status") and det.get("status") != "UNSUBMITTED":
        return json.dumps({
            "success": True if det["status"] == "ACTIVE" else None,
            "alpha_id": alpha_id,
            "status": det["status"],
            "dateSubmitted": det.get("dateSubmitted"),
            "message": f"Already {det['status']} — no action needed",
        }, ensure_ascii=False, indent=2)

    # 从 checkpoint 取 description 素材
    cands = _load_checkpoints()
    c = next((x for x in cands if x["pid"] == alpha_id), None)
    label = c["label"] if c else alpha_id

    desc = (
        f"PPA alpha on USA EQUITY TOP3000, delay 1. "
        f"Signal constructed from quantitative factor mining pipeline. "
        f"IS metrics: sharpe={c['sharpe'] if c else '?'}, fitness={c['fitness'] if c else '?'}. "
        f"Industry-neutralized with low turnover design for reduced trading cost. "
        f"Submitted for Power Pool Alpha (PPA) program evaluation."
    )
    # PATCH description
    s.patch(urljoin(BASE, f"alphas/{alpha_id}"),
            json={"name": f"ppa_{label}"[:80], "regular": {"description": desc}, "color": "GREEN"})

    # POST submit
    r = s.post(urljoin(BASE, f"alphas/{alpha_id}/submit"))
    submit_ok = r.status_code in (200, 201, 202)

    # Poll (up to 3 min)
    final_st, final_dsub = "UNSUBMITTED", None
    for _ in range(36):
        d = a.get_alpha_details(alpha_id)
        final_st = d.get("status")
        final_dsub = d.get("dateSubmitted")
        if final_dsub or (final_st and final_st != "UNSUBMITTED"):
            break
        time.sleep(5)

    return json.dumps({
        "success": final_st == "ACTIVE",
        "alpha_id": alpha_id,
        "submit_response": r.status_code,
        "submit_ok": submit_ok,
        "final_status": final_st,
        "dateSubmitted": final_dsub,
        "message": "ACTIVE — successfully submitted!" if final_st == "ACTIVE"
                    else ("UNSUBMITTED — likely hard gate FAIL (needs OOS first)" if final_st == "UNSUBMITTED"
                          else f"Status: {final_st}"),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def wq_list_candidates() -> str:
    """列出所有 checkpoint 中的候选 alpha（PASS_CHEAP + CHECK_PENDING），按 Sharpe 降序。
    Returns: JSON 数组 [{pid, task, label, status, sharpe, fitness, expr}]
    """
    cands = _load_checkpoints()
    return json.dumps(cands, ensure_ascii=False, indent=2)


@mcp.tool()
def wq_get_status(alpha_id: str) -> str:
    """仅查询 alpha 的提交状态（轻量，不跑 IS check）。
    Args:
        alpha_id: WQ alpha ID
    Returns: JSON {alpha_id, status, dateSubmitted}
    """
    a = _api()
    det = a.get_alpha_details(alpha_id)
    return json.dumps({
        "alpha_id": alpha_id,
        "status": det.get("status"),
        "dateSubmitted": det.get("dateSubmitted"),
        "sharpe": (det.get("is") or {}).get("sharpe"),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def wq_bulk_check(alpha_ids: str) -> str:
    """批量检查多个 alpha 的 IS 闸门（逗号分隔）。
    Args:
        alpha_ids: 逗号分隔的 alpha ID 列表，如 "YPgAa3WR,zqRkPVbX,j2rrpVzO"
    Returns: JSON [{alpha_id, status, submittable, fail_count}]
    """
    ids = [x.strip() for x in alpha_ids.split(",") if x.strip()]
    results = []
    for aid in ids:
        try:
            r = json.loads(wq_check_alpha(aid))
            results.append({
                "alpha_id": aid,
                "status": r.get("status"),
                "submittable": r.get("submittable"),
                "fail_count": r.get("fail_count", 0),
            })
        except Exception as e:
            results.append({"alpha_id": aid, "error": str(e)})
        time.sleep(0.5)
    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
