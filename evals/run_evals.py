#!/usr/bin/env python
"""DentaBot evaluation suite runner."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EVALS_DIR = Path(__file__).parent
REPORTS_DIR = EVALS_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(EVALS_DIR.parent))


def get_hardware_info() -> dict:
    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        ram_gb = "unknown"

    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "ram_gb": ram_gb,
        "python_version": sys.version.split()[0],
    }


def get_dependency_versions() -> dict:
    import importlib.metadata

    packages = [
        "fastapi",
        "uvicorn",
        "chromadb",
        "sentence-transformers",
        "llama-cpp-python",
        "ragas",
        "pytest",
        "websockets",
        "locust",
    ]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except Exception:
            versions[package] = "not installed"
    return versions


def run_pytest_tests(pattern: str = "") -> dict:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(EVALS_DIR),
        "-v",
        "--tb=short",
        f"--junit-xml={REPORTS_DIR / 'pytest_results.xml'}",
    ]
    if pattern:
        cmd.append(f"-k={pattern}")

    print("\nRUNNING PYTEST TESTS")
    print(" ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, check=False)
    return {"success": result.returncode == 0, "exit_code": result.returncode}


def run_rag_evaluation() -> dict:
    print("\nRUNNING RAG EVALUATION")
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
        print(f"RAG evaluation failed: {exc}")
        return {"success": False, "error": str(exc)}


def generate_markdown_report(results: dict) -> str:
    hardware = results.get("hardware", {})
    dependencies = results.get("dependencies", {})
    pytest_results = results.get("pytest", {})
    rag = results.get("rag", {})

    lines = [
        "# DentaBot Evaluation Report",
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n## Hardware",
        f"- Platform: {hardware.get('platform', 'N/A')} {hardware.get('platform_release', '')}",
        f"- CPU: {hardware.get('processor', 'N/A')} ({hardware.get('cpu_count', 'N/A')} cores)",
        f"- RAM: {hardware.get('ram_gb', 'N/A')} GB",
        f"- Python: {hardware.get('python_version', 'N/A')}",
        "\n## Summary",
        "\n| Component | Result |",
        "| --- | --- |",
        f"| Pytest suite | {'Passed' if pytest_results.get('success') else 'Failed or skipped'} |",
        f"| RAG evaluation | {'Passed' if rag.get('success') else 'Failed or skipped'} |",
        "| Load testing | Run separately with `locust -f evals/locust_ws.py --host=http://localhost:8000` |",
    ]

    if rag.get("success"):
        lines.extend(
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
    elif rag.get("error"):
        lines.extend(["\n## RAG Error", f"\n```text\n{rag['error']}\n```"])

    if dependencies:
        lines.extend(["\n## Dependencies", "\n| Package | Version |", "| --- | --- |"])
        lines.extend(f"| {package} | {version} |" for package, version in dependencies.items())

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="DentaBot evaluation suite")
    parser.add_argument("--component", choices=["all", "tools", "rag"], default="all")
    parser.add_argument("--quick", action="store_true", help="Kept for compatibility; currently runs the same focused checks.")
    parser.add_argument("--report-only", action="store_true", help="Regenerate the markdown report from existing JSON results.")
    args = parser.parse_args()

    results_path = REPORTS_DIR / "evaluation_results.json"
    if args.report_only and results_path.exists():
        results = json.loads(results_path.read_text(encoding="utf-8"))
    else:
        results = {
            "timestamp": datetime.now().isoformat(),
            "mode": "quick" if args.quick else "full",
            "hardware": get_hardware_info(),
            "dependencies": get_dependency_versions(),
            "pytest": {},
            "rag": {},
        }
        if args.component in {"all", "tools"}:
            results["pytest"] = run_pytest_tests()
        if args.component in {"all", "rag"}:
            results["rag"] = run_rag_evaluation()
        results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    report_path = REPORTS_DIR / "EVALUATION_REPORT.md"
    report_path.write_text(generate_markdown_report(results), encoding="utf-8")

    print(f"\nRaw results saved to: {results_path}")
    print(f"Markdown report saved to: {report_path}")
    print("\nEvaluation complete.")

    failed = any(
        component.get("success") is False
        for component in (results.get("pytest", {}), results.get("rag", {}))
        if component
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
