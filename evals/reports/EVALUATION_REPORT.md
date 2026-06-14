# DentaBot Evaluation Report

_Generated: n/a_

## Executive Summary

| Dimension | Status / Value |
|-----------|----------------|


## Environment
_(environment.json not found)_


## §2.2 Component Unit Tests (pytest)
_(pytest_tools.xml not found — run `python evals/run_all.py`)_


## §2.1 Overall Conversational Correctness
_(conversation_results.json not found — start the server and run `python evals/run_all.py`)_


## §2.1 LLM-Judge Human Agreement
_(no human annotations yet — fill in `evals/data/human_annotations_template.csv`)_


## §2.2.1 RAG Component
_(rag_results.json not found)_


## §2.2.2 / §2.2.3 LLM Tool-Calling Accuracy
_(tool_calling_results.json not found)_


## §2.3.1 Latency
_(latency_results.json not found)_


## §2.3.2 Concurrency / Throughput
_(concurrency_results.json not found)_


## Limitations & Notes

- The system-under-test runs a 1.5B-parameter quantised local LLM on CPU; production-grade latency requires GPU.
- TTFT in this report is the time-to-first-streamed-chunk after the LLM completes; the engine does not stream tokens directly from the model.
- The LLM judge (Gemini 2.0 Flash) is independent from the SUT but may share biases with other LLMs; human-agreement validation is provided where annotations exist.
- Concurrency is intentionally limited to small ramps (1, 2, 4 users) given CPU-bound inference (~25 s/turn).
