#!/usr/bin/env bash
# piper_bootstrap.sh — Downloads and verifies the piper-tts runtime voice model
# This is the ONNX runtime voice (en_US-lessac-medium) used by Roamin's TTS engine.
# It is DISTINCT from the LibriTTS-R .pt generator model used by piper-sample-generator.
#
# Run from project root: bash training/setup/piper_bootstrap.sh [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/training/venv/bin/python"

MODEL_DIR="$HOME/.local/share/piper/models"
MODEL_BASE="en_US-lessac-medium"
ONNX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
ONNX_FILE="$MODEL_DIR/${MODEL_BASE}.onnx"
JSON_FILE="$MODEL_DIR/${MODEL_BASE}.onnx.json"
# SHA256 of en_US-lessac-medium.onnx — recorded at §0.4
EXPECTED_SHA256="5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f"

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

run() {
  if $DRY_RUN; then echo "[DRY-RUN] $*"; else echo "+ $*"; "$@"; fi
}

echo "=== piper_bootstrap.sh ==="
echo "Model dir : $MODEL_DIR"
echo "Dry-run   : $DRY_RUN"
echo ""

# Create model directory
run mkdir -p "$MODEL_DIR"

# Download ONNX model (idempotent)
if [ -f "$ONNX_FILE" ]; then
  echo "ONNX model already exists — skipping download"
else
  echo ">>> Downloading $MODEL_BASE.onnx ..."
  run wget -q --show-progress --https-only "$ONNX_URL" -O "$ONNX_FILE"
fi

# Download JSON config (idempotent)
if [ -f "$JSON_FILE" ]; then
  echo "JSON config already exists — skipping download"
else
  echo ">>> Downloading $MODEL_BASE.onnx.json ..."
  run wget -q --show-progress --https-only "$JSON_URL" -O "$JSON_FILE"
fi

# SHA256 verification
if ! $DRY_RUN; then
  ACTUAL_SHA=$(sha256sum "$ONNX_FILE" | cut -d' ' -f1)
  if [ "$EXPECTED_SHA256" = "FILL_IN_AT_S0_4" ]; then
    echo "SHA256 (record this in EXPECTED_SHA256 at §0.4): $ACTUAL_SHA"
  elif [ "$ACTUAL_SHA" != "$EXPECTED_SHA256" ]; then
    echo "ERROR: SHA256 mismatch for $ONNX_FILE"
    echo "  Expected : $EXPECTED_SHA256"
    echo "  Actual   : $ACTUAL_SHA"
    echo "  Delete the file and re-run this script."
    exit 1
  else
    echo "Checksum OK: $ACTUAL_SHA"
  fi
fi

# Sanity test — generate a test WAV using piper
echo ""
echo ">>> Running piper sanity test..."
SANITY_WAV="/tmp/piper_sanity_$$.wav"

if ! $DRY_RUN; then
  if ! command -v piper &>/dev/null; then
    # Try from venv
    PIPER_CMD="$PROJECT_ROOT/training/venv/bin/piper"
    if [ ! -f "$PIPER_CMD" ]; then
      echo "WARNING: piper command not found. Run wsl_bootstrap.sh first."
    fi
  else
    PIPER_CMD="piper"
  fi

  echo "hey roamin" | "$PIPER_CMD" \
    --model "$ONNX_FILE" \
    --output_file "$SANITY_WAV" 2>/dev/null

  if [ ! -f "$SANITY_WAV" ]; then
    echo "ERROR: Sanity WAV was not produced."
    exit 1
  fi

  SIZE=$(stat -c%s "$SANITY_WAV" 2>/dev/null || echo 0)
  if [ "$SIZE" -lt 10240 ]; then
    echo "ERROR: Sanity WAV is too small (${SIZE} bytes < 10 KB). Piper may have failed."
    rm -f "$SANITY_WAV"
    exit 1
  fi

  echo "Sanity WAV OK: ${SIZE} bytes at $SANITY_WAV"
  rm -f "$SANITY_WAV"
fi

echo ""
echo "=== piper_bootstrap.sh complete ==="
echo "Next step: bash training/setup/data_bootstrap.sh"
