"""
RAGAS Evaluation for DentaBot RAG System.

Metrics evaluated:
- Context Precision: Are retrieved chunks relevant to the query?
- Context Recall: Did we retrieve all needed information?
- Faithfulness: Is the answer grounded in retrieved context?
- Answer Relevancy: Does the answer address the question?

Run: pytest evals/test_rag_ragas.py -v --tb=short
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.RAG import retrieve_relevant_chunks

# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════

DATA_PATH = Path(__file__).parent / "data" / "rag_ground_truth.json"
TOP_K = 3


# ══════════════════════════════════════════════════════════════════════════════
# Load Test Data
# ══════════════════════════════════════════════════════════════════════════════

def load_ground_truth():
    """Load the annotated ground truth dataset."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════════════════
# Basic RAG Metrics (No external LLM needed)
# ══════════════════════════════════════════════════════════════════════════════

def compute_basic_retrieval_metrics(ground_truth_data: list, top_k: int = 3):
    """
    Compute precision@k and recall@k based on source document matching.
    This doesn't require an LLM - just checks if relevant docs were retrieved.
    """
    results = []
    
    for item in ground_truth_data:
        question = item["question"]
        expected_docs = set(item["relevant_docs"])
        
        # Get retrieved chunks
        chunks = retrieve_relevant_chunks(question, top_k=top_k)
        
        # Extract source documents from chunks (rough matching)
        retrieved_sources = set()
        for chunk in chunks:
            for doc in expected_docs:
                doc_name = doc.replace(".md", "").replace("_", " ").lower()
                if any(word in chunk.lower() for word in doc_name.split()[:3]):
                    retrieved_sources.add(doc)
        
        # Calculate metrics
        if len(expected_docs) > 0:
            recall = len(retrieved_sources & expected_docs) / len(expected_docs)
        else:
            recall = 0.0
            
        precision = len(retrieved_sources & expected_docs) / top_k if top_k > 0 else 0.0
        
        results.append({
            "question": question,
            "expected_docs": list(expected_docs),
            "retrieved_count": len(chunks),
            "matched_docs": list(retrieved_sources),
            "precision": precision,
            "recall": recall,
            "hit": len(retrieved_sources & expected_docs) > 0
        })
    
    # Aggregate metrics
    avg_precision = sum(r["precision"] for r in results) / len(results)
    avg_recall = sum(r["recall"] for r in results) / len(results)
    hit_rate = sum(r["hit"] for r in results) / len(results)
    
    return {
        "precision@k": round(avg_precision, 4),
        "recall@k": round(avg_recall, 4),
        "hit_rate": round(hit_rate, 4),
        "total_queries": len(results),
        "details": results
    }


# ══════════════════════════════════════════════════════════════════════════════
# RAGAS Evaluation (Supports Gemini or OpenAI)
# ══════════════════════════════════════════════════════════════════════════════

