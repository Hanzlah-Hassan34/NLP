"""
RAG Evaluation — basic retrieval metrics (no LLM) plus full RAGAS metrics
(faithfulness, answer relevancy, context precision/recall) using Gemini 2.0
Flash as the judge LLM.

Two modes:
  1. Basic metrics only (fast, no API key) — Precision@k, Recall@k, Hit-rate.
  2. Full RAGAS — drives the live server to generate answers, then scores
     them against retrieved context.

Usage:
    pytest evals/test_rag_ragas.py -v
    python evals/test_rag_ragas.py --mode basic
    python evals/test_rag_ragas.py --mode full --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from app.RAG import retrieve_relevant_chunks  # noqa: E402

DATA_PATH = Path(__file__).parent / "data" / "rag_ground_truth.json"
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_URL = os.getenv("DENTABOT_BASE_URL", "http://localhost:8000")
TOP_K = 3


# ─── Data loading ────────────────────────────────────────────────────────────
def load_ground_truth() -> List[Dict[str, Any]]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def has_gemini() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY"))


# ─── Basic retrieval metrics (no LLM) ────────────────────────────────────────
def compute_basic_retrieval_metrics(data: List[Dict[str, Any]], top_k: int = TOP_K) -> Dict[str, Any]:
    results = []
    for item in data:
        question = item["question"]
        expected_docs = set(item["relevant_docs"])
        chunks = retrieve_relevant_chunks(question, top_k=top_k)

        retrieved_sources: set[str] = set()
        for chunk in chunks:
            for doc in expected_docs:
                doc_words = doc.replace(".md", "").replace("_", " ").lower().split()[:3]
                if any(w in chunk.lower() for w in doc_words):
                    retrieved_sources.add(doc)

        recall = len(retrieved_sources & expected_docs) / len(expected_docs) if expected_docs else 0.0
        precision = len(retrieved_sources & expected_docs) / top_k if top_k else 0.0
        results.append({
            "question": question,
            "expected_docs": list(expected_docs),
            "matched_docs": list(retrieved_sources),
            "precision": precision,
            "recall": recall,
            "hit": len(retrieved_sources & expected_docs) > 0,
        })

    return {
        "precision@k": round(sum(r["precision"] for r in results) / max(len(results), 1), 4),
        "recall@k": round(sum(r["recall"] for r in results) / max(len(results), 1), 4),
        "hit_rate": round(sum(r["hit"] for r in results) / max(len(results), 1), 4),
        "total_queries": len(results),
        "top_k": top_k,
        "details": results,
    }


# ─── Full RAGAS metrics ──────────────────────────────────────────────────────
def _server_alive(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url}/healthz", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _generate_answer(base_url: str, question: str, timeout: int = 180) -> str:
    sid = f"rag-{uuid.uuid4().hex[:8]}"
    try:
        requests.post(f"{base_url}/v1/eval/reset",
                      json={"session_id": sid}, timeout=10)
    except Exception:
        pass
    try:
        r = requests.post(
            f"{base_url}/v1/eval/chat",
            json={"session_id": sid, "message": question},
            timeout=timeout,
        )
        if r.ok:
            return (r.json().get("reply") or "").strip()
    except Exception as exc:
        return f"[error: {exc}]"
    return ""


def _build_ragas_dataset(
    data: List[Dict[str, Any]],
    base_url: Optional[str],
    top_k: int = TOP_K,
    max_items: int = 30,
) -> Dict[str, List[Any]]:
    questions: List[str] = []
    contexts: List[List[str]] = []
    answers: List[str] = []
    ground_truths: List[str] = []
    use_live = bool(base_url and _server_alive(base_url))
    print(f"[RAGAS] live server={'YES' if use_live else 'no'} (using ground_truth as answer otherwise)")

    for item in data[:max_items]:
        q = item["question"]
        chunks = retrieve_relevant_chunks(q, top_k=top_k) or [""]
        if use_live:
            t0 = time.perf_counter()
            ans = _generate_answer(base_url, q)
            print(f"  [{len(answers)+1}/{min(len(data), max_items)}] answered in {time.perf_counter()-t0:.1f}s")
        else:
            ans = item.get("ground_truth", "")
        questions.append(q)
        contexts.append(chunks)
        answers.append(ans or "(no answer)")
        ground_truths.append(item.get("ground_truth", ""))
    return {
        "question": questions,
        "contexts": contexts,
        "answer": answers,
        "ground_truth": ground_truths,
    }


def run_ragas_full(
    data: List[Dict[str, Any]],
    base_url: Optional[str] = None,
    top_k: int = TOP_K,
    max_items: int = 30,
) -> Optional[Dict[str, Any]]:
    if not has_gemini():
        print("[RAGAS] GOOGLE_API_KEY not set — skipping full RAGAS run.")
        return None
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
    except Exception as exc:
        print(f"[RAGAS] import failed ({exc}); install ragas, datasets, "
              "langchain-google-genai")
        return None

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash",
                                 google_api_key=os.getenv("GOOGLE_API_KEY"))
    try:
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
    except Exception:
        embeddings = None

    payload = _build_ragas_dataset(data, base_url, top_k=top_k, max_items=max_items)
    ds = Dataset.from_dict(payload)
    metrics = [context_precision, context_recall, faithfulness, answer_relevancy]
    try:
        kwargs: Dict[str, Any] = {"llm": llm}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        result = evaluate(ds, metrics=metrics, **kwargs)
    except Exception as exc:
        print(f"[RAGAS] evaluation failed: {exc}")
        return None

    def get(key: str) -> float:
        try:
            return float(result[key])
        except Exception:
            try:
                return float(result.to_pandas()[key].mean())  # type: ignore
            except Exception:
                return float("nan")

    return {
        "n_items": len(payload["question"]),
        "context_precision": round(get("context_precision"), 4),
        "context_recall": round(get("context_recall"), 4),
        "faithfulness": round(get("faithfulness"), 4),
        "answer_relevancy": round(get("answer_relevancy"), 4),
        "items": [
            {"question": q, "answer": a[:200], "n_chunks": len(c)}
            for q, c, a in zip(payload["question"], payload["contexts"], payload["answer"])
        ],
    }


# ─── pytest tests ────────────────────────────────────────────────────────────
import pytest  # noqa: E402


class TestRAGRetrieval:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.data = load_ground_truth()

    def test_basic_metrics_meets_thresholds(self):
        m = compute_basic_retrieval_metrics(self.data, TOP_K)
        assert m["hit_rate"] >= 0.5, f"hit_rate={m['hit_rate']}"

    def test_no_empty_retrievals(self):
        empties = [it["question"] for it in self.data
                   if not retrieve_relevant_chunks(it["question"], top_k=TOP_K)]
        assert not empties, f"empty retrievals: {empties}"


# ─── CLI ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["basic", "full"], default="basic")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--max-items", type=int, default=30)
    ap.add_argument("--out", default=str(REPORTS_DIR / "rag_results.json"))
    args = ap.parse_args()

    data = load_ground_truth()
    print(f"[RAG] Loaded {len(data)} ground-truth queries")

    output: Dict[str, Any] = {}
    output["basic"] = compute_basic_retrieval_metrics(data, top_k=args.top_k)
    print(f"[RAG] basic: P@{args.top_k}={output['basic']['precision@k']} "
          f"R@{args.top_k}={output['basic']['recall@k']} "
          f"hit={output['basic']['hit_rate']}")

    if args.mode == "full":
        ragas_out = run_ragas_full(
            data,
            base_url=args.base_url,
            top_k=args.top_k,
            max_items=args.max_items,
        )
        output["ragas"] = ragas_out

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Saved -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
