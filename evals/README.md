# DentaBot Evaluation Suite

Comprehensive evaluation framework for the DentaBot conversational AI system.

## Frameworks Used

| Framework | Purpose |
|-----------|---------|
| **pytest** | Unit and integration tests |
| **RAGAS** | RAG evaluation (retrieval relevance, faithfulness, context relevance) |
| **DeepEval** | LLM output evaluation (custom metrics, hallucination detection) |
| **LangSmith** | Tracing and evaluation |
| **Locust** | Load testing |

## Quick Start

```bash
# Install dependencies
pip install pytest pytest-html ragas datasets websockets psutil locust deepeval langsmith

# Run all tests (with server running)
python evals/run_evals.py

# Run quick mode (fewer trials)
python evals/run_evals.py --quick

# Run only unit tests (no server needed)
pytest evals/ -v --ignore=evals/benchmark_latency.py --ignore=evals/benchmark_throughput.py
```

## Structure

```
evals/
├── run_evals.py              # Main runner script
├── conftest.py               # Pytest fixtures
├── test_rag_ragas.py         # RAG evaluation (RAGAS metrics)
├── test_deepeval.py          # DeepEval LLM evaluation
├── test_tools_crm.py         # CRM tool unit tests
├── test_tools_appointment.py # Appointment tool unit tests
├── test_tools_weather.py     # Weather tool unit tests
├── test_tools_cost.py        # DentalCost tool unit tests
├── test_conversation.py      # Conversation correctness tests
├── locustfile.py             # Locust load testing
├── langsmith_eval.py         # LangSmith evaluation
├── data/
│   ├── rag_ground_truth.json # 30 annotated RAG queries
│   └── conversations.json    # 15 multi-turn test dialogues
└── reports/
    ├── evaluation_results.json
    └── EVALUATION_REPORT.md
```

## Evaluation Components

### 1. RAG Evaluation

**Metrics:**
- **Precision@k**: Fraction of retrieved chunks that are relevant
- **Recall@k**: Fraction of relevant chunks that were retrieved  
- **Hit Rate**: Queries where at least one relevant chunk was found
- **Faithfulness** (RAGAS): Is the answer grounded in retrieved context?
- **Context Relevance** (RAGAS): Are retrieved chunks useful?

**Run:**
```bash
# Basic metrics (no API key needed)
python evals/test_rag_ragas.py

# Full RAGAS evaluation (requires OpenAI)
export OPENAI_API_KEY=sk-...
pytest evals/test_rag_ragas.py -v
```

### 2. Tool Unit Tests

Tests CRUD operations and functional correctness for all tools.

| Tool | Tests |
|------|-------|
| CRM | Create, Read, Update, persistence, edge cases |
| Appointment | Get slots, book, cancel, collision handling |
| Weather | API response, error handling, mocked tests |
| DentalCost | Known/unknown procedures, price ranges |

**Run:**
```bash
pytest evals/test_tools_*.py -v
```

### 3. Conversation Evaluation

**Metrics:**
- **Task Completion Rate**: Did the bot fulfill the user's request?
- **Policy Adherence**: Does the bot refuse out-of-scope requests?
- **Coherence**: Does the bot maintain context across turns?

**Run:**
```bash
pytest evals/test_conversation.py -v
```

### 4. Load Testing with Locust