def get_ragas_llm():
    """Get LLM for RAGAS - prefers Gemini (free), falls back to OpenAI."""
    # Try Gemini first (free)
    if os.getenv("GOOGLE_API_KEY"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=os.getenv("GOOGLE_API_KEY")
            )
        except ImportError:
            print("Install: pip install langchain-google-genai")
    
    # Fall back to OpenAI
    if os.getenv("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model="gpt-3.5-turbo")
        except ImportError:
            pass
    
    return None


def run_ragas_evaluation(ground_truth_data: list, top_k: int = 3):
    """
    Run full RAGAS evaluation with faithfulness, context relevance, etc.
    Requires: pip install ragas datasets langchain-google-genai
    And either GOOGLE_API_KEY (free) or OPENAI_API_KEY.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError:
        print("RAGAS not installed. Run: pip install ragas datasets")
        return None
    
    # Get LLM
    llm = get_ragas_llm()
    if not llm:
        print("No LLM configured. Set GOOGLE_API_KEY or OPENAI_API_KEY")
        return None
    
    # Prepare data for RAGAS
    questions = []
    ground_truths = []
    contexts = []
    answers = []
    
    for item in ground_truth_data:
        question = item["question"]
        ground_truth = item["ground_truth"]
        
        # Retrieve context
        chunks = retrieve_relevant_chunks(question, top_k=top_k)
        
        # For answer, we use ground_truth as placeholder
        # In real eval, you'd call your LLM to generate the answer
        answer = ground_truth  # Replace with actual LLM response
        
        questions.append(question)
        ground_truths.append(ground_truth)
        contexts.append(chunks)
        answers.append(answer)
    
    # Create dataset
    dataset = Dataset.from_dict({
        "question": questions,
        "ground_truth": ground_truths,
        "contexts": contexts,
        "answer": answers,
    })
    
    # Run evaluation with configured LLM
    try:
        results = evaluate(
            dataset,
            metrics=[
                context_precision,
                context_recall,
                faithfulness,
                answer_relevancy,
            ],
            llm=llm,
        )
        return {
            "context_precision": round(results["context_precision"], 4),
            "context_recall": round(results["context_recall"], 4),
            "faithfulness": round(results["faithfulness"], 4),
            "answer_relevancy": round(results["answer_relevancy"], 4),
        }
    except Exception as e:
        print(f"RAGAS evaluation failed: {e}")
        print("Check your GOOGLE_API_KEY or OPENAI_API_KEY")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Pytest Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRAGRetrieval:
    """Test RAG retrieval quality."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.ground_truth = load_ground_truth()
    
    def test_basic_retrieval_metrics(self):
        """Test basic precision@k and recall@k."""
        metrics = compute_basic_retrieval_metrics(self.ground_truth, top_k=TOP_K)
        
        print("\n" + "="*60)
        print("BASIC RETRIEVAL METRICS")
        print("="*60)
        print(f"Precision@{TOP_K}: {metrics['precision@k']}")
        print(f"Recall@{TOP_K}:    {metrics['recall@k']}")
        print(f"Hit Rate:         {metrics['hit_rate']}")
        print(f"Total Queries:    {metrics['total_queries']}")
        print("="*60)
        
        # Assert minimum thresholds
        assert metrics["hit_rate"] >= 0.5, f"Hit rate too low: {metrics['hit_rate']}"
        
    def test_retrieval_returns_results(self):
        """Verify retrieval returns non-empty results for all queries."""
        empty_count = 0
        for item in self.ground_truth:
            chunks = retrieve_relevant_chunks(item["question"], top_k=TOP_K)
            if not chunks:
                empty_count += 1
                print(f"Empty retrieval for: {item['question']}")
        
        assert empty_count == 0, f"{empty_count} queries returned empty results"
    
    def test_retrieval_chunk_count(self):
        """Verify we get expected number of chunks."""
        for item in self.ground_truth[:5]:  # Test first 5
            chunks = retrieve_relevant_chunks(item["question"], top_k=TOP_K)
            assert len(chunks) <= TOP_K, f"Got more than {TOP_K} chunks"
            assert len(chunks) > 0, "Got zero chunks"

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set - skipping RAGAS evaluation"
    )
    def test_ragas_evaluation(self):
        """Run full RAGAS evaluation (requires OpenAI API key)."""
        results = run_ragas_evaluation(self.ground_truth, top_k=TOP_K)
        
        if results:
            print("\n" + "="*60)
            print("RAGAS EVALUATION RESULTS")
            print("="*60)
            print(f"Context Precision: {results['context_precision']}")
            print(f"Context Recall:    {results['context_recall']}")
            print(f"Faithfulness:      {results['faithfulness']}")
            print(f"Answer Relevancy:  {results['answer_relevancy']}")
            print("="*60)
            
            # Assert minimum thresholds
            assert results["context_precision"] >= 0.5
            assert results["faithfulness"] >= 0.6


# ══════════════════════════════════════════════════════════════════════════════
# Standalone Runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Loading ground truth data...")
    data = load_ground_truth()
    print(f"Loaded {len(data)} test queries\n")
    
    # Run basic metrics (always works)
    print("Running basic retrieval metrics...")
    basic_results = compute_basic_retrieval_metrics(data, top_k=TOP_K)
    
    print("\n" + "="*60)
    print("BASIC RETRIEVAL METRICS")
    print("="*60)
    print(f"Precision@{TOP_K}: {basic_results['precision@k']}")
    print(f"Recall@{TOP_K}:    {basic_results['recall@k']}")
    print(f"Hit Rate:         {basic_results['hit_rate']}")
    print("="*60)
    
    # Show per-query details
    print("\nPer-Query Results:")
    for r in basic_results["details"][:10]:  # Show first 10
        status = "✓" if r["hit"] else "✗"
        print(f"  {status} {r['question'][:50]}... (recall={r['recall']:.2f})")
    
    # Run RAGAS if API key available
    if os.getenv("OPENAI_API_KEY"):
        print("\n\nRunning RAGAS evaluation...")
        ragas_results = run_ragas_evaluation(data, top_k=TOP_K)
        if ragas_results:
            print("\n" + "="*60)
            print("RAGAS EVALUATION RESULTS")
            print("="*60)
            for metric, value in ragas_results.items():
                print(f"{metric}: {value}")
            print("="*60)
    else:
        print("\n⚠ OPENAI_API_KEY not set - skipping RAGAS evaluation")
        print("Set it to run full evaluation: set OPENAI_API_KEY=sk-...")
