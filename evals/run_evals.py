#!/usr/bin/env python
"""
DentaBot Evaluation Suite - Main Runner

Runs all evaluations and generates a comprehensive report.

Usage:
    python evals/run_evals.py                    # Run all tests
    python evals/run_evals.py --quick            # Quick mode (fewer trials)
    python evals/run_evals.py --report-only      # Generate report from existing results
    python evals/run_evals.py --component tools  # Run only tool tests

Frameworks Used:
    - pytest: Unit and integration tests
    - RAGAS: RAG evaluation (retrieval relevance, faithfulness)
    - DeepEval: LLM output evaluation (custom metrics)
    - LangSmith: Tracing and evaluation
    - Locust: Load testing

Requirements:
    pip install pytest pytest-html ragas datasets websockets psutil locust deepeval langsmith
"""
import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════

EVALS_DIR = Path(__file__).parent
REPORTS_DIR = EVALS_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def get_hardware_info() -> dict:
    """Collect hardware information."""
    import psutil
    
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "python_version": sys.version,
    }


def get_dependency_versions() -> dict:
    """Get versions of key dependencies."""
    versions = {}
    
    packages = [
        "fastapi", "uvicorn", "chromadb", "sentence-transformers",
        "llama-cpp-python", "ragas", "pytest", "websockets"
    ]
    
    for pkg in packages:
        try:
            import importlib.metadata
            versions[pkg] = importlib.metadata.version(pkg.replace("-", "_"))
        except Exception:
            versions[pkg] = "not installed"
    
    return versions


def run_pytest_tests(test_pattern: str = "", extra_args: list = None) -> dict:
    """Run pytest tests and return results."""
    cmd = [
        sys.executable, "-m", "pytest",
        str(EVALS_DIR),
        "-v",
        "--tb=short",
        f"--junit-xml={REPORTS_DIR}/pytest_results.xml",
    ]
    
    if test_pattern:
        cmd.append(f"-k={test_pattern}")
    
    if extra_args:
        cmd.extend(extra_args)
    
    print(f"\n{'='*60}")
    print("RUNNING PYTEST TESTS")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, capture_output=False)
    
    return {
        "exit_code": result.returncode,
        "success": result.returncode == 0
    }


# Note: Load testing is now done with Locust
# Run: locust -f evals/locustfile.py --host=ws://localhost:8000


def run_rag_evaluation() -> dict:
    """Run RAG evaluation."""
    print(f"\n{'='*60}")
    print("RUNNING RAG EVALUATION")
    print(f"{'='*60}\n")
    
    try:
        from evals.test_rag_ragas import load_ground_truth, compute_basic_retrieval_metrics
        
        data = load_ground_truth()
        metrics = compute_basic_retrieval_metrics(data, top_k=3)
        
        return {
            "success": True,
            "precision_at_k": metrics["precision@k"],
            "recall_at_k": metrics["recall@k"],
            "hit_rate": metrics["hit_rate"],
            "total_queries": metrics["total_queries"]
        }
    except Exception as e:
        print(f"RAG evaluation failed: {e}")
        return {"success": False, "error": str(e)}


def generate_markdown_report(results: dict) -> str:
    """Generate markdown report from results."""
    report = []
    
    # Header
    report.append("# DentaBot Evaluation Report")
    report.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Hardware Info
    hw = results.get("hardware", {})
    report.append("\n## Hardware Configuration")
    report.append(f"- **Platform:** {hw.get('platform', 'N/A')} {hw.get('platform_release', '')}")
    report.append(f"- **CPU:** {hw.get('processor', 'N/A')} ({hw.get('cpu_count', 'N/A')} cores)")
    report.append(f"- **RAM:** {hw.get('ram_gb', 'N/A')} GB")
    report.append(f"- **Python:** {hw.get('python_version', 'N/A').split()[0]}")
    
    # Summary
    report.append("\n## Summary")
    
    tests = results.get("pytest", {})
    report.append(f"- **Unit Tests:** {'✓ Passed' if tests.get('success') else '✗ Failed'}")
    
    rag = results.get("rag", {})
    if rag.get("success"):
        report.append(f"- **RAG Hit Rate:** {rag.get('hit_rate', 0)*100:.1f}%")
        report.append(f"- **RAG Precision@3:** {rag.get('precision_at_k', 0):.4f}")
    
    report.append("- **Load Testing:** Use Locust (locust -f evals/locustfile.py)")
    
    # RAG Metrics
    if rag.get("success"):
        report.append("\n## RAG Evaluation")
        report.append("\n| Metric | Value |")
        report.append("|--------|-------|")
        report.append(f"| Precision@3 | {rag.get('precision_at_k', 0):.4f} |")
        report.append(f"| Recall@3 | {rag.get('recall_at_k', 0):.4f} |")
        report.append(f"| Hit Rate | {rag.get('hit_rate', 0):.4f} |")
        report.append(f"| Total Queries | {rag.get('total_queries', 0)} |")
    
    # Load Testing Note
    report.append("\n## Load Testing")
    report.append("\nRun load tests with Locust:")
    report.append("```bash")
    report.append("locust -f evals/locustfile.py --host=ws://localhost:8000")
    report.append("```")
    
    # Dependencies
    deps = results.get("dependencies", {})
    if deps:
        report.append("\n## Dependencies")
        report.append("\n| Package | Version |")
        report.append("|---------|---------|")
        for pkg, ver in deps.items():
            report.append(f"| {pkg} | {ver} |")
    
    return "\n".join(report)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="DentaBot Evaluation Suite")
    parser.add_argument("--quick", action="store_true", help="Quick mode (fewer trials)")
    parser.add_argument("--report-only", action="store_true", help="Generate report from existing results")
    parser.add_argument("--component", choices=["tools", "rag", "all"],
                        default="all", help="Component to test")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DENTABOT EVALUATION SUITE")
    print("=" * 60)
    print(f"Mode: {'Quick' if args.quick else 'Full'}")
    print(f"Component: {args.component}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "mode": "quick" if args.quick else "full",
        "hardware": {},
        "dependencies": {},
        "pytest": {},
        "rag": {}
    }
    
    # Collect system info
    try:
        results["hardware"] = get_hardware_info()
        results["dependencies"] = get_dependency_versions()
    except Exception as e:
        print(f"Warning: Could not collect system info: {e}")
    
    # Run tests based on component
    if args.component in ["all", "tools"]:
        results["pytest"] = run_pytest_tests()
    
    if args.component in ["all", "rag"]:
        results["rag"] = run_rag_evaluation()
    
    # Note: Load testing is done separately with Locust
    # Run: locust -f evals/locustfile.py --host=ws://localhost:8000
    
    # Save raw results
    results_path = REPORTS_DIR / "evaluation_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw results saved to: {results_path}")
    
    # Generate markdown report
    report = generate_markdown_report(results)
    report_path = REPORTS_DIR / "EVALUATION_REPORT.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Markdown report saved to: {report_path}")
    
    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)
    
    # Print summary
    print("\nQuick Summary:")
    print(f"  Tests: {'✓' if results['pytest'].get('success') else '✗'}")
    print(f"  RAG: {'✓' if results['rag'].get('success') else '✗'}")
    print(f"  Latency: {'✓' if results['latency'].get('success') else 'skipped'}")
    print(f"  Throughput: {'✓' if results['throughput'].get('success') else 'skipped'}")


if __name__ == "__main__":
    asyncio.run(main())
