#!/usr/bin/env python3
"""
GPU Test Farm — Result Aggregator
Reads JSON result files from results/ and prints a formatted summary report.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone


def load_results(results_dir: Path) -> list[dict]:
    results = []
    for p in sorted(results_dir.rglob("*.json")):
        if p.name == "run_summary.json":
            continue
        try:
            with open(p) as f:
                results.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return results


def count_test_cases(result: dict) -> tuple[int, int]:
    """Returns (passed, total) test cases for a result."""
    tests = result.get("tests", [])
    if not tests:
        passed = 1 if result.get("overall") == "PASS" else 0
        return passed, 1
    passed = sum(1 for t in tests if t.get("result") == "PASS")
    return passed, len(tests)


def print_report(results: list[dict]) -> bool:
    width = 56
    sep = "=" * width

    print(sep)
    print("  GPU TEST FARM — EXECUTION REPORT")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(sep)

    total_cases  = 0
    total_passed = 0
    failures     = []

    for result in results:
        passed, total = count_test_cases(result)
        total_cases  += total
        total_passed += passed

        gpu  = result.get("gpu_type",     result.get("gpu", "unknown"))
        cuda = result.get("cuda_version", result.get("cuda", "?"))
        node = result.get("node", "local")
        overall = result.get("overall", "UNKNOWN")

        tag = "✓" if overall == "PASS" else "✗"
        print(f"\n  [{tag}] {gpu} / CUDA {cuda}  (node: {node})")
        print(f"      Overall: {overall}  |  {passed}/{total} tests passed")

        for test in result.get("tests", []):
            tool   = test.get("tool", "?")
            res    = test.get("result", "?")
            dur    = test.get("duration_sec", test.get("elapsed_sec", "?"))
            marker = "  ✓" if res == "PASS" else "  ✗"
            print(f"      {marker} {tool:<30} {res}  ({dur}s)")

            if res not in ("PASS", "SKIP"):
                err = test.get("error", "")
                failures.append(f"[{gpu}/CUDA-{cuda}] {tool}: {err or res}")

        if overall != "PASS" and not result.get("tests"):
            failures.append(f"[{gpu}/CUDA-{cuda}] (node={node}): {result.get('error', overall)}")

    total_failed = total_cases - total_passed
    pass_rate    = (total_passed / total_cases * 100) if total_cases else 0

    print(f"\n{sep}")
    print(f"  Total configs tested : {len(results)}")
    print(f"  Total test cases     : {total_cases}")
    print(f"  Passed               : {total_passed}")
    print(f"  Failed               : {total_failed}")
    print(f"  Pass rate            : {pass_rate:.1f}%")

    if failures:
        print(f"\n  FAILURES ({len(failures)}):")
        for f in failures:
            print(f"    • {f}")

    print(sep)
    return total_failed == 0


def main():
    parser = argparse.ArgumentParser(description="GPU Test Farm Report Generator")
    parser.add_argument("--results-dir", default="results", help="Path to results directory")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"ERROR: Results directory '{results_dir}' not found. Run 'make test' first.")
        sys.exit(1)

    results = load_results(results_dir)
    if not results:
        print(f"No result files found in '{results_dir}'. Run 'make test' first.")
        sys.exit(1)

    success = print_report(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
