#!/usr/bin/env python
"""Run a quick local DentaBot evaluation and write a small markdown summary."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def run_rag_smoke() -> dict:
    try:
        from evals.test_rag_ragas import compute_basic_retrieval_metrics, load_ground_truth

        data = load_ground_truth()
        metrics = compute_basic_retrieval_metrics(data, top_k=3)
        return {
            "success": True,
            "precision_at_3": metrics["precision@k"],
            "recall_at_3": metrics["recall@k"],
            "hit_rate": metrics["hit_rate"],
            "total_queries": metrics["total_queries"],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def write_report(results: dict, reports_dir: Path) -> None:
    rag = results["rag"]
    report = [
        "# DentaBot Quick Evaluation Report",
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n## Summary",
        "\n| Component | Result |",
        "| --- | --- |",
        f"| RAG smoke test | {'Passed' if rag.get('success') else 'Failed'} |",
        "| Tool tests | Run with `python -m pytest evals/test_tools_*.py -v` |",
        "| Load test | Run with `locust -f evals/locust_ws.py --host=http://localhost:8000` |",
    ]

    if rag.get("success"):
        report.extend(
            [
                "\n## RAG Metrics",
                "\n| Metric | Value |",
                "| --- | --- |",
                f"| Precision@3 | {rag['precision_at_3']} |",
                f"| Recall@3 | {rag['recall_at_3']} |",
                f"| Hit Rate | {rag['hit_rate']} |",
                f"| Total Queries | {rag['total_queries']} |",
            ]
        )
    else:
        report.extend(["\n## RAG Error", f"\n```text\n{rag.get('error')}\n```"])

    (reports_dir / "EVALUATION_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    print("=" * 60)
    print("DENTABOT QUICK EVALUATION")
    print("=" * 60)

    results = {
        "timestamp": datetime.now().isoformat(),
        "rag": run_rag_smoke(),
        "locust": "Run manually with: locust -f evals/locust_ws.py --host=http://localhost:8000",
    }

    reports_dir = Path(__file__).parent / "evals" / "reports"
    reports_dir.mkdir(exist_ok=True)

    results_path = reports_dir / "quick_eval_results.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(results, reports_dir)

    print(f"Results saved to: {results_path}")
    if results["rag"].get("success"):
        print("RAG smoke test passed.")
        return 0

    print(f"RAG smoke test failed: {results['rag'].get('error')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
