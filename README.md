# GPU Test Farm Provisioner

A miniature version of NVIDIA's Compute CUDA QA test infrastructure — an automated system that provisions test nodes, configures them with GPU drivers and CUDA Toolkit, deploys containerized test workloads, runs tests, and collects results.

**Stack:** Terraform · Ansible · Docker · Python · cmake · autoconf · meson

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator (Python)                     │
│         orchestrate.py → dispatch → collect → report        │
└────────────┬──────────────────────────┬─────────────────────┘
             │                          │
    ┌────────▼─────────┐     ┌──────────▼────────┐
    │   gpu-node-1     │     │   gpu-node-2       │
    │  (Ubuntu 22.04)  │     │  (Ubuntu 22.04)    │
    │  ┌────────────┐  │     │  ┌──────────────┐  │
    │  │cuda-test   │  │     │  │ cuda-test    │  │
    │  │container   │  │     │  │ container    │  │
    │  │ cmake tool │  │     │  │  cmake tool  │  │
    │  │ autoconf   │  │     │  │  autoconf    │  │
    │  │ meson tool │  │     │  │  meson tool  │  │
    │  └────────────┘  │     │  └──────────────┘  │
    └──────────────────┘     └────────────────────┘
             ▲                          ▲
             └─────── Terraform ────────┘
                   (Docker provider)
             ▲                          ▲
             └──────── Ansible ─────────┘
                 (cuda_stub, docker, test_runner roles)
```

### Four Layers

| Layer | Tool | Purpose | JD Mapping |
|-------|------|---------|------------|
| Infrastructure | Terraform + Docker | Provisions Ubuntu test node containers | Virtualization/KVM |
| Configuration | Ansible | Installs CUDA stub, Docker CLI, test runner | Configuration mgmt |
| Workload | Docker | Runs containerized test jobs | Containers |
| Orchestration | Python | Dispatches jobs, collects results, reports | Automation |

### Data Flow

1. **Terraform** provisions 2 Ubuntu containers (`gpu-node-1`, `gpu-node-2`) simulating GPU test nodes
2. **Ansible** SSHes (or docker-execs) into each node and installs Docker, CUDA stub (nvcc/nvidia-smi), test infra
3. **Python orchestrator** reads `test_matrix.json` (GPU type × CUDA version × test suite) and dispatches jobs
4. Each **Docker container** runs 3 compiled C test tools (cmake/autoconf/meson build systems) and writes JSON results
5. Orchestrator **collects results**, generates aggregated summary report

---

## Prerequisites

**Mac (recommended for development):**
```bash
brew install terraform ansible python@3.11
brew install --cask docker   # Docker Desktop
pip3 install docker          # Python Docker SDK
```

**Linux (for real KVM):** see [KVM Setup](#kvm-phase-2-linux)

---

## Quick Start

```bash
# Full workflow: provision → configure → build → test → report
make all

# Or step by step:
make infra-up     # Provision node containers via Terraform
make configure    # Configure nodes with Ansible
make build        # Build cuda-test Docker image
make test         # Run test matrix across nodes
make report       # Print aggregated report

# Smoke test (no nodes needed)
make verify

