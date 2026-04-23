#!/usr/bin/env bash
# clean.sh — Remove generated training artifacts to free disk space
#
# Keeps: training/venv/, training/data/ (downloaded external data),
#        training/configs/, training/scripts/, training/requirements-training.txt
# Removes: training/out/ (generated WAVs + NPYs + trained ONNX)
#           *.manifest.json sidecar files
#
# Usage:
#   bash training/scripts/clean.sh              # dry-run by default (prints what would be removed)
#   bash training/scripts/clean.sh --confirm    # actually delete
#   bash training/scripts/clean.sh --all        # also remove training/data/ (re-download required)
#   bash training/scripts/clean.sh --all --confirm

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="$PROJECT_ROOT/training/out"
DATA_DIR="$PROJECT_ROOT/training/data"
CONFIGS_DIR="$PROJECT_ROOT/training/configs"

CONFIRM=false
CLEAN_ALL=false

for arg in "$@"; do
  case "$arg" in
    --confirm)  CONFIRM=true ;;
    --all)      CLEAN_ALL=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

echo "=== clean.sh ==="
echo "Project root : $PROJECT_ROOT"
echo "Confirm      : $CONFIRM"
echo "Clean all    : $CLEAN_ALL (includes training/data/ if true)"
echo ""

if ! $CONFIRM; then
  echo "[DRY-RUN] Pass --confirm to actually delete files."
  echo ""
fi

# -- training/out/ ------------------------------------------------------------
if [ -d "$OUT_DIR" ]; then
  OUT_SIZE=$(du -sh "$OUT_DIR" 2>/dev/null | cut -f1)
  echo "  training/out/  : $OUT_SIZE"
  if $CONFIRM; then
    rm -rf "$OUT_DIR"
    echo "  Deleted training/out/"
  else
    echo "  [DRY-RUN] Would delete: $OUT_DIR"
  fi
else
  echo "  training/out/  : (not present)"
fi

# -- manifest sidecar files ---------------------------------------------------
MANIFESTS=$(find "$CONFIGS_DIR" -name "*.manifest.json" 2>/dev/null || true)
if [ -n "$MANIFESTS" ]; then
  echo ""
  echo "  Manifest files:"
  echo "$MANIFESTS" | while read -r f; do
    echo "    $f"
    if $CONFIRM; then
      rm -f "$f"
    fi
  done
  if $CONFIRM; then
    echo "  Deleted manifest files"
  else
    echo "  [DRY-RUN] Would delete manifest files"
  fi
fi

# -- training/data/ (only with --all) ----------------------------------------
if $CLEAN_ALL; then
  echo ""
  if [ -d "$DATA_DIR" ]; then
    DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1)
    echo "  training/data/ : $DATA_SIZE"
    if $CONFIRM; then
      rm -rf "$DATA_DIR"
      echo "  Deleted training/data/"
      echo "  WARNING: You must re-run data_bootstrap.sh before training again."
    else
      echo "  [DRY-RUN] Would delete: $DATA_DIR"
      echo "  WARNING: This would require re-downloading ~10+ GB of data."
    fi
  else
    echo "  training/data/ : (not present)"
  fi
fi

echo ""
echo "=== clean.sh done ==="
if ! $CONFIRM; then
  echo "Re-run with --confirm to perform the deletion."
fi
