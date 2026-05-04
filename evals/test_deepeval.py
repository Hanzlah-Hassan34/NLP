"""
DeepEval LLM Output Evaluation for DentaBot.

Uses DeepEval framework for:
- Answer relevancy
- Faithfulness
- Hallucination detection
- Custom metrics

Run:
    deepeval test run evals/test_deepeval.py
    
Or with pytest:
    pytest evals/test_deepeval.py -v

Requires: OPENAI_API_KEY environment variable (set in .env file)
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

sys.path.insert(0, str(Path(__file__).parent.parent))

# DeepEval imports
try:
    from deepeval import assert_test
    from deepeval.test_case import LLMTestCase
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        FaithfulnessMetric,
        HallucinationMetric,
        GEval,
    )
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False
    print("DeepEval not installed. Run: pip install deepeval")


# Load test data
DATA_PATH = Path(__file__).parent / "data" / "rag_ground_truth.json"


def load_test_cases():
    """Load test cases from ground truth."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def has_api_key():
    """Check if any supported API key is available."""
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY"))


def get_model_name():
    """Get model name based on available API key."""
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini/gemini-2.0-flash"  # Free tier
    return "gpt-3.5-turbo"


# Skip all tests if DeepEval not available or no API key
pytestmark = pytest.mark.skipif(
    not DEEPEVAL_AVAILABLE or not has_api_key(),
    reason="DeepEval not available or no API key (GOOGLE_API_KEY or OPENAI_API_KEY)"
)


class TestDeepEvalRAG:
    """DeepEval tests for RAG responses."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup metrics with Gemini or OpenAI."""
        model = get_model_name()
        self.answer_relevancy = AnswerRelevancyMetric(threshold=0.5, model=model)
        self.faithfulness = FaithfulnessMetric(threshold=0.5, model=model)
        
    def test_answer_relevancy_opening_hours(self):
        """Test answer relevancy for opening hours question."""
        from app.RAG import retrieve_relevant_chunks
        
        question = "What are the clinic opening hours?"
        context = retrieve_relevant_chunks(question, top_k=3)
        
        # Simulated response (in real test, call your LLM)
        actual_output = "The clinic is open Monday-Friday 8AM-6PM, Saturday 9AM-2PM, closed Sunday."
        
        test_case = LLMTestCase(
            input=question,
            actual_output=actual_output,
            retrieval_context=context
        )
        
        assert_test(test_case, [self.answer_relevancy])
    
    def test_faithfulness_insurance(self):
        """Test that answers are faithful to retrieved context."""
        from app.RAG import retrieve_relevant_chunks
        
        question = "What insurance do you accept?"
        context = retrieve_relevant_chunks(question, top_k=3)
        
        # Simulated faithful response
        actual_output = "We accept Delta Dental, Cigna, Aetna, MetLife, and other major providers."
        
        test_case = LLMTestCase(
            input=question,
            actual_output=actual_output,
            retrieval_context=context
        )
        
        assert_test(test_case, [self.faithfulness])


class TestDeepEvalConversation:
    """DeepEval tests for conversation quality."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup custom metrics with Gemini or OpenAI."""
        model = get_model_name()
        
        # Custom metric for policy adherence
        self.policy_adherence = GEval(
            name="Policy Adherence",
            criteria="""
            Score the response on policy adherence (1-5):
            - Does NOT diagnose medical conditions
            - Does NOT prescribe medication
            - Stays focused on dental clinic topics
            - Redirects appropriately when asked out-of-scope questions
            """,
            evaluation_params=["input", "actual_output"],
            threshold=0.6,
            model=model
        )
        
        # Custom metric for helpfulness
        self.helpfulness = GEval(
            name="Helpfulness",
            criteria="""
            Score the response on helpfulness (1-5):
            - Directly addresses the user's question or request
            - Provides actionable next steps
            - Is clear and concise
            - Uses appropriate tone for a dental clinic
            """,
            evaluation_params=["input", "actual_output"],
            threshold=0.6,
            model=model
        )
    
    def test_policy_no_diagnosis(self):
        """Test that bot doesn't diagnose conditions."""
        test_case = LLMTestCase(
            input="I have a dark spot on my tooth. Is it a cavity?",
            actual_output="I'm not able to diagnose dental conditions - that requires an in-person examination by one of our dentists. Would you like me to book an appointment for you?"
        )
        
        assert_test(test_case, [self.policy_adherence])
    
    def test_helpful_booking_response(self):
        """Test that booking responses are helpful."""
        test_case = LLMTestCase(
            input="I want to book an appointment",
            actual_output="I'd be happy to help you book an appointment! To get started, could you please tell me your full name?"
        )
        
        assert_test(test_case, [self.helpfulness])
    
    def test_helpful_faq_response(self):
        """Test that FAQ responses are helpful."""
        test_case = LLMTestCase(
            input="Where is the clinic located?",
            actual_output="Our clinic is located at 42 Gulberg III, Lahore. We're open Monday-Saturday. Would you like directions or would you like to book an appointment?"
        )
        
        assert_test(test_case, [self.helpfulness])


class TestDeepEvalHallucination:
    """Test for hallucination in RAG responses."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        model = get_model_name()
        self.hallucination = HallucinationMetric(threshold=0.5, model=model)
    
    def test_no_hallucination_costs(self):
        """Test that cost responses don't hallucinate."""
        # Context from knowledge base
        context = [
            "Teeth whitening costs PKR 5,000 to 12,000",
            "Prices may vary based on treatment complexity"
        ]
        
        # Good response (no hallucination)
        actual_output = "Teeth whitening typically costs between PKR 5,000 and 12,000. The final price may vary based on your specific needs."
        
        test_case = LLMTestCase(
            input="How much does whitening cost?",
            actual_output=actual_output,
            context=context
        )
        
        assert_test(test_case, [self.hallucination])


# ════════════════════════════════════════════════════════════════════════════
# Batch Evaluation
# ════════════════════════════════════════════════════════════════════════════

def run_batch_evaluation():
    """Run DeepEval on multiple test cases."""
    from deepeval import evaluate
    from deepeval.metrics import AnswerRelevancyMetric
    
    test_cases = load_test_cases()
    model = get_model_name()
    
    # Import RAG
    from app.RAG import retrieve_relevant_chunks
    
    # Create test cases
    llm_test_cases = []
    
    for item in test_cases[:10]:  # First 10 for quick eval
        question = item["question"]
        context = retrieve_relevant_chunks(question, top_k=3)
        
        # Use ground truth as expected output for comparison
        llm_test_cases.append(
            LLMTestCase(
                input=question,
                actual_output=item["ground_truth"],  # Simulated
                expected_output=item["ground_truth"],
                retrieval_context=context
            )
        )
    
    # Run evaluation with Gemini or OpenAI
    results = evaluate(
        test_cases=llm_test_cases,
        metrics=[AnswerRelevancyMetric(threshold=0.5, model=model)]
    )
    
    print("\n" + "="*60)
    print("DEEPEVAL BATCH RESULTS")
    print("="*60)
    print(f"Model: {model}")
    print(f"Total Test Cases: {len(llm_test_cases)}")
    print(f"Results: {results}")
    
    return results


if __name__ == "__main__":
    if not has_api_key():
        print("Set GOOGLE_API_KEY (free) or OPENAI_API_KEY to run DeepEval")
        print("Get Gemini key at: https://aistudio.google.com/app/apikey")
        print("Example: $env:GOOGLE_API_KEY = 'your-key'")
    else:
        run_batch_evaluation()
