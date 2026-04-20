#!/usr/bin/env python3
"""
GPU Test Farm Orchestrator
Dispatches CUDA test jobs across nodes (round-robin), collects results.
Mac variant: runs cuda-test containers directly on the host Docker daemon,
simulating dispatch to node containers (avoids Docker-in-Docker volume issues).
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    import docker
except ImportError:
    print("ERROR: Install docker SDK: pip install docker")
    sys.exit(1)

NODE_NAMES = ["gpu-node-1", "gpu-node-2"]
TEST_IMAGE  = "cuda-test:latest"


def discover_nodes(client: docker.DockerClient) -> list[str]:
    running = []
    for name in NODE_NAMES:
        try:
            c = client.containers.get(name)
            if c.status == "running":
                running.append(name)
                print(f"  [+] Node found: {name} (status={c.status})")
            else:
                print(f"  [-] Node {name} not running (status={c.status})")
        except docker.errors.NotFound:
            print(f"  [-] Node {name} not found — run 'make infra-up' first")
    return running


def node_health_check(client: docker.DockerClient, node_name: str) -> bool:
    try:
        node = client.containers.get(node_name)
        exit_code, _ = node.exec_run("df -h /")
        return exit_code == 0
    except Exception as e:
        print(f"  [!] {node_name}: health check error: {e}")
        return False


def dispatch_job(client: docker.DockerClient, node_name: str, config: dict, results_dir: Path) -> dict:
    gpu    = config["gpu_type"]
    cuda   = config["cuda_version"]
    driver = config.get("driver_version", "unknown")
    suites = config.get("test_suites", [])

    print(f"  [>] Dispatching [{gpu}/CUDA-{cuda}] → {node_name} (suites: {', '.join(suites)})")

    node_results_dir = results_dir / node_name
    node_results_dir.mkdir(parents=True, exist_ok=True)

    cmd_parts = [f"--gpu {gpu}", f"--cuda {cuda}"]
    for s in suites:
        cmd_parts += ["--suite", s]

    start = time.monotonic()
    try:
        output = client.containers.run(
            TEST_IMAGE,
            command=" ".join(cmd_parts),
            volumes={str(node_results_dir.resolve()): {"bind": "/results", "mode": "rw"}},
            remove=True,
            stdout=True,
            stderr=True,
        )
        elapsed   = time.monotonic() - start
        exit_code = 0
        output_text = output.decode("utf-8", errors="replace") if output else ""

    except docker.errors.ContainerError as e:
        elapsed     = time.monotonic() - start
        exit_code   = e.exit_status
        output_text = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)

    except Exception as e:
        elapsed     = time.monotonic() - start
        exit_code   = -1
        output_text = str(e)

    test_results = []
    for line in output_text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                test_results.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    overall = "PASS" if exit_code == 0 else "FAIL"
    result  = {
        "node":           node_name,
        "gpu_type":       gpu,
        "cuda_version":   cuda,
        "driver_version": driver,
        "exit_code":      exit_code,
        "elapsed_sec":    round(elapsed, 2),
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "overall":        overall,
        "tests":          test_results,
    }

    fname = f"{gpu}_{cuda.replace('.', '_')}.json"
    with open(node_results_dir / fname, "w") as f:
        json.dump(result, f, indent=2)

    marker = "OK" if overall == "PASS" else "!!"
    print(f"  [{marker}] {node_name} [{gpu}/CUDA-{cuda}]: {overall} ({elapsed:.1f}s)")
    return result


def round_robin_schedule(configs: list[dict], nodes: list[str]) -> list[tuple[str, dict]]:
    return [(nodes[i % len(nodes)], config) for i, config in enumerate(configs)]


def main():
    parser = argparse.ArgumentParser(description="GPU Test Farm Orchestrator")
    parser.add_argument("--matrix",      default="docker/test_matrix.json")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--gpu",         default=None)
    parser.add_argument("--cuda",        default=None)
    parser.add_argument("--workers",     type=int, default=4)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("GPU TEST FARM ORCHESTRATOR")
    print("=" * 60)

    with open(args.matrix) as f:
        matrix = json.load(f)

    configs = matrix["test_configs"]
    if args.gpu:
        configs = [c for c in configs if c["gpu_type"] == args.gpu]
    if args.cuda:
        configs = [c for c in configs if c["cuda_version"] == args.cuda]

    print(f"\nTest matrix: {len(configs)} config(s)")
    for c in configs:
        print(f"  {c['gpu_type']}/CUDA-{c['cuda_version']}: {c.get('test_suites', [])}")

    print("\nDiscovering nodes...")
    client = docker.from_env()
    nodes  = discover_nodes(client)

    if not nodes:
        print("\nERROR: No nodes found. Run 'make infra-up' first.")
        sys.exit(1)

    print(f"\nHealth checking {len(nodes)} node(s)...")
    healthy = [n for n in nodes if node_health_check(client, n)]
    if not healthy:
        print("ERROR: All nodes failed health check.")
        sys.exit(1)

    assignments = round_robin_schedule(configs, healthy)
    print(f"\nDispatching {len(assignments)} job(s) across {len(healthy)} node(s)...")

    all_results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(dispatch_job, client, node, config, results_dir): (node, config)
            for node, config in assignments
        }
        for future in as_completed(futures):
            all_results.append(future.result())

    summary_path = results_dir / "run_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "run_time":   datetime.now(timezone.utc).isoformat(),
            "nodes_used": healthy,
            "results":    all_results,
        }, f, indent=2)

    passed = sum(1 for r in all_results if r.get("overall") == "PASS")
    failed = len(all_results) - passed
    print(f"\nSummary: {passed}/{len(all_results)} passed, {failed} failed")
    print(f"Results written to: {results_dir}/")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
