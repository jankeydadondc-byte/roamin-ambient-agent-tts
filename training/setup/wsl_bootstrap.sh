#!/usr/bin/env bash
# wsl_bootstrap.sh — Idempotent training environment setup
# Installs Python 3.12 venv + PyTorch CUDA 12.6 + OpenWakeWord + piper-sample-generator
# Run inside WSL2 Ubuntu 24.04 from the project root:
#   bash training/setup/wsl_bootstrap.sh [--dry-run] [--uninstall]
#
# Environment: Ubuntu 24.04 LTS, Python 3.12, NVIDIA driver ≥ 550, CUDA 13.x passthrough

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PROJECT_ROOT/training/venv"
PIPER_MODEL_DIR="$PROJECT_ROOT/training/data/piper_models"
PIPER_PT_URL="https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt"
PIPER_PT_FILE="$PIPER_MODEL_DIR/en_US-libritts_r-medium.pt"
# SHA256 recorded at §0.2 — placeholder until validated
PIPER_PT_SHA256="e95ee53770bf598c354a6e6dbfc95ccb259aeeb501d35a86be8a767429ab0ff6"

DRY_RUN=false
UNINSTALL=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=true ;;
    --uninstall) UNINSTALL=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

run() {
  if $DRY_RUN; then
    echo "[DRY-RUN] $*"
  else
    echo "+ $*"
    "$@"
  fi
}

echo "=== wsl_bootstrap.sh ==="
echo "Project root : $PROJECT_ROOT"
echo "Venv         : $VENV_DIR"
echo "Dry-run      : $DRY_RUN"
echo ""

# -- Uninstall mode -------------------------------------------------------
if $UNINSTALL; then
  echo "Removing training venv and piper model..."
  run rm -rf "$VENV_DIR"
  run rm -rf "$PIPER_MODEL_DIR"
  echo "Done."
  exit 0
fi

# -- Prerequisite checks --------------------------------------------------
echo ">>> Checking prerequisites..."

# Must be inside WSL2
if ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "ERROR: This script must be run inside WSL2, not on Windows directly."
  exit 1
fi

# Must be Ubuntu 24.04
if ! grep -q "24.04" /etc/os-release 2>/dev/null; then
  echo "WARNING: Expected Ubuntu 24.04 but /etc/os-release shows a different version."
  echo "         Continuing anyway — check docs/WAKE_WORD_TRAINING.md if issues arise."
fi

# GPU passthrough check
if ! nvidia-smi &>/dev/null; then
  echo "ERROR: nvidia-smi not found. NVIDIA GPU passthrough is not working."
  echo "       See 'Prerequisites' in docs/WAKE_WORD_TRAINING.md for setup instructions."
  exit 1
fi
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'detected')"

# Python 3.12 check
if ! python3.12 --version &>/dev/null; then
  echo "ERROR: python3.12 not found. On Ubuntu 24.04 it should be pre-installed."
  echo "       Try: sudo apt-get install -y python3.12 python3.12-venv python3.12-dev"
  exit 1
fi
echo "Python: $(python3.12 --version)"

# -- System packages ------------------------------------------------------
echo ""
echo ">>> Checking system packages (sudo skipped — install manually if missing)..."
for cmd in git wget ffmpeg tmux python3.12; do
  if command -v "$cmd" &>/dev/null; then
    echo "  $cmd : OK"
  else
    echo "  WARNING: $cmd not found — if later steps fail, run:"
    echo "    sudo apt-get install -y python3.12-venv python3.12-dev build-essential git wget ffmpeg tmux libsndfile1 libffi-dev pkg-config"
  fi
done

# -- Create venv ----------------------------------------------------------
echo ""
echo ">>> Creating training venv at $VENV_DIR..."
if [ ! -d "$VENV_DIR" ]; then
  run python3.12 -m venv "$VENV_DIR"
else
  echo "Venv already exists — skipping creation"
fi

VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python"

# -- Upgrade pip/setuptools/wheel ----------------------------------------
echo ""
echo ">>> Upgrading pip/setuptools/wheel..."
run "$VENV_PIP" install --upgrade pip setuptools wheel

# -- PyTorch (CUDA 12.6) --------------------------------------------------
echo ""
echo ">>> Installing PyTorch with CUDA 12.6..."
run "$VENV_PIP" install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu126

# -- Training requirements ------------------------------------------------
echo ""
echo ">>> Installing openwakeword (--no-deps to skip tflite-runtime, no Python 3.12 wheel)..."
run "$VENV_PIP" install openwakeword --no-deps
# Install openwakeword's non-tflite deps manually
run "$VENV_PIP" install "scipy>=1.3,<2" "scikit-learn>=1,<2" requests "onnxruntime>=1.10.0,<2"

echo ""
echo ">>> Installing training requirements..."
run "$VENV_PIP" install -r "$PROJECT_ROOT/training/requirements-training.txt"

# -- piper-sample-generator model -----------------------------------------
echo ""
echo ">>> Downloading piper-sample-generator voice model (.pt)..."
run mkdir -p "$PIPER_MODEL_DIR"

if [ -f "$PIPER_PT_FILE" ]; then
  echo "Model already exists at $PIPER_PT_FILE — verifying checksum..."
else
  run wget -q --show-progress "$PIPER_PT_URL" -O "$PIPER_PT_FILE"
fi

# Checksum verification (skip if placeholder not yet filled)
if [ "$PIPER_PT_SHA256" != "FILL_IN_AT_S0_2" ] && ! $DRY_RUN; then
  ACTUAL_SHA=$(sha256sum "$PIPER_PT_FILE" | cut -d' ' -f1)
  if [ "$ACTUAL_SHA" != "$PIPER_PT_SHA256" ]; then
    echo "ERROR: SHA256 mismatch for $PIPER_PT_FILE"
    echo "  Expected : $PIPER_PT_SHA256"
    echo "  Actual   : $ACTUAL_SHA"
    echo "  Delete the file and re-run this script."
    exit 1
  fi
  echo "Checksum OK: $ACTUAL_SHA"
elif ! $DRY_RUN; then
  ACTUAL_SHA=$(sha256sum "$PIPER_PT_FILE" | cut -d' ' -f1)
  echo "SHA256 (record this in PIPER_PT_SHA256): $ACTUAL_SHA"
fi

# -- GPU verification -----------------------------------------------------
echo ""
echo ">>> Verifying CUDA is accessible from Python..."
if ! $DRY_RUN; then
  "$VENV_PYTHON" -c "
import torch
if not torch.cuda.is_available():
    print('ERROR: torch.cuda.is_available() returned False')
    print('Check NVIDIA driver and CUDA passthrough setup.')
    raise SystemExit(1)
print(f'CUDA OK: {torch.cuda.get_device_name(0)} | torch {torch.__version__}')
"
fi

# -- Version summary ------------------------------------------------------
echo ""
echo ">>> Installed package versions:"
if ! $DRY_RUN; then
  "$VENV_PIP" show torch openwakeword speechbrain onnxruntime-gpu 2>/dev/null \
    | grep -E "^(Name|Version):" | paste - -
fi

echo ""
echo "=== wsl_bootstrap.sh complete ==="
echo "Next step: bash training/setup/piper_bootstrap.sh"
