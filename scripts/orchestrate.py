#!/usr/bin/env python3
"""
GPU Test Farm Orchestrator
Dispatches CUDA test jobs across node containers, collects results.
Uses Docker Python SDK (Mac variant) instead of paramiko/SSH.
"""

import argparse
import json
import os
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
    """Return names of running gpu-node-* containers."""
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
    """Check disk and memory before dispatching."""
    try:
        node = client.containers.get(node_name)
        code, out = node.exec_run("df -h /")
        if code != 0:
            print(f"  [!] {node_name}: disk check failed")
            return False
        return True
    except Exception as e:
        print(f"  [!] {node_name}: health check error: {e}")
        return False


def dispatch_job(client: docker.DockerClient, node_name: str, config: dict, results_dir: Path) -> dict:
    """Run one test config on a node via docker exec → docker run."""
    gpu    = config["gpu_type"]
    cuda   = config["cuda_version"]
    suites = config.get("test_suites", [])

    print(f"  [>] Dispatching [{gpu}/CUDA-{cuda}] → {node_name} (suites: {', '.join(suites)})")

    node_results_dir = results_dir / node_name
    node_results_dir.mkdir(parents=True, exist_ok=True)

    # Map host results dir to container path via the shared volume already mounted
    # For Mac variant: run the test container via docker exec on the node container
    # The node has /var/run/docker.sock mounted from host so it can run sibling containers
    suite_args = " ".join(f"--suite {s}" for s in suites) if suites else ""
    cmd = (
        f"docker run --rm "
        f"-v /opt/test_results:/results "
        f"{TEST_IMAGE} "
        f"--gpu {gpu} --cuda {cuda} {suite_args} "
        f"--output /results"
    )

    try:
        node = client.containers.get(node_name)
        start = time.monotonic()
        exit_code, output = node.exec_run(cmd, demux=False)
        elapsed = time.monotonic() - start

        output_text = output.decode("utf-8", errors="replace") if output else ""

        result = {
            "node":         node_name,
            "gpu_type":     gpu,
            "cuda_version": cuda,
            "exit_code":    exit_code,
            "elapsed_sec":  round(elapsed, 2),
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "output":       output_text.strip(),
            "overall":      "PASS" if exit_code == 0 else "FAIL",
        }

        # Try to parse embedded JSON results from output
        test_results = []
        for line in output_text.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    test_results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if test_results:
            result["tests"] = test_results

        fname = f"{gpu}_{cuda}.json".replace(".", "_")
        with open(node_results_dir / fname, "w") as f:
            json.dump(result, f, indent=2)

        status = "PASS" if exit_code == 0 else "FAIL"
        print(f"  [{'OK' if status == 'PASS' else '!!'}] {node_name} [{gpu}/CUDA-{cuda}]: {status} ({elapsed:.1f}s)")
        return result

    except docker.errors.NotFound:
        err = {"node": node_name, "gpu_type": gpu, "cuda_version": cuda,
               "overall": "FAIL", "error": "Container not found"}
        print(f"  [!!] {node_name}: container not found")
        return err
    except Exception as e:
        err = {"node": node_name, "gpu_type": gpu, "cuda_version": cuda,
               "overall": "FAIL", "error": str(e)}
        print(f"  [!!] {node_name}: {e}")
        return err


def round_robin_schedule(configs: list[dict], nodes: list[str]) -> list[tuple[str, dict]]:
    """Assign configs to nodes in round-robin order."""
    assignments = []
    for i, config in enumerate(configs):
        node = nodes[i % len(nodes)]
        assignments.append((node, config))
    return assignments


def main():
    parser = argparse.ArgumentParser(description="GPU Test Farm Orchestrator")
    parser.add_argument("--matrix",      default="docker/test_matrix.json")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--gpu",         default=None, help="Filter by GPU type")
    parser.add_argument("--cuda",        default=None, help="Filter by CUDA version")
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
    nodes = discover_nodes(client)

    if not nodes:
        print("\nERROR: No healthy nodes found. Run 'make infra-up' first.")
        sys.exit(1)

    print(f"\nHealth checking {len(nodes)} node(s)...")
    healthy_nodes = [n for n in nodes if node_health_check(client, n)]
    if not healthy_nodes:
        print("ERROR: All nodes failed health check.")
        sys.exit(1)

    assignments = round_robin_schedule(configs, healthy_nodes)
    print(f"\nDispatching {len(assignments)} job(s) across {len(healthy_nodes)} node(s)...")

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
            "nodes_used": healthy_nodes,
            "results":    all_results,
        }, f, indent=2)

    passed = sum(1 for r in all_results if r.get("overall") == "PASS")
    failed = len(all_results) - passed
    print(f"\nSummary: {passed}/{len(all_results)} passed, {failed} failed")
    print(f"Results written to: {results_dir}/")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
