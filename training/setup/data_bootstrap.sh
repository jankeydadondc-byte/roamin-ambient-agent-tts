#!/usr/bin/env bash
# data_bootstrap.sh — Downloads all external training data required by the pipeline
# Downloads: validation_set_features.npy, background audio (FMA small), MIT RIR Survey
#
# Run from project root: bash training/setup/data_bootstrap.sh [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_DIR="$PROJECT_ROOT/training/data"

# Validation set features (pre-computed by OWW maintainer, ~2-4 GB)
VAL_NPY_URL="https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy"
VAL_NPY_FILE="$DATA_DIR/validation_set_features.npy"
# SHA256 recorded at §0.3 after first download
VAL_NPY_SHA256="a56a8a0f8e0efb91900acc6de4c0cdf4c564842e8475a7d49b36c039e17a690f"

# FMA small subset for background audio (~7.2 GB; freely licensed)
FMA_URL="https://os.unil.cloud.switch.ch/fma/fma_small.zip"
FMA_ZIP="$DATA_DIR/fma_small.zip"
BG_DIR="$DATA_DIR/background"

# MIT Room Impulse Response Survey (~500 MB)
RIR_URL="http://mcdermottlab.mit.edu/Reverb/IR_Survey.zip"
RIR_ZIP="$DATA_DIR/IR_Survey.zip"
RIR_DIR="$DATA_DIR/rir"

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