**Framework:** Locust (https://locust.io)

**Metrics:**
- **Requests per second**: Throughput under load
- **Response times**: 50th, 90th, 95th percentiles
- **Failure rate**: Percentage of failed requests
- **User count**: Concurrent users supported

**Run:**

```bash
# Start server first
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run Locust with Web UI (http://localhost:8089)
locust -f evals/locustfile.py --host=ws://localhost:8000

# Run Locust headless (no UI)
locust -f evals/locustfile.py --host=ws://localhost:8000 --headless -u 10 -r 2 -t 60s
# -u 10: 10 users
# -r 2: spawn 2 users/second
# -t 60s: run for 60 seconds
```

### 5. LLM Output Evaluation with DeepEval

**Framework:** DeepEval (https://deepeval.com)

**Metrics:**
- **Answer Relevancy**: Is the response relevant to the question?
- **Faithfulness**: Is the response grounded in retrieved context?
- **Hallucination**: Does the response contain made-up information?
- **Custom GEval**: Policy adherence, helpfulness

**Requirements:**
```bash
pip install deepeval
export OPENAI_API_KEY=sk-...  # Required for LLM-based metrics
```

**Run:**
```bash
# With pytest
pytest evals/test_deepeval.py -v

# With DeepEval CLI
deepeval test run evals/test_deepeval.py
```

### 6. Tracing with LangSmith

**Framework:** LangSmith (https://smith.langchain.com)

**Features:**
- **Tracing**: See all LLM calls with inputs/outputs
- **Evaluation Datasets**: Upload test cases
- **Experiments**: Compare different configurations

**Setup:**
```bash
pip install langsmith

# Set environment variables
$env:LANGCHAIN_API_KEY = "ls__..."  # From https://smith.langchain.com
$env:LANGCHAIN_TRACING_V2 = "true"
$env:LANGCHAIN_PROJECT = "dentabot-eval"
```

**Run:**
```bash
python evals/langsmith_eval.py
```

## Interpreting Results

### Good Performance Targets

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| RAG Hit Rate | >0.8 | 0.6-0.8 | <0.6 |
| RAG Precision@3 | >0.5 | 0.3-0.5 | <0.3 |
| TTFT (simple) | <500ms | 500-2000ms | >2000ms |
| Concurrency | >5 users | 2-5 users | <2 users |
| Tool Tests | 100% pass | >90% pass | <90% pass |

### Understanding RAG Metrics

- **High Precision, Low Recall**: Retriever is too conservative
- **Low Precision, High Recall**: Retriever returns too many irrelevant chunks
- **Low Faithfulness**: LLM is hallucinating beyond retrieved context

### Understanding Latency

- **High TTFT**: Model loading or slow retrieval
- **High Inter-token**: Model inference bottleneck
- **TTFT degrades with concurrency**: CPU/GPU saturation

## Configuration

### Environment Variables

```bash
# Server URL (for benchmarks)
export DENTABOT_WS_URL=ws://localhost:8000/ws/chat

# LLM model path
export DENTABOT_MODEL_PATH=models/qwen2.5-1.5b-instruct-q4_k_m.gguf

# For RAGAS full evaluation
export OPENAI_API_KEY=sk-...
```

### Customizing Benchmarks

Edit constants in benchmark files:
```python
# benchmark_latency.py
NUM_TRIALS = 30  # Trials per scenario

# benchmark_throughput.py
CONCURRENCY_LEVELS = [1, 2, 3, 5, 8, 10, 15, 20]
TTFT_THRESHOLD_MS = 2000
TOTAL_THRESHOLD_MS = 10000
```

## Generated Reports

After running `python evals/run_evals.py`:

- **reports/evaluation_results.json**: Raw metrics data
- **reports/EVALUATION_REPORT.md**: Human-readable report
- **reports/latency_results.json**: Detailed latency data
- **reports/throughput_results.json**: Throughput data

## Adding New Tests

### New RAG Query
Add to `data/rag_ground_truth.json`:
```json
{
  "question": "Your question here",
  "ground_truth": "Expected answer",
  "relevant_docs": ["document_filename.md"]
}
```

### New Conversation Test
Add to `data/conversations.json`:
```json
{
  "id": "unique_id",
  "description": "What this tests",
  "expected_outcome": "outcome_type",
  "turns": [
    {"user": "User message", "expected_intent": "intent"}
  ]
}
```

## Troubleshooting

### "Connection refused" in benchmarks
Start the server: `uvicorn app.main:app --port 8000`

### RAG tests fail with empty results
Initialize the vector DB: `python -c "from app.RAG import retrieve_relevant_chunks; retrieve_relevant_chunks('test')"`

### RAGAS tests skipped
Set `OPENAI_API_KEY` environment variable

### Import errors
Ensure you're in the project root and venv is activated
