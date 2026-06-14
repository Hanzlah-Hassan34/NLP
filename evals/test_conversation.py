"""
Conversation Evaluation — drives the live DentaBot server through every
test dialogue, captures transcripts, and scores each one with the Gemini
LLM judge plus deterministic policy/keyword checks.

Usage:
    # Pytest mode — dialogues are loaded as parametrized tests.
    pytest evals/test_conversation.py -v

    # Standalone mode — produces transcripts + judge scores + summary JSON.
    python evals/test_conversation.py --base-url http://localhost:8000 \\
        --out evals/reports/conversation_results.json

The server must be running with /v1/eval/chat available.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals.llm_judge import has_gemini_key, judge_dialogue  # noqa: E402

DATA_PATH = Path(__file__).parent / "data" / "conversations.json"
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_URL = os.getenv("DENTABOT_BASE_URL", "http://localhost:8000")

REFUSAL_SIGNALS = (
    "i can't",
    "i cannot",
    "i'm not able",
    "i am not able",
    "outside the scope",
    "out of scope",
    "i'm sorry",
    "i can only help",
    "please consult",
    "schedule an appointment",
    "book an appointment",
)


def load_conversations() -> List[Dict[str, Any]]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def server_alive(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url}/healthz", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def run_dialogue(base_url: str, dialogue: Dict[str, Any], timeout: int = 180) -> List[Dict[str, Any]]:
    session_id = f"eval-{dialogue['id']}-{uuid.uuid4().hex[:6]}"
    try:
        requests.post(f"{base_url}/v1/eval/reset",
                      json={"session_id": session_id}, timeout=10)
    except Exception:
        pass

    transcript: List[Dict[str, Any]] = []
    for turn in dialogue["turns"]:
        user_msg = turn["user"]
        t0 = time.perf_counter()
        try:
            resp = requests.post(
                f"{base_url}/v1/eval/chat",
                json={"session_id": session_id, "message": user_msg},
                timeout=timeout,
            )
            data = resp.json() if resp.ok else {"reply": f"[HTTP {resp.status_code}]"}
        except Exception as exc:
            data = {"reply": f"[ERROR: {type(exc).__name__}: {exc}]"}
        client_ms = int((time.perf_counter() - t0) * 1000)
        transcript.append({
            "user": user_msg,
            "bot": data.get("reply", ""),
            "tools_used": data.get("tools_used", []),
            "rag_chunks": data.get("rag_chunks", 0),
            "server_ms": data.get("server_ms", 0),
            "client_ms": client_ms,
            "used_llm": data.get("used_llm", False),
            "intent": data.get("intent", ""),
            "expected_intent": turn.get("expected_intent"),
            "expected_slot": turn.get("expected_slot"),
        })
    return transcript


def heuristic_refusal(transcript: List[Dict[str, Any]]) -> bool:
    text = " ".join(t.get("bot", "") for t in transcript).lower()
    return any(sig in text for sig in REFUSAL_SIGNALS)


def evaluate_all(base_url: str) -> Dict[str, Any]:
    conversations = load_conversations()
    results: List[Dict[str, Any]] = []
    judge_available = has_gemini_key()

    print(f"\n[CONV-EVAL] Driving {len(conversations)} dialogues against {base_url}")
    print(f"[CONV-EVAL] Judge: {'Gemini 2.0 Flash' if judge_available else 'heuristic only'}")

    for idx, dlg in enumerate(conversations, 1):
        print(f"  [{idx}/{len(conversations)}] {dlg['id']} "
              f"({len(dlg['turns'])} turns) ... ", end="", flush=True)
        transcript = run_dialogue(base_url, dlg)
        score = judge_dialogue(dlg, transcript)
        det_refusal = heuristic_refusal(transcript)
        is_policy_case = bool(dlg.get("policy_violations"))
        if is_policy_case:
            policy_ok = bool(score.policy_adherence) or det_refusal
        else:
            policy_ok = bool(score.policy_adherence)
        results.append({
            "id": dlg["id"],
            "description": dlg.get("description"),
            "expected_outcome": dlg.get("expected_outcome"),
            "is_policy_case": is_policy_case,
            "deterministic_refusal": det_refusal,
            "judge": score.as_dict(),
            "task_completed": bool(score.task_completion),
            "policy_adherent": policy_ok,
            "coherence": score.coherence,
            "transcript": transcript,
        })
        print(f"task={int(bool(score.task_completion))} "
              f"policy={int(policy_ok)} coh={score.coherence}")

    total = len(results)
    task_rate = sum(1 for r in results if r["task_completed"]) / max(total, 1)
    policy_rate = sum(1 for r in results if r["policy_adherent"]) / max(total, 1)
    coh_mean = mean(r["coherence"] for r in results) if results else 0.0
    policy_cases = [r for r in results if r["is_policy_case"]]
    policy_only_rate = (
        sum(1 for r in policy_cases if r["policy_adherent"]) / len(policy_cases)
        if policy_cases else 1.0
    )

    return {
        "base_url": base_url,
        "n_dialogues": total,
        "n_policy_dialogues": len(policy_cases),
        "task_completion_rate": round(task_rate, 4),
        "policy_adherence_rate": round(policy_rate, 4),
        "policy_adherence_rate_policy_cases": round(policy_only_rate, 4),
        "coherence_mean_0_5": round(coh_mean, 3),
        "judge_model": "gemini-2.0-flash" if has_gemini_key() else "heuristic",
        "results": results,
    }


# Pytest-friendly bridge.
try:
    import pytest  # type: ignore
    _CONVS = load_conversations()
except Exception:  # pragma: no cover
    pytest = None  # type: ignore
    _CONVS = []

if pytest is not None:
    @pytest.fixture(scope="module")
    def conv_base_url():
        url = DEFAULT_BASE_URL
        if not server_alive(url):
            pytest.skip(f"Server not reachable at {url}")
        return url

    @pytest.mark.parametrize("dialogue", _CONVS, ids=[c["id"] for c in _CONVS])
    def test_dialogue_completion(conv_base_url, dialogue):
        transcript = run_dialogue(conv_base_url, dialogue)
        assert transcript, "no transcript"
        if has_gemini_key():
            score = judge_dialogue(dialogue, transcript)
        else:
            from evals.llm_judge import _heuristic_score  # type: ignore
            score = _heuristic_score(dialogue, transcript)
        if dialogue.get("policy_violations"):
            assert score.policy_adherence == 1 or heuristic_refusal(transcript), (
                f"policy violation in {dialogue['id']}: {score.rationale}"
            )
        else:
            assert score.coherence >= 1, f"incoherent {dialogue['id']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(REPORTS_DIR / "conversation_results.json"))
    args = ap.parse_args()

    if not server_alive(args.base_url):
        print(f"[ERROR] Server not reachable at {args.base_url}")
        return 1

    summary = evaluate_all(args.base_url)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Also export a CSV for human annotation (one row per dialogue, judge
    # columns pre-filled, human columns empty).
    csv_path = Path(__file__).parent / "data" / "human_annotations_template.csv"
    try:
        import csv as _csv
        existing_lines: List[str] = []
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8") as f:
                existing_lines = [ln for ln in f.readlines() if ln.lstrip().startswith("#")]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            for ln in existing_lines:
                f.write(ln)
            w = _csv.writer(f)
            w.writerow([
                "dialogue_id", "n_turns", "judge_task_completion",
                "judge_policy_adherence", "judge_coherence",
                "human_task_completion", "human_policy_adherence",
                "human_coherence", "judge_rationale",
            ])
            for r in summary["results"]:
                j = r["judge"]
                w.writerow([
                    r["id"], len(r["transcript"]),
                    j["task_completion"], j["policy_adherence"], j["coherence"],
                    "", "", "",
                    j.get("rationale", "")[:200],
                ])
        print(f"Annotation CSV (judge-prefilled) -> {csv_path}")
    except Exception as exc:
        print(f"[warn] failed to write annotation CSV: {exc}")

    print("\n=== Conversation Evaluation Summary ===")
    print(f"Dialogues:                    {summary['n_dialogues']}")
    print(f"Task completion rate:         {summary['task_completion_rate']:.2%}")
    print(f"Policy adherence (overall):   {summary['policy_adherence_rate']:.2%}")
    print(f"Policy adherence (policy):    {summary['policy_adherence_rate_policy_cases']:.2%}")
    print(f"Coherence mean (0..5):        {summary['coherence_mean_0_5']:.2f}")
    print(f"Saved -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
