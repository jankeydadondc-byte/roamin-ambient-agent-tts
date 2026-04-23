#!/usr/bin/env python3
"""
train_model.py — Stage 3 wrapper: calls OWW --train_model
Reads the YAML config and invokes:
    python -m openwakeword.train --training_config <yaml> --train_model

OWW auto_train() runs two sequences:
  Sequence 1: `steps` iterations with max_negative_weight ramped linearly 1 → max_negative_weight
  Sequence 2: steps/10 iterations at lr/10; doubles weight if fp_per_hour > target_false_positives_per_hour

IMPORTANT: OWW writes NO checkpoint files during training. If this process is
interrupted, training must restart from scratch (Stage 3 only — Stages 1 & 2
are preserved). Use nohup or tmux to guard against disconnects:
    tmux new -s train
    python training/scripts/train_model.py --config training/configs/hey_roamin.yaml

Output: training/out/hey_roamin.onnx  (or stop_roamin.onnx)

Features:
  - Pre-flight checks: verify feature NPY files exist (Stage 2 output)
  - Manifest-backed: marks training complete; ONNX path saved in manifest
  - --dry-run: print without executing

Usage (from project root inside training/venv):
    python training/scripts/train_model.py --config training/configs/hey_roamin.yaml
    python training/scripts/train_model.py --config training/configs/hey_roamin.yaml --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
REQUIRED_FIELDS = [
    "model_name",
    "output_dir",
    "steps",
    "max_negative_weight",
    "target_false_positives_per_hour",
    "feature_data_files",
    "false_positive_validation_data_path",
    "batch_n_per_class",
    "layer_size",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OWW Stage 3: train DNN model")
    p.add_argument("--config", required=True, help="Path to OWW YAML config")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command without executing",
    )
    return p.parse_args()


def load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        sys.exit(f"ERROR: Config not found: {config_path}")

    try:
        config_path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        sys.exit(f"ERROR: Config path escapes project root: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    if not isinstance(cfg, dict):
        sys.exit("ERROR: Config YAML did not parse as a dict")

    for field in REQUIRED_FIELDS:
        if field not in cfg:
            sys.exit(f"ERROR: Required field '{field}' missing from config")

    if not MODEL_NAME_RE.match(str(cfg["model_name"])):
        sys.exit(f"ERROR: model_name '{cfg['model_name']}' must match ^[a-zA-Z0-9_-]+$")

    return cfg


def manifest_path(config_path: Path) -> Path:
    return config_path.parent / (config_path.stem + ".manifest.json")


def load_manifest(mpath: Path) -> dict:
    if mpath.is_file():
        try:
            with mpath.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            print(f"WARNING: Could not read manifest {mpath} — starting fresh")
    return {}


def save_manifest(mpath: Path, data: dict) -> None:
    with mpath.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def preflight_checks(cfg: dict) -> Path:
    """Verify Stage 2 output (feature NPY files) and validation data exist."""
    model_name = cfg["model_name"]
    out_dir = PROJECT_ROOT / cfg["output_dir"]
    errors = []

    # OWW --augment_clips writes feature NPYs to output_dir/<model_name>/
    # Named: positive_features_train.npy, negative_features_train.npy, etc.
    model_out_dir = out_dir / model_name
    feature_files = list(model_out_dir.glob("*_features_*.npy")) if model_out_dir.is_dir() else []
    if len(feature_files) < 2:
        errors.append(
            f"ERROR: Expected ≥ 2 feature NPY files in {model_out_dir} (Stage 2 output).\n"
            f"       Found: {len(feature_files)}\n"
            f"       Run augment_samples.py first."
        )
    else:
        for f in feature_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  Feature NPY: {f.name} ({size_mb:.0f} MB) ✓")

    val_npy = PROJECT_ROOT / cfg["false_positive_validation_data_path"]
    if not val_npy.is_file():
        errors.append(
            f"ERROR: validation_set_features.npy not found at {val_npy}\n"
            f"       Run training/setup/data_bootstrap.sh first."
        )
    else:
        size_mb = val_npy.stat().st_size / (1024 * 1024)
        print(f"  Val NPY    : {val_npy.name} ({size_mb:.0f} MB) ✓")

    if errors:
        print()
        for e in errors:
            print(e)
        sys.exit(1)

    return out_dir


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    mpath = manifest_path(config_path)
    manifest = load_manifest(mpath)
    model_name = cfg["model_name"]
    steps = cfg["steps"]
    max_neg = cfg["max_negative_weight"]
    target_fp = cfg["target_false_positives_per_hour"]

    print("=== train_model.py ===")
    print(f"  Config                  : {config_path}")
    print(f"  Model                   : {model_name}")
    print(f"  Steps (Seq 1)           : {steps}")
    print(f"  Steps (Seq 2)           : {steps // 10}")
    print(f"  max_negative_weight     : {max_neg}")
    print(f"  target_fp_per_hour      : {target_fp}")
    print(f"  Dry-run                 : {args.dry_run}")
    print()
    print(
        "  NOTE: OWW writes no checkpoints. If training is interrupted,\n"
        "        Stage 3 must restart from scratch. Use tmux or nohup.\n"
    )

    if not manifest.get("augment_completed"):
        print(
            "WARNING: augment_samples.py manifest does not show Stage 2 complete.\n"
            "         Proceeding anyway — OWW will error if feature NPYs are missing.\n"
        )

    if manifest.get("train_completed"):
        onnx_path = manifest.get("onnx_path", "unknown")
        print(
            f"Manifest shows training already complete for {model_name}.\n"
            f"ONNX: {onnx_path}\n"
            f"Delete {mpath.name} to re-train."
        )
        return

    if not args.dry_run:
        out_dir = preflight_checks(cfg)
    else:
        out_dir = PROJECT_ROOT / cfg["output_dir"]

    venv_python = PROJECT_ROOT / "training" / "venv" / "bin" / "python"
    if not venv_python.is_file() and not args.dry_run:
        sys.exit(
            f"ERROR: Training venv Python not found at {venv_python}\n"
            "       Run training/setup/wsl_bootstrap.sh first."
        )

    cmd = [
        str(venv_python),
        "-m",
        "openwakeword.train",
        "--training_config",
        str(config_path),
        "--train_model",
    ]

    expected_onnx = out_dir / f"{model_name}.onnx"

    if args.dry_run:
        print(f"[DRY-RUN] Would run:\n  {' '.join(cmd)}")
        print(f"[DRY-RUN] Expected output: {expected_onnx}")
        return

    print(f"+ Running: {' '.join(cmd)}")
    print(
        f"  (Training {steps:,} steps + {steps // 10:,} fine-tune steps;\n"
        f"   estimated 2-6 hours on RTX 3090 — keep tmux session alive)\n"
    )

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        sys.exit(
            f"\nERROR: openwakeword.train --train_model exited with code {result.returncode}\n"
            f"       Check output above for details.\n"
            f"       The manifest was NOT updated — re-running will restart Stage 3."
        )

    # Verify ONNX was produced
    if not expected_onnx.is_file():
        sys.exit(
            f"\nERROR: Training reported success but ONNX not found at:\n"
            f"       {expected_onnx}\n"
            f"       Check output_dir and model_name in config."
        )

    size_mb = expected_onnx.stat().st_size / (1024 * 1024)
    print(f"\nONNX produced: {expected_onnx} ({size_mb:.1f} MB)")

    manifest["train_completed"] = True
    manifest["onnx_path"] = str(expected_onnx)
    save_manifest(mpath, manifest)
    print(f"Manifest updated: {mpath}")
    print(f"Next step: python training/scripts/verify_model.py --onnx {expected_onnx}")


if __name__ == "__main__":
    main()
