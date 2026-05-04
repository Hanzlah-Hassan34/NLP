# DentaBot Evaluation Report

**Generated:** 2026-05-04 22:25

## Summary

| Component | Status |
|-----------|--------|
| pytest Unit Tests | **58 passed**, 1 skipped |
| RAG Retrieval | Precision: **0.41**, Recall: **1.0**, Hit Rate: **1.0** |
| Load Testing | HTTP: 5.3 req/s, 0% failures |
| DeepEval | Configured (requires API) |
| LangSmith | Configured (requires API) |

## Evaluation Frameworks Used

| Framework | Purpose | Status |
|-----------|---------|--------|
| **pytest** | Unit/Integration Tests | ✓ Working |
| **RAGAS** | RAG Evaluation | ✓ Basic metrics working |
| **Locust** | Load Testing | ✓ Working |
| **DeepEval** | LLM Output Evaluation | Configured (API required) |
| **LangSmith** | Tracing & Evaluation | Configured (API required) |

## RAG Evaluation Results

| Metric | Value | Interpretation |
|--------|-------|----------------|
| **Precision@3** | 0.4111 | ~41% of retrieved docs are relevant |
| **Recall@3** | 1.0 | 100% of relevant docs retrieved |
| **Hit Rate** | 1.0 | 100% queries have at least 1 relevant doc |
| **Total Queries** | 30 | Ground truth test cases |

**Interpretation:**
- **Excellent Recall (1.0)**: The RAG system always retrieves the relevant documents
- **Good Hit Rate (1.0)**: Every query gets at least one relevant result
- **Moderate Precision (0.41)**: Some irrelevant docs also retrieved (expected with top_k=3)

## pytest Results

| Test Suite | Passed | Skipped | Total |
|------------|--------|---------|-------|
| CRM Tool | 12 | 0 | 12 |
| Appointment Tool | 14 | 1 | 15 |
| Weather Tool | 9 | 0 | 9 |
| DentalCost Tool | 22 | 0 | 22 |
| **Total** | **58** | **1** | **59** |

### Test Categories:
- **CRM Tool**: Create, read, update patients; persistence; edge cases
- **Appointment Tool**: Get slots, book, cancel, collision handling
- **Weather Tool**: API response, error handling, mocked tests
- **DentalCost Tool**: Known/unknown procedures, price ranges, formatting

## Load Testing Results (Locust)

### HTTP Endpoint Test
```
Type     Name         # reqs  # fails |  Avg   Min   Max   Med | req/s
---------|------------|-------|--------|------|-----|-----|-----|------
GET      /               71  0(0.00%) |   4     2    84     3 |  5.30
```

- **Total Requests**: 71
- **Failure Rate**: 0%
- **Avg Response Time**: 4ms
- **Max Response Time**: 84ms
- **Throughput**: 5.3 requests/second

### WebSocket Test (with LLM)
- **Limitation**: Local LLM (Qwen 2.5 1.5B on CPU) can only handle 1 concurrent request
- **Response Time**: 25-26 seconds per LLM response
- **Expected**: Production would use GPU or API-based LLM

## Files Structure

```
evals/
├── test_tools_crm.py          # pytest - CRM tool tests (12 tests)
├── test_tools_appointment.py  # pytest - Appointment tests (15 tests)
├── test_tools_weather.py      # pytest - Weather tests (9 tests)
├── test_tools_cost.py         # pytest - Cost tests (22 tests)
├── test_conversation.py       # pytest - Conversation tests
├── test_rag_ragas.py          # RAGAS - RAG evaluation
├── test_deepeval.py           # DeepEval - LLM evaluation
├── locustfile.py              # Locust - Load testing
├── langsmith_eval.py          # LangSmith - Tracing
├── conftest.py                # Pytest fixtures
├── run_evals.py               # Main runner
└── data/
    ├── rag_ground_truth.json  # 30 annotated queries
    └── conversations.json     # 15 test dialogues
```

## API-Dependent Components

The following require API keys in `.env`:

### 1. DeepEval (`test_deepeval.py`)
- **Requires**: `GOOGLE_API_KEY` or `OPENAI_API_KEY`
- **Metrics**: Answer relevancy, faithfulness, hallucination detection
- **Tests**: 6 test cases defined

### 2. LangSmith (`langsmith_eval.py`)
- **Requires**: `LANGCHAIN_API_KEY`
- **Features**: Tracing, evaluation datasets, experiments

### 3. RAGAS Full Metrics (`test_rag_ragas.py`)
- **Requires**: `GOOGLE_API_KEY` or `OPENAI_API_KEY`
- **Metrics**: Faithfulness, answer relevancy, context precision/recall

## How to Run All Evaluations

```powershell
# 1. Start the DentaBot server
python -m uvicorn app.main:app --port 8000

# 2. Run pytest tool tests
python -m pytest evals/test_tools_*.py -v

# 3. Run RAG basic evaluation
python quick_eval.py

# 4. Run Locust HTTP load test
locust -f evals/locustfile.py --host=http://localhost:8000 --headless -u 5 -r 1 -t 30s

# 5. (Optional) Run DeepEval - requires API key
# Set GOOGLE_API_KEY in .env first
python -m pytest evals/test_deepeval.py -v

# 6. (Optional) Run LangSmith - requires API key
# Set LANGCHAIN_API_KEY in .env first
python evals/langsmith_eval.py
```

## Key Findings

1. **Tool Tests**: All 4 tools (CRM, Appointment, Weather, Cost) pass comprehensive unit tests
2. **RAG System**: Perfect recall - always finds relevant documents
3. **HTTP Performance**: Server handles 5+ requests/second with sub-10ms response
4. **LLM Bottleneck**: Local CPU inference limits concurrent WebSocket handling

## Recommendations

1. **For Production**: Use GPU or API-based LLM for faster inference
2. **Improve Precision**: Tune embedding model or add re-ranking
3. **Add Caching**: Cache frequent RAG queries for better latency