# Tear down
make clean
```

---

## Test Matrix

Defined in [`docker/test_matrix.json`](docker/test_matrix.json):

| GPU | CUDA | Driver | Test Suites |
|-----|------|--------|-------------|
| H100 | 13.0 | 550.90 | cublas_regression, driver_compat, stress |
| A100 | 12.8 | 535.183 | cublas_regression, driver_compat |

---

## C Test Tools (Three Build Systems)

The `cuda-test` container compiles three C validation tools, one per build system:

| Tool | Build System | What It Does |
|------|-------------|--------------|
| `cuda_math_validator` | **cmake** | 4×4 matrix multiply validation (cuBLAS simulation) |
| `cuda_version_checker` | **autoconf/automake** | Reads `/usr/local/cuda/version.txt`, validates expected version |
| `cuda_stress_runner` | **meson** | CPU stress test simulating GPU compute load, reports ops/sec |

```bash
# Inside the container they're called like:
cuda_math_validator --gpu H100 --cuda 13.0
cuda_version_checker --expected 13.0
cuda_stress_runner --gpu H100 --iterations 5000000
```

---

## Directory Structure

```
gpu-test-farm-provisioner/
├── terraform/
│   ├── main.tf              # Mac: Docker provider (kreuzwerker/docker)
│   ├── variables.tf
│   ├── outputs.tf
│   └── kvm/main.tf          # Linux: libvirt/KVM provider (Phase 2)
├── ansible/
│   ├── inventory/
│   │   ├── hosts.yml        # Mac: ansible_connection=docker
│   │   └── hosts_ssh.yml    # Linux: SSH for KVM VMs
│   ├── playbooks/
│   │   ├── setup_node.yml
│   │   ├── deploy_tests.yml
│   │   └── collect_results.yml
│   └── roles/
│       ├── docker/          # Installs Docker CLI
│       ├── cuda_stub/       # Simulates CUDA Toolkit
│       └── test_runner/     # Deploys test infra
├── docker/
│   ├── Dockerfile.node      # Ubuntu "VM" container
│   ├── Dockerfile.cuda-test # Test workload (builds C tools)
│   ├── test_runner.py       # Python orchestrates C binaries
│   ├── test_matrix.json     # GPU × CUDA × suite config
│   └── tests/
│       ├── cmake_validator/   # cuda_math_validator.c + CMakeLists.txt
│       ├── autoconf_checker/  # cuda_version_checker.c + configure.ac
│       └── meson_stress/      # cuda_stress_runner.c + meson.build
├── scripts/
│   ├── orchestrate.py       # Dispatches jobs, collects results
│   └── generate_report.py   # Aggregates and prints report
├── results/                 # .gitignored
├── Makefile
└── README.md
```

---

## KVM Phase 2 (Linux)

Once the Mac version is working, deploy real KVM VMs on AWS (m5.xlarge, ~$3-5 for 2-3 hours):

```bash
# 1. Launch Ubuntu 22.04 EC2, SSH in
# 2. Install KVM + Terraform
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients
# 3. Clone repo and swap Terraform provider
cp terraform/kvm/main.tf terraform/main.tf
cp ansible/inventory/hosts_ssh.yml ansible/inventory/hosts.yml
# 4. Same workflow
make all
virsh list --all  # Verify real KVM VMs
```

**Terraform provider swap is one line** — libvirt instead of Docker. Ansible playbooks run identically.

---

## Architecture Decisions

**1. Provider-agnostic Terraform:** The Docker provider (Mac) and libvirt provider (KVM) both use the same `variables.tf` and `outputs.tf`. Switching environments is a one-line change. This mirrors how real NVIDIA infrastructure uses Terraform to target different hypervisors.

**2. Connection-agnostic Ansible:** `ansible_connection=docker` (Mac) vs `ansible_connection=ssh` (KVM) is set in inventory only. All roles and playbooks are identical. Idempotent — re-run any playbook to correct node drift.

**3. Containerized test workloads:** Same `cuda-test` container image runs on any node. Config comes in as arguments, results come out as JSON. This is exactly how a real GPU validation farm scales across hundreds of GPU types and CUDA versions.

**4. Three build systems, one container:** The Dockerfile compiles cmake, autoconf, and meson tools in one image. This demonstrates hands-on experience with all three build systems that the NVIDIA JD lists as a stand-out skill.

---

## Sample Report Output

```
========================================================
  GPU TEST FARM — EXECUTION REPORT
  Generated: 2026-04-19 10:32:15 UTC
========================================================

  [✓] H100 / CUDA 13.0  (node: gpu-node-1)
      Overall: PASS  |  3/3 tests passed
        ✓ cuda_math_validator          PASS  (0.002s)
        ✓ cuda_version_checker         PASS  (0.001s)
        ✓ cuda_stress_runner           PASS  (0.312s)

  [✓] A100 / CUDA 12.8  (node: gpu-node-2)
      Overall: PASS  |  2/2 tests passed
        ✓ cuda_math_validator          PASS  (0.001s)
        ✓ cuda_version_checker         PASS  (0.001s)

========================================================
  Total configs tested : 2
  Total test cases     : 5
  Passed               : 5
  Failed               : 0
  Pass rate            : 100.0%
========================================================
```

---

## Interview Talking Points

> "I built a miniature GPU test farm provisioner to get hands-on experience with the exact stack in the JD — KVM, Ansible, Docker, and Terraform. It provisions nodes via Terraform (Docker on Mac, swappable to KVM/libvirt for Linux), configures them with Ansible roles (idempotent CUDA stub, Docker install), and runs test workloads in containers. The Docker image compiles three C validation tools — one each with cmake, autoconf, and meson — so I have firsthand experience with all three build systems. The Python orchestrator dispatches jobs across nodes, collects JSON results, and generates a summary report. Same architecture as a real GPU validation farm, just miniaturized."

---

## Tags

`ansible` `docker` `kvm` `terraform` `test-automation` `cuda` `ci-cd` `cmake` `autoconf` `meson` `gpu`