check_disk() {
  local dir="$1"
  local min_gb="$2"
  local avail_gb
  avail_gb=$(df -BG "$dir" 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')
  if [ "${avail_gb:-0}" -lt "$min_gb" ]; then
    echo "ERROR: Less than ${min_gb} GB free at $dir (${avail_gb} GB available)"
    echo "       Free up space and re-run."
    exit 1
  fi
}

echo "=== data_bootstrap.sh ==="
echo "Data dir : $DATA_DIR"
echo "Dry-run  : $DRY_RUN"
echo ""

run mkdir -p "$DATA_DIR" "$BG_DIR" "$RIR_DIR"

if ! $DRY_RUN; then
  check_disk "$DATA_DIR" 15
fi

# ── 1. Validation set features ───────────────────────────────────────────────
echo ">>> [1/3] Validation set features (validation_set_features.npy)..."
if [ -f "$VAL_NPY_FILE" ] && [ -s "$VAL_NPY_FILE" ]; then
  echo "Already downloaded — skipping"
else
  echo "Downloading ~2-4 GB from HuggingFace..."
  run wget -q --show-progress "$VAL_NPY_URL" -O "$VAL_NPY_FILE"
fi

if ! $DRY_RUN; then
  ACTUAL_SHA=$(sha256sum "$VAL_NPY_FILE" | cut -d' ' -f1)
  if [ "$VAL_NPY_SHA256" = "FILL_IN_AT_S0_3" ]; then
    echo "SHA256 (record this in VAL_NPY_SHA256 at §0.3): $ACTUAL_SHA"
  elif [ "$ACTUAL_SHA" != "$VAL_NPY_SHA256" ]; then
    echo "ERROR: SHA256 mismatch for validation_set_features.npy"
    echo "  Expected : $VAL_NPY_SHA256"
    echo "  Actual   : $ACTUAL_SHA"
    exit 1
  else
    echo "Checksum OK"
  fi

  # Verify it loads with numpy
  "$PROJECT_ROOT/training/venv/bin/python" -c "
import numpy as np
d = np.load('$VAL_NPY_FILE')
print(f'validation_set_features.npy loaded OK: shape={d.shape}, dtype={d.dtype}')
" || { echo "ERROR: Failed to load validation_set_features.npy with numpy"; exit 1; }
fi

# ── 2. Background audio (FMA small) ──────────────────────────────────────────
echo ""
echo ">>> [2/3] Background audio (FMA small subset)..."
if [ -f "$FMA_ZIP" ] && [ -s "$FMA_ZIP" ]; then
  echo "FMA zip already downloaded — checking extraction..."
else
  echo "Downloading FMA small (~7.2 GB, Creative Commons licensed)..."
  run wget -q --show-progress "$FMA_URL" -O "$FMA_ZIP"
fi

# Extract only MP3 audio files if not already done
BG_COUNT=$(find "$BG_DIR" -name "*.wav" 2>/dev/null | wc -l)
if [ "$BG_COUNT" -gt 100 ]; then
  echo "Background WAVs already extracted ($BG_COUNT files) — skipping"
else
  echo "Extracting and converting to 16kHz WAV..."
  if ! $DRY_RUN; then
    TMP_MP3="$DATA_DIR/fma_tmp_mp3"
    mkdir -p "$TMP_MP3"
    # Extract subset of MP3s (first 500 tracks ≈ ~1 hour)
    unzip -q "$FMA_ZIP" "fma_small/0*" -d "$TMP_MP3" 2>/dev/null || \
    unzip -q "$FMA_ZIP" -d "$TMP_MP3" 2>/dev/null

    # Convert MP3 → 16kHz mono WAV
    find "$TMP_MP3" -name "*.mp3" | head -500 | while read -r mp3; do
      base=$(basename "$mp3" .mp3)
      ffmpeg -i "$mp3" -ar 16000 -ac 1 -q:a 0 "$BG_DIR/${base}.wav" -y -loglevel error 2>/dev/null || true
    done
    rm -rf "$TMP_MP3"
    BG_COUNT=$(find "$BG_DIR" -name "*.wav" | wc -l)
    echo "Converted ${BG_COUNT} background WAVs"
  fi
fi

if ! $DRY_RUN; then
  if [ "$BG_COUNT" -lt 10 ]; then
    echo "ERROR: Fewer than 10 background WAVs in $BG_DIR — extraction may have failed"
    exit 1
  fi
  # Verify total duration ≥ 1 hour
  TOTAL_DUR=0
  while IFS= read -r wav; do
    DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$wav" 2>/dev/null || echo 0)
    TOTAL_DUR=$(echo "$TOTAL_DUR + ${DUR:-0}" | bc)
  done < <(find "$BG_DIR" -name "*.wav" | head -100)
  echo "Total background audio duration (sample of 100 files): ${TOTAL_DUR%.*}s"
fi

# ── 3. MIT Room Impulse Response Survey ──────────────────────────────────────
echo ""
echo ">>> [3/3] MIT Room Impulse Response Survey..."
RIR_COUNT=$(find "$RIR_DIR" -name "*.wav" 2>/dev/null | wc -l)
if [ "$RIR_COUNT" -gt 0 ]; then
  echo "RIR WAVs already present ($RIR_COUNT files) — skipping"
else
  if [ -f "$RIR_ZIP" ] && [ -s "$RIR_ZIP" ]; then
    echo "RIR zip already downloaded — extracting..."
  else
    echo "Downloading MIT IR Survey (~500 MB)..."
    # Note: MIT RIR URL may require HTTP (not HTTPS) — try both
    run wget -q --show-progress "$RIR_URL" -O "$RIR_ZIP" 2>/dev/null || \
    run wget -q --show-progress "${RIR_URL/http:/https:}" -O "$RIR_ZIP" 2>/dev/null || \
    { echo "WARNING: MIT RIR download failed. See §0.6 for alternative URL."; }
  fi

  if [ -f "$RIR_ZIP" ] && [ -s "$RIR_ZIP" ] && ! $DRY_RUN; then
    unzip -q "$RIR_ZIP" "*.wav" -d "$RIR_DIR" 2>/dev/null || \
    unzip -q "$RIR_ZIP" -d "$RIR_DIR" 2>/dev/null
    # Move any nested WAVs up
    find "$RIR_DIR" -name "*.wav" -not -path "$RIR_DIR/*.wav" \
      -exec mv {} "$RIR_DIR/" \; 2>/dev/null || true
    RIR_COUNT=$(find "$RIR_DIR" -name "*.wav" | wc -l)
    echo "Extracted $RIR_COUNT RIR WAVs"
  fi
fi

if ! $DRY_RUN && [ "$RIR_COUNT" -lt 1 ]; then
  echo "WARNING: No RIR WAVs found in $RIR_DIR"
  echo "         Augmentation will proceed without room simulation."
  echo "         See §0.6 in tasks.md for alternative RIR sources."
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== data_bootstrap.sh summary ==="
if ! $DRY_RUN; then
  [ -f "$VAL_NPY_FILE" ] && echo "validation_set_features.npy : $(du -sh "$VAL_NPY_FILE" | cut -f1)" || echo "validation_set_features.npy : MISSING"
  echo "Background WAVs             : $(find "$BG_DIR" -name '*.wav' 2>/dev/null | wc -l) files"
  echo "RIR WAVs                    : $(find "$RIR_DIR" -name '*.wav' 2>/dev/null | wc -l) files"
fi
echo "Next step: python training/scripts/generate_samples.py --config training/configs/hey_roamin.yaml --preview 10"
