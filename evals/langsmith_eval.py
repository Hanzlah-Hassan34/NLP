"""
LangSmith Integration for DentaBot Evaluation.

LangSmith provides:
- Tracing of LLM calls
- Evaluation datasets
- Automated evaluation runs

Setup:
    1. Create account at https://smith.langchain.com
    2. Get API key from Settings
    3. Set environment variables:
       $env:LANGCHAIN_API_KEY = "ls__..."
       $env:LANGCHAIN_TRACING_V2 = "true"
       $env:LANGCHAIN_PROJECT = "dentabot-eval"

Run:
    python evals/langsmith_eval.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))

# Check for LangSmith
try:
    from langsmith import Client
    from langsmith.evaluation import evaluate
    from langsmith.schemas import Run, Example
    LANGSMITH_AVAILABLE = True
except ImportError as e:
    LANGSMITH_AVAILABLE = False
    print(f"LangSmith import error: {e}")
    # Dummy types for when LangSmith is not available
    Run = object
    Example = object


# ════════════════════════════════════════════════════════════════════════════
# Configuration
# ════════════════════════════════════════════════════════════════════════════

DATA_PATH = Path(__file__).parent / "data" / "rag_ground_truth.json"
DATASET_NAME = "dentabot-rag-eval"


def load_ground_truth():
    """Load ground truth data."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ════════════════════════════════════════════════════════════════════════════
# LangSmith Dataset Creation
# ════════════════════════════════════════════════════════════════════════════

def create_evaluation_dataset():
    """Create or update LangSmith evaluation dataset."""
    if not LANGSMITH_AVAILABLE:
        print("LangSmith not available")
        return None
    
    if not os.getenv("LANGCHAIN_API_KEY"):
        print("Set LANGCHAIN_API_KEY to use LangSmith")
        return None
    
    client = Client()
    
    # Check if dataset exists
    try:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        print(f"Dataset '{DATASET_NAME}' already exists")
        return dataset
    except:
        pass
    
    # Create new dataset
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="DentaBot RAG evaluation queries with ground truth"
    )
    
    # Add examples
    ground_truth = load_ground_truth()
    
    for item in ground_truth:
        client.create_example(
            inputs={"question": item["question"]},
            outputs={"answer": item["ground_truth"]},
            metadata={"relevant_docs": item["relevant_docs"]},
            dataset_id=dataset.id
        )
    
    print(f"Created dataset '{DATASET_NAME}' with {len(ground_truth)} examples")
    return dataset


# ════════════════════════════════════════════════════════════════════════════
# Target Function (Your RAG System)
# ════════════════════════════════════════════════════════════════════════════

def dentabot_rag_chain(inputs: dict) -> dict:
    """
    Target function that LangSmith will evaluate.
    This calls your RAG system.
    """
    from app.RAG import retrieve_relevant_chunks
    
    question = inputs["question"]
    
    # Retrieve context
    chunks = retrieve_relevant_chunks(question, top_k=3)
    context = "\n".join(chunks)
    
    # In a full implementation, you'd call your LLM here
    # For now, return context as the "answer" for retrieval evaluation
    return {
        "answer": context,
        "context": chunks
    }


# ════════════════════════════════════════════════════════════════════════════
# Custom Evaluators
# ════════════════════════════════════════════════════════════════════════════

def context_recall_evaluator(run: Run, example: Example) -> dict:
    """
    Custom evaluator: Check if relevant docs were retrieved.
    """
    # Get expected relevant docs
    expected_docs = example.metadata.get("relevant_docs", [])
    
    # Get actual retrieved context
    actual_context = run.outputs.get("context", [])
    
    # Check if any expected doc content appears in context
    hits = 0
    for doc in expected_docs:
        doc_name = doc.replace(".md", "").replace("_", " ").lower()
        for chunk in actual_context:
            if any(word in chunk.lower() for word in doc_name.split()[:3]):
                hits += 1
                break
    
    recall = hits / len(expected_docs) if expected_docs else 0
    
    return {
        "key": "context_recall",
        "score": recall,
        "comment": f"Retrieved {hits}/{len(expected_docs)} relevant docs"
    }


def answer_contains_info_evaluator(run: Run, example: Example) -> dict:
    """
    Custom evaluator: Check if answer contains expected information.
    """
    expected = example.outputs.get("answer", "").lower()
    actual = run.outputs.get("answer", "").lower()
    
    # Simple keyword matching
    expected_words = set(expected.split())
    actual_words = set(actual.split())
    
    overlap = len(expected_words & actual_words)
    score = overlap / len(expected_words) if expected_words else 0
    
    return {
        "key": "info_coverage",
        "score": min(score, 1.0),
        "comment": f"Matched {overlap} keywords"
    }


# ════════════════════════════════════════════════════════════════════════════
# Run Evaluation
# ════════════════════════════════════════════════════════════════════════════

def run_langsmith_evaluation():
    """Run evaluation using LangSmith."""
    if not LANGSMITH_AVAILABLE:
        print("LangSmith not available")
        return None
    
    if not os.getenv("LANGCHAIN_API_KEY"):
        print("Set LANGCHAIN_API_KEY to use LangSmith")
        print("Example: $env:LANGCHAIN_API_KEY = 'ls__...'")
        return None
    
    # Enable tracing
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = "dentabot-eval"
    
    # Create dataset if needed
    create_evaluation_dataset()
    
    print("\n" + "="*60)
    print("RUNNING LANGSMITH EVALUATION")
    print("="*60)
    
    # Run evaluation
    results = evaluate(
        dentabot_rag_chain,
        data=DATASET_NAME,
        evaluators=[
            context_recall_evaluator,
            answer_contains_info_evaluator,
        ],
        experiment_prefix="dentabot-rag",
        metadata={
            "version": "1.0",
            "timestamp": datetime.now().isoformat()
        }
    )
    
    print("\n" + "="*60)
    print("LANGSMITH EVALUATION COMPLETE")
    print("="*60)
    print(f"View results at: https://smith.langchain.com")
    
    return results


# ════════════════════════════════════════════════════════════════════════════
# Tracing Wrapper
# ════════════════════════════════════════════════════════════════════════════

def enable_langsmith_tracing():
    """
    Enable LangSmith tracing for your application.
    Call this at startup to trace all LLM calls.
    """
    if not os.getenv("LANGCHAIN_API_KEY"):
        print("LangSmith tracing disabled (no API key)")
        return False
    
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = "dentabot"
    
    print("LangSmith tracing enabled")
    print("View traces at: https://smith.langchain.com")
    return True


# ════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("LangSmith Evaluation for DentaBot")
    print("-" * 40)
    
    if not os.getenv("LANGCHAIN_API_KEY"):
        print("\nTo use LangSmith:")
        print("1. Sign up at https://smith.langchain.com")
        print("2. Get API key from Settings")
        print("3. Set: $env:LANGCHAIN_API_KEY = 'ls__...'")
        print("4. Run this script again")
    else:
        run_langsmith_evaluation()
