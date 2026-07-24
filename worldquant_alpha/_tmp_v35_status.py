"""Quick V35 progress snapshot."""
import json
from datetime import datetime
from pathlib import Path

LOG = Path("results/v35_news_nlp_progress_20260723_174611.log")
CKPT = Path("results/v35_news_nlp_checkpoint.json")
PID = 32928


def pid_alive(pid: int) -> bool:
    try:
        import ctypes

        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        exit_code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(exit_code))
        k.CloseHandle(h)
        return bool(ok) and exit_code.value == 259  # STILL_ACTIVE
    except Exception:
        return False


def main() -> None:
    now = datetime.now().strftime("%H:%M:%S")
    alive = pid_alive(PID)
    if not LOG.exists():
        print(f"[{now}] V35 log missing | pid={PID} {'alive' if alive else 'DEAD'}")
        return

    lines = LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    o = json.loads(lines[-1])
    d = json.load(CKPT.open(encoding="utf-8")) if CKPT.exists() else {}
    rs = d.get("results", [])
    found = d.get("found_alphas", [])
    passes = sum(1 for r in rs if r.get("status") == "PASS" or r.get("found"))
    fails = sum(1 for r in rs if r.get("status") == "FAIL")

    done = o.get("done")
    total = o.get("total")
    pct = o.get("pct")
    eta = o.get("eta")
    elapsed = o.get("elapsed_sec")
    print(
        f"[{now}] V35 {done}/{total} ({pct}%) | eta={eta} | "
        f"elapsed={elapsed:.0f}s | pid={PID} {'alive' if alive else 'DEAD'}"
    )
    print(f"  checkpoint: results={len(rs)} PASS/found={passes} FAIL={fails} found_alphas={len(found)}")

    recent = o.get("recent") or []
    if recent:
        tops = sorted(rs, key=lambda x: abs(x.get("sharpe") or 0), reverse=True)[:3]
        if tops:
            print("  top |S|:")
            for r in tops:
                print(
                    f"    {r.get('label')}: S={r.get('sharpe')} F={r.get('fitness')} "
                    f"TVR={r.get('tvr')} status={r.get('status')}"
                )
        r = recent[-1]
        print(
            f"  latest: step={r.get('step')} {r.get('label')} "
            f"S={r.get('sharpe')} F={r.get('fitness')} status={r.get('status')}"
        )

    if o.get("event") in ("done", "complete", "finish") or (alive is False and done == total):
        print("  *** V35 FINISHED ***")


if __name__ == "__main__":
    main()
