# GPU Test Farm Provisioner — Makefile (Mac variant, Docker Desktop)
# First time: ./setup.sh && source .venv/bin/activate
# Full workflow: make all
# Tear down:    make clean

.PHONY: all setup infra-up configure build test report clean help

MATRIX    := docker/test_matrix.json
RESULTS   := results
INVENTORY := ansible/inventory/hosts.yml
PYTHON    := $(shell [ -f .venv/bin/python3 ] && echo .venv/bin/python3 || echo python3)

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install all dependencies (Terraform, Ansible, Python venv)
	bash setup.sh

infra-up: ## Provision node containers via Terraform
	@echo "==> Provisioning GPU test nodes..."
	@mkdir -p results/node-1 results/node-2
	cd terraform && terraform init -upgrade -input=false
	cd terraform && terraform apply -auto-approve
	@echo "==> Nodes running:"
	@docker ps --filter "name=gpu-node" --format "  {{.Names}}\t{{.Status}}"

configure: ## Configure nodes with Ansible (cuda_stub, docker, test_runner roles)
	@echo "==> Configuring GPU test nodes with Ansible..."
	cd ansible && ansible-playbook -i inventory/hosts.yml playbooks/setup_node.yml

build: ## Build the CUDA test workload container
	@echo "==> Building cuda-test container..."
	cd docker && docker build -t cuda-test:latest -f Dockerfile.cuda-test .
	@echo "==> Saving image tarball for node deployment..."
	docker save cuda-test:latest -o docker/cuda-test.tar

test: ## Run test matrix across all nodes
	@echo "==> Running test matrix..."
	@mkdir -p $(RESULTS)
	$(PYTHON) scripts/orchestrate.py --matrix $(MATRIX) --results-dir $(RESULTS)

report: ## Generate aggregated test report
	@echo ""
	$(PYTHON) scripts/generate_report.py --results-dir $(RESULTS)

all: infra-up configure build test report ## Full workflow: provision → configure → build → test → report

clean: ## Tear down nodes and clean results
	@echo "==> Destroying GPU test nodes..."
	cd terraform && terraform destroy -auto-approve || true
	@echo "==> Cleaning results..."
	rm -rf $(RESULTS)
	@echo "==> Done."

# Convenience targets
nodes-status: ## Show status of GPU test nodes
	@docker ps --filter "name=gpu-node" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

nodes-down: ## Stop and remove node containers without destroying Terraform state
	docker rm -f gpu-node-1 gpu-node-2 2>/dev/null || true

verify: ## Quick smoke test of the CUDA test container
	@echo "==> Smoke testing cuda-test container..."
	mkdir -p /tmp/gpu-farm-smoke
	docker run --rm -v /tmp/gpu-farm-smoke:/results cuda-test:latest \
		--gpu H100 --cuda 13.0 --suite cublas_regression
	@echo "==> Smoke test complete. Results:"
	@cat /tmp/gpu-farm-smoke/*.json 2>/dev/null | python3 -m json.tool || true
