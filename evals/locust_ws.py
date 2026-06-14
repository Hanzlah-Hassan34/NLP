"""
WebSocket concurrency ramp — measures end-to-end latency at increasing
levels of concurrent users hitting /ws/chat. Each simulated user sends
a fixed sequence of 3 turns.

Reports per-stage:
  - mean / median / p90 / p99 e2e latency
  - successful turn count, error count
  - turns-per-second throughput

Outputs a JSON results file and a concurrency-vs-latency PNG plot.

Usage:
    python evals/locust_ws.py --host localhost --port 8000 \\
        --users 1,2,4 --turns 3 --out evals/reports/concurrency_results.json

NOTE: With local CPU LLM (Qwen 2.5 1.5B), each LLM-backed turn takes
~20-30s. Keep --users small (1, 2, 4) to bound runtime.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

USER_TURNS = [
    "Hello",
    "What are your opening hours?",
    "How much does teeth whitening cost?",
]


async def one_user(uri: str, user_idx: int, turns: List[str], timeout: float = 240.0) -> List[Dict[str, Any]]:
    sid = f"load-{user_idx}-{uuid.uuid4().hex[:6]}"
    samples: List[Dict[str, Any]] = []
    try:
        async with websockets.connect(uri, ping_interval=None, max_size=None) as ws:
            try:
                await asyncio.wait_for(ws.recv(), timeout=10)  # info hello
            except Exception:
                pass
            for msg in turns:
                t0 = time.perf_counter()
                err: str | None = None
                t_first: float | None = None
                tokens = 0
                try:
                    await ws.send(json.dumps({
                        "type": "chat",
                        "session_id": sid,
                        "message": msg,
                        "stream": True,
                    }))
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        evt = json.loads(raw)
                        et = evt.get("type")
                        if et == "token":
                            tokens += 1
                            if t_first is None:
                                t_first = time.perf_counter()
                        elif et == "complete":
                            break
                        elif et == "error":
                            err = json.dumps(evt.get("data", {}))[:200]
                            break
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"
                t1 = time.perf_counter()
                samples.append({
                    "user_idx": user_idx,
                    "msg": msg,
                    "ttft_ms": (t_first - t0) * 1000 if t_first else (t1 - t0) * 1000,
                    "e2e_ms": (t1 - t0) * 1000,
                    "n_tokens": tokens,
                    "error": err,
                })
    except Exception as exc:
        samples.append({
            "user_idx": user_idx,
            "msg": "<connect>",
            "ttft_ms": 0.0,
            "e2e_ms": 0.0,
            "n_tokens": 0,
            "error": f"{type(exc).__name__}: {exc}",
        })
    return samples


def percentiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0, "median": 0, "p90": 0, "p99": 0}
    s = sorted(values)
    def pct(p: float) -> float:
        k = (len(s) - 1) * p
        f = int(k); c = min(f + 1, len(s) - 1)
        return s[f] + (s[c] - s[f]) * (k - f)
    return {
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "p90": round(pct(0.90), 2),
        "p99": round(pct(0.99), 2),
    }


async def run_stage(uri: str, n_users: int, turns: List[str]) -> Dict[str, Any]:
    print(f"\n[CONCURRENCY] Stage: {n_users} users x {len(turns)} turns")
    t_stage0 = time.perf_counter()
    coros = [one_user(uri, i, turns) for i in range(n_users)]
    all_results: List[List[Dict[str, Any]]] = await asyncio.gather(*coros)
    stage_dur = time.perf_counter() - t_stage0

    flat = [s for u in all_results for s in u]
    ok = [s for s in flat if s["error"] is None]
    errs = len(flat) - len(ok)
    e2e = [s["e2e_ms"] for s in ok]
    ttft = [s["ttft_ms"] for s in ok]
    turns_per_sec = len(ok) / stage_dur if stage_dur > 0 else 0.0

    print(f"  duration={stage_dur:.1f}s ok_turns={len(ok)} errors={errs} "
          f"throughput={turns_per_sec:.2f} turns/s")
    if e2e:
        print(f"  e2e: mean={statistics.mean(e2e):.0f}ms p90={percentiles(e2e)['p90']:.0f}ms")

    return {
        "users": n_users,
        "turns_per_user": len(turns),
        "duration_s": round(stage_dur, 2),
        "n_total_turns": len(flat),
        "n_ok_turns": len(ok),
        "n_errors": errs,
        "throughput_turns_per_s": round(turns_per_sec, 3),
        "ttft_ms": percentiles(ttft),
        "e2e_ms": percentiles(e2e),
        "raw": flat,
    }


def render_plot(report: Dict[str, Any], out_dir: Path) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"[CONCURRENCY] matplotlib unavailable: {exc}")
        return None

    stages = report["stages"]
    if not stages:
        return None
    users = [s["users"] for s in stages]
    e2e_mean = [s["e2e_ms"]["mean"] for s in stages]
    e2e_p90 = [s["e2e_ms"]["p90"] for s in stages]
    thr = [s["throughput_turns_per_s"] for s in stages]

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.plot(users, e2e_mean, "o-", label="e2e mean (ms)")
    ax1.plot(users, e2e_p90, "s--", label="e2e p90 (ms)")
    ax1.set_xlabel("Concurrent users")
    ax1.set_ylabel("Latency (ms)")
    ax1.legend(loc="upper left")
    ax2 = ax1.twinx()
    ax2.plot(users, thr, "g^:", label="throughput (turns/s)")
    ax2.set_ylabel("Throughput (turns/s)")
    ax2.legend(loc="upper right")
    ax1.set_title("Concurrency vs latency / throughput")
    fig.tight_layout()
    p = out_dir / "concurrency_curve.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    return str(p)


async def amain(host: str, port: int, user_levels: List[int], turns: int, out: str) -> int:
    uri = f"ws://{host}:{port}/ws/chat"
    turn_list = USER_TURNS[:turns] if turns <= len(USER_TURNS) else USER_TURNS + (
        [USER_TURNS[-1]] * (turns - len(USER_TURNS))
    )
    report: Dict[str, Any] = {"uri": uri, "turn_set": turn_list, "stages": []}
    for n in user_levels:
        stage = await run_stage(uri, n, turn_list)
        report["stages"].append(stage)

    plot = render_plot(report, REPORTS_DIR)
    if plot:
        report["plot"] = plot

    # Sustainable concurrency: highest stage where p90 e2e < 30s and 0 errors.
    sustainable = 0
    breakpoint_users = None
    for st in report["stages"]:
        if st["n_errors"] == 0 and st["e2e_ms"]["p90"] < 30000:
            sustainable = st["users"]
        else:
            breakpoint_users = breakpoint_users or st["users"]
    report["sustainable_concurrency"] = sustainable
    report["breakpoint_users"] = breakpoint_users

    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n=== Concurrency Summary ===")
    for s in report["stages"]:
        print(f"  users={s['users']:>2}  ok={s['n_ok_turns']:>3}/{s['n_total_turns']:>3}  "
              f"e2e mean={s['e2e_ms']['mean']:>6}ms p90={s['e2e_ms']['p90']:>6}ms "
              f"throughput={s['throughput_turns_per_s']:.2f} turns/s")
    print(f"Sustainable concurrency: {sustainable} users")
    print(f"Saved -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.getenv("DENTABOT_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.getenv("DENTABOT_PORT", "8000")))
    ap.add_argument("--users", default="1,2,4",
                    help="comma-separated concurrency levels")
    ap.add_argument("--turns", type=int, default=3,
                    help="number of turns each simulated user sends")
    ap.add_argument("--out", default=str(REPORTS_DIR / "concurrency_results.json"))
    args = ap.parse_args()
    levels = [int(x) for x in args.users.split(",") if x.strip()]
    return asyncio.run(amain(args.host, args.port, levels, args.turns, args.out))


if __name__ == "__main__":
    sys.exit(main())
