"""
Tool-Calling Accuracy — drives utterances through the live engine via
/v1/eval/chat and compares the actually triggered tools against the
expected tool set in evals/data/tool_calling_dataset.json.

Computes:
  - per-tool precision, recall, F1
  - false-positive rate on negative cases (utterances that should NOT
    trigger any tool)
  - exact-set match rate (precision-style)

Usage:
    python evals/test_tool_calling_accuracy.py --base-url http://localhost:8000 \\
        --out evals/reports/tool_calling_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_PATH = Path(__file__).parent / "data" / "tool_calling_dataset.json"
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_URL = os.getenv("DENTABOT_BASE_URL", "http://localhost:8000")


def _post(base_url: str, sid: str, message: str, timeout: int = 90) -> Dict[str, Any]:
    r = requests.post(
        f"{base_url}/v1/eval/chat",
        json={"session_id": sid, "message": message},
        timeout=timeout,
    )
    if not r.ok:
        return {"reply": "", "tools_used": [], "_error": f"HTTP {r.status_code}"}
    return r.json()


def _reset(base_url: str, sid: str) -> None:
    try:
        requests.post(f"{base_url}/v1/eval/reset", json={"session_id": sid}, timeout=10)
    except Exception:
        pass


def _seed_session(base_url: str, sid: str, preconditions: Dict[str, Any]) -> None:
    """For appointment-related cases we need to walk the patient through the
    initial intent gate (the engine refuses to dispatch booking tools until
    new/existing patient status is set)."""
    if not preconditions:
        return
    status = preconditions.get("patient_status")
    name = preconditions.get("patient_name")
    if status == "new":
        _post(base_url, sid, "Hi")
        _post(base_url, sid, "I'm a new patient")
    elif status == "existing":
        _post(base_url, sid, "Hi")
        _post(base_url, sid, "I'm an existing patient")
        if name:
            _post(base_url, sid, f"My name is {name}")


def evaluate(base_url: str) -> Dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        ds = json.load(f)
    cases = ds["cases"]

    per_tool = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    case_results: List[Dict[str, Any]] = []
    n_neg = 0
    n_neg_correct = 0
    n_exact_match = 0

    for case in cases:
        sid = f"toolcall-{case['id']}-{uuid.uuid4().hex[:6]}"
        _reset(base_url, sid)
        _seed_session(base_url, sid, case.get("preconditions") or {})

        resp = _post(base_url, sid, case["utterance"])
        actual: Set[str] = set(resp.get("tools_used", []) or [])
        expected: Set[str] = set(case.get("expected_tools", []) or [])

        # Per-tool TP/FP/FN.
        all_tools = actual | expected
        for t in all_tools:
            if t in actual and t in expected:
                per_tool[t]["tp"] += 1
            elif t in actual and t not in expected:
                per_tool[t]["fp"] += 1
            elif t not in actual and t in expected:
                per_tool[t]["fn"] += 1

        is_negative = len(expected) == 0
        if is_negative:
            n_neg += 1
            if not actual:
                n_neg_correct += 1

        if actual == expected:
            n_exact_match += 1

        case_results.append({
            "id": case["id"],
            "utterance": case["utterance"],
            "category": case.get("category"),
            "expected": sorted(expected),
            "actual": sorted(actual),
            "exact_match": actual == expected,
            "intent": resp.get("intent"),
            "reply_preview": (resp.get("reply") or "")[:120],
        })

    per_tool_metrics: Dict[str, Any] = {}
    macro_p, macro_r, macro_f1 = [], [], []
    for tool, c in per_tool.items():
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        per_tool_metrics[tool] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        }
        macro_p.append(prec); macro_r.append(rec); macro_f1.append(f1)

    summary = {
        "base_url": base_url,
        "n_cases": len(cases),
        "n_exact_match": n_exact_match,
        "exact_match_rate": round(n_exact_match / max(len(cases), 1), 4),
        "n_negative": n_neg,
        "negative_accuracy": round(n_neg_correct / n_neg, 4) if n_neg else None,
        "false_positive_rate_on_negatives": round(
            (n_neg - n_neg_correct) / n_neg, 4
        ) if n_neg else None,
        "macro_precision": round(sum(macro_p) / len(macro_p), 4) if macro_p else 0.0,
        "macro_recall": round(sum(macro_r) / len(macro_r), 4) if macro_r else 0.0,
        "macro_f1": round(sum(macro_f1) / len(macro_f1), 4) if macro_f1 else 0.0,
        "per_tool": per_tool_metrics,
        "cases": case_results,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(REPORTS_DIR / "tool_calling_results.json"))
    args = ap.parse_args()

    try:
        h = requests.get(f"{args.base_url}/healthz", timeout=5)
        if not h.ok:
            raise RuntimeError(str(h.status_code))
    except Exception as exc:
        print(f"[ERROR] Server not reachable at {args.base_url}: {exc}")
        return 1

    s = evaluate(args.base_url)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

    print("\n=== Tool-Calling Accuracy Summary ===")
    print(f"Cases:                  {s['n_cases']}")
    print(f"Exact match rate:       {s['exact_match_rate']:.2%}")
    print(f"Negative accuracy:      {s['negative_accuracy']}")
    print(f"FP rate on negatives:   {s['false_positive_rate_on_negatives']}")
    print(f"Macro precision:        {s['macro_precision']:.3f}")
    print(f"Macro recall:           {s['macro_recall']:.3f}")
    print(f"Macro F1:               {s['macro_f1']:.3f}")
    print("\nPer-tool:")
    for t, m in s["per_tool"].items():
        print(f"  {t:>22}  P={m['precision']:.2f} R={m['recall']:.2f} "
              f"F1={m['f1']:.2f}  tp={m['tp']} fp={m['fp']} fn={m['fn']}")
    print(f"\nSaved -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
