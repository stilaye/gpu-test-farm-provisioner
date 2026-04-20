#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  [✓]${NC} $*"; }
warn() { echo -e "${YELLOW}  [!]${NC} $*"; }
fail() { echo -e "${RED}  [✗]${NC} $*"; exit 1; }
info() { echo -e "  [→] $*"; }

echo "=============================================="
echo "  GPU Test Farm Provisioner — Setup"
echo "=============================================="

# ── Homebrew ───────────────────────────────────────
if ! command -v brew &>/dev/null; then
  warn "Homebrew not found. Installing..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
ok "Homebrew"

# ── Terraform ──────────────────────────────────────
if ! command -v terraform &>/dev/null; then
  info "Installing Terraform..."
  brew install terraform
fi
ok "Terraform $(terraform version -json | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])')"

# ── Ansible ────────────────────────────────────────
if ! command -v ansible &>/dev/null; then
  info "Installing Ansible..."
  brew install ansible
fi
ok "Ansible $(ansible --version | head -1 | awk '{print $3}' | tr -d ']')"

# ── Docker Desktop ─────────────────────────────────
if ! command -v docker &>/dev/null; then
  fail "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
fi
if ! docker info &>/dev/null 2>&1; then
  fail "Docker daemon not running. Please start Docker Desktop and re-run setup."
fi
ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

# ── Python venv ────────────────────────────────────
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
  info "Creating Python virtual environment at .venv..."
  python3 -m venv "$VENV_DIR"
fi
ok "Python venv (.venv)"

# ── pip install ────────────────────────────────────
info "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt
ok "Python packages (docker, paramiko, ansible)"

# ── results dir ────────────────────────────────────
mkdir -p results
ok "results/ directory"

echo ""
echo "=============================================="
echo "  Setup complete. Next steps:"
echo ""
echo "  Activate venv:   source .venv/bin/activate"
echo "  Full workflow:   make all"
echo "  Smoke test:      make verify"
echo "=============================================="
