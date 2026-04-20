#!/usr/bin/env python3
"""
CUDA test workload runner — executes inside the cuda-test container.
Calls compiled C binaries (cmake/autoconf/meson) and writes JSON results.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def run_c_tool(tool_name: str, gpu: str, cuda_ver: str, **kwargs) -> dict:
    cmd = [tool_name, "--gpu", gpu, "--cuda", cuda_ver]
    if "iterations" in kwargs:
        cmd += ["--iterations", str(kwargs["iterations"])]
    if "expected" in kwargs:
        cmd += ["--expected", kwargs["expected"]]

    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        elapsed = time.monotonic() - start
        if proc.stdout.strip():
            result = json.loads(proc.stdout.strip())
            result["duration_sec"] = round(elapsed, 3)
            result["exit_code"] = proc.returncode
            return result
        return {
            "tool": tool_name,
            "result": "FAIL",
            "error": f"No output. stderr: {proc.stderr.strip()}",
            "duration_sec": round(elapsed, 3),
            "exit_code": proc.returncode,
        }
    except FileNotFoundError:
        return {
            "tool": tool_name,
            "result": "FAIL",
            "error": f"Binary '{tool_name}' not found in PATH",
            "duration_sec": 0,
            "exit_code": -1,
        }
    except subprocess.TimeoutExpired:
        return {
            "tool": tool_name,
            "result": "FAIL",
            "error": "Timeout after 60s",
            "duration_sec": 60,
            "exit_code": -1,
        }


def check_cuda_version(expected: str) -> dict:
    return run_c_tool("cuda_version_checker", gpu="N/A", cuda_ver=expected, expected=expected)


def run_math_validation(gpu: str, cuda: str) -> dict:
    return run_c_tool("cuda_math_validator", gpu=gpu, cuda_ver=cuda)


def run_driver_compatibility_check(gpu: str, cuda: str) -> dict:
    return run_c_tool("cuda_version_checker", gpu=gpu, cuda_ver=cuda, expected=cuda)


def run_stress_test(gpu: str, cuda: str, iterations: int = 1_000_000) -> dict:
    return run_c_tool("cuda_stress_runner", gpu=gpu, cuda_ver=cuda, iterations=iterations)


SUITE_MAP = {
    "cublas_regression": run_math_validation,
    "driver_compat":     run_driver_compatibility_check,
    "stress":            run_stress_test,
}


def run_config(config: dict) -> dict:
    gpu        = config["gpu_type"]
    cuda       = config["cuda_version"]
    driver     = config.get("driver_version", "unknown")
    suites     = config.get("test_suites", list(SUITE_MAP.keys()))

    results = []
    for suite in suites:
        fn = SUITE_MAP.get(suite)
        if fn:
            results.append(fn(gpu=gpu, cuda=cuda))
        else:
            results.append({"tool": suite, "result": "SKIP", "reason": "unknown suite"})

    all_pass = all(r.get("result") == "PASS" for r in results)
    return {
        "gpu_type":       gpu,
        "cuda_version":   cuda,
        "driver_version": driver,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "overall":        "PASS" if all_pass else "FAIL",
        "tests":          results,
    }


def main():
    parser = argparse.ArgumentParser(description="CUDA test workload runner")
    parser.add_argument("--gpu",    default=None, help="GPU type filter")
    parser.add_argument("--cuda",   default=None, help="CUDA version filter")
    parser.add_argument("--suite",  action="append", dest="suites", help="Test suite (repeatable)")
    parser.add_argument("--matrix", default="/tests/test_matrix.json")
    parser.add_argument("--output", default="/results")
    args = parser.parse_args()

    # Write the CUDA version stub dynamically so version checks match the config
    if args.cuda:
        cuda_ver_file = Path("/usr/local/cuda/version.txt")
        if cuda_ver_file.parent.exists():
            cuda_ver_file.write_text(f"CUDA Version {args.cuda}\n")

    with open(args.matrix) as f:
        matrix = json.load(f)

    configs = matrix["test_configs"]

    if args.gpu:
        configs = [c for c in configs if c["gpu_type"] == args.gpu]
    if args.cuda:
        configs = [c for c in configs if c["cuda_version"] == args.cuda]
    if args.suites:
        configs = [{**c, "test_suites": args.suites} for c in configs]

    if not configs:
        print(json.dumps({"error": "No matching configs", "overall": "FAIL"}))
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    exit_code = 0

    for config in configs:
        result = run_config(config)
        all_results.append(result)

        fname = f"{config['gpu_type']}_{config['cuda_version'].replace('.', '_')}.json"
        out_path = out_dir / fname
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        print(json.dumps(result, indent=2))

        if result["overall"] != "PASS":
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
