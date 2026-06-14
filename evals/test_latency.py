"""
Latency Benchmark — measures TTFT, inter-token, and end-to-end response time
for four scenarios:
  (a) simple   : greetings / FAQ-style prompts that don't trigger RAG/tools
  (b) rag      : prompts that should hit RAG (kb questions)
  (c) tool     : prompts that should hit a tool (cost / weather)
  (d) mixed    : prompts that should hit both RAG and a tool

Connects to ws://<host>:<port>/ws/chat.

Caveat: the current engine generates the FULL reply synchronously, then the
WebSocket handler streams the already-formed reply word-by-word. Therefore
TTFT here = time from user message to the first 'token' event AFTER the
full LLM call has finished. We document this in the report. Inter-token
latency is therefore an artefact of the streaming chunker, not of LLM
generation, and is reported only for completeness.
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

DEFAULT_HOST = os.getenv("DENTABOT_HOST", "localhost")
DEFAULT_PORT = int(os.getenv("DENTABOT_PORT", "8000"))


SCENARIOS: Dict[str, List[str]] = {
    "simple": [
        "Hello",
        "Hi there",
        "Good morning",
        "Thanks",
        "Thank you",
        "Hi",
        "Hey",
        "Good afternoon",
        "Hello, how are you?",
        "Good evening",
    ],
    "rag": [
        "What are your opening hours?",
        "Where is the clinic located?",
        "Do you treat children?",
        "Do you offer Invisalign?",
        "How long does a routine checkup take?",
        "What insurance providers do you accept?",
        "Do you have wheelchair access?",
        "Can I bring my child?",
        "Is the clinic open on Sundays?",
        "What payment methods do you accept?",
    ],
    "tool": [
        "How much does teeth whitening cost?",
        "What is the price of braces?",
        "How much do dental implants cost?",
        "What's the weather today?",
        "Is it raining outside?",
        "How expensive is a root canal?",
        "What's the cost of a filling?",
        "How is the weather in Lahore?",
        "Cost of a routine cleaning?",
        "Is it hot outside?",
    ],
    "mixed": [
        "How much does a wisdom tooth removal cost and what days are you open?",
        "What's the price of veneers and where is the clinic?",
        "Cost of braces and do you accept insurance?",
        "How much does whitening cost and can I come tomorrow?",
        "Price of a checkup and what are your hours?",
        "Cost of a filling and how do I get there?",
        "What does an extraction cost and is parking available?",
        "Implant cost and what insurance do you accept?",
        "Cleaning fee and is the clinic kid-friendly?",
        "Root canal price and how long does it take?",
    ],
}


async def one_turn(uri: str, message: str, timeout: float = 180.0) -> Dict[str, Any]:
    """Send one message over WS, return timing breakdown."""
    sid = f"lat-{uuid.uuid4().hex[:8]}"
    payload = {
        "type": "chat",
        "session_id": sid,
        "message": message,
        "stream": True,
    }
    t_send: float = 0.0
    t_first_token: float | None = None
    t_last_token: float | None = None
    t_complete: float | None = None
    token_times: List[float] = []
    error: str | None = None

    try:
        async with websockets.connect(uri, ping_interval=None, max_size=None) as ws:
            # Server sends an initial 'info' event; consume it.
            try:
                _hello = await asyncio.wait_for(ws.recv(), timeout=10)
            except Exception:
                pass

            t_send = time.perf_counter()
            await ws.send(json.dumps(payload))

            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                evt = json.loads(raw)
                etype = evt.get("type")
                now = time.perf_counter()
                if etype == "token":
                    if t_first_token is None:
                        t_first_token = now
                    token_times.append(now)
                    t_last_token = now
                elif etype == "complete":
                    t_complete = now
                    break
                elif etype == "error":
                    error = json.dumps(evt.get("data", {}))[:200]
                    t_complete = now
                    break
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    if t_complete is None:
        t_complete = time.perf_counter()
    if t_first_token is None:
        t_first_token = t_complete
    if t_last_token is None:
        t_last_token = t_complete

    inter_token_ms: List[float] = []
    if len(token_times) >= 2:
        for a, b in zip(token_times[:-1], token_times[1:]):
            inter_token_ms.append((b - a) * 1000)

    return {
        "ttft_ms": (t_first_token - t_send) * 1000,
        "e2e_ms": (t_complete - t_send) * 1000,
        "stream_ms": (t_last_token - t_first_token) * 1000,
        "inter_token_ms_mean": (
            statistics.mean(inter_token_ms) if inter_token_ms else 0.0
        ),
        "n_tokens": len(token_times),
        "error": error,
    }


def percentiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0, "median": 0, "p90": 0, "p99": 0, "min": 0, "max": 0}
    s = sorted(values)
    def pct(p: float) -> float:
        if not s:
            return 0.0
        k = (len(s) - 1) * p
        f = int(k)
        c = min(f + 1, len(s) - 1)
        return s[f] + (s[c] - s[f]) * (k - f)
    return {
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "p90": round(pct(0.90), 2),
        "p99": round(pct(0.99), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


async def run_scenario(uri: str, name: str, prompts: List[str], trials: int) -> Dict[str, Any]:
    samples: List[Dict[str, Any]] = []
    print(f"\n[LATENCY] Scenario '{name}' — {trials} trials")
    for i in range(trials):
        prompt = prompts[i % len(prompts)]
        sample = await one_turn(uri, prompt)
        samples.append({"prompt": prompt, **sample})
        ok = "OK" if sample["error"] is None else f"ERR({sample['error'][:40]})"
        print(f"  [{i+1:>2}/{trials}] ttft={sample['ttft_ms']:>7.0f}ms "
              f"e2e={sample['e2e_ms']:>7.0f}ms tokens={sample['n_tokens']:>3} {ok}")

    ok_samples = [s for s in samples if s["error"] is None]
    return {
        "scenario": name,
        "n_trials": trials,
        "n_ok": len(ok_samples),
        "n_errors": trials - len(ok_samples),
        "ttft_ms": percentiles([s["ttft_ms"] for s in ok_samples]),
        "e2e_ms": percentiles([s["e2e_ms"] for s in ok_samples]),
        "stream_ms": percentiles([s["stream_ms"] for s in ok_samples]),
        "inter_token_ms_mean": percentiles(
            [s["inter_token_ms_mean"] for s in ok_samples if s["inter_token_ms_mean"] > 0]
        ),
        "samples": samples,
    }


def render_plots(report: Dict[str, Any], out_dir: Path) -> List[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        print(f"[LATENCY] matplotlib unavailable: {exc}")
        return []

    saved: List[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    # Histogram of e2e per scenario.
    fig, ax = plt.subplots(figsize=(8, 5))
    for sc in report["scenarios"]:
        vals = [s["e2e_ms"] for s in sc["samples"] if s["error"] is None]
        if vals:
            ax.hist(vals, bins=12, alpha=0.55, label=sc["scenario"])
    ax.set_xlabel("End-to-end latency (ms)")
    ax.set_ylabel("Count")
    ax.set_title("End-to-end latency distribution by scenario")
    ax.legend()
    fig.tight_layout()
    p1 = out_dir / "latency_e2e_hist.png"
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    saved.append(str(p1))

    # TTFT bar chart of mean / p90.
    fig, ax = plt.subplots(figsize=(8, 5))
    names = [s["scenario"] for s in report["scenarios"]]
    means = [s["ttft_ms"]["mean"] for s in report["scenarios"]]
    p90s = [s["ttft_ms"]["p90"] for s in report["scenarios"]]
    x = range(len(names))
    ax.bar([i - 0.2 for i in x], means, width=0.4, label="mean")
    ax.bar([i + 0.2 for i in x], p90s, width=0.4, label="p90")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names)
    ax.set_ylabel("TTFT (ms)")
    ax.set_title("Time-to-first-token by scenario")
    ax.legend()
    fig.tight_layout()
    p2 = out_dir / "latency_ttft_bars.png"
    fig.savefig(p2, dpi=120)
    plt.close(fig)
    saved.append(str(p2))

    return saved


async def amain(host: str, port: int, trials: int, scenarios: List[str], out: str) -> int:
    uri = f"ws://{host}:{port}/ws/chat"
    print(f"[LATENCY] Connecting to {uri}, {trials} trials per scenario")
    report: Dict[str, Any] = {
        "uri": uri,
        "trials_per_scenario": trials,
        "scenarios": [],
    }
    for sc in scenarios:
        sc_report = await run_scenario(uri, sc, SCENARIOS[sc], trials)
        report["scenarios"].append(sc_report)

    plots = render_plots(report, REPORTS_DIR)
    report["plots"] = plots

    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n=== Latency Summary ===")
    for sc in report["scenarios"]:
        ttft = sc["ttft_ms"]
        e2e = sc["e2e_ms"]
        print(f"  {sc['scenario']:>7}  ttft mean={ttft['mean']:>6}ms "
              f"p90={ttft['p90']:>6}ms  e2e mean={e2e['mean']:>6}ms "
              f"p90={e2e['p90']:>6}ms  errors={sc['n_errors']}")
    print(f"Saved -> {out}")
    if plots:
        print(f"Plots -> {', '.join(plots)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument(
        "--scenarios",
        default="simple,rag,tool,mixed",
        help="comma-separated subset of: simple,rag,tool,mixed",
    )
    ap.add_argument("--out", default=str(REPORTS_DIR / "latency_results.json"))
    args = ap.parse_args()
    scs = [s.strip() for s in args.scenarios.split(",") if s.strip() in SCENARIOS]
    return asyncio.run(amain(args.host, args.port, args.trials, scs, args.out))


if __name__ == "__main__":
    sys.exit(main())
