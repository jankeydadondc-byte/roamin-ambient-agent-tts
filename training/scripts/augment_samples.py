#!/usr/bin/env python3
"""
augment_samples.py — Stage 2 wrapper: calls OWW --augment_clips
Reads the YAML config and invokes:
    python -m openwakeword.train --training_config <yaml> --augment_clips

Requires:
  - Stage 1 (generate_samples.py) must have run first
  - Background WAVs in training/data/background/ (from data_bootstrap.sh)
  - RIR WAVs in training/data/rir/ (from data_bootstrap.sh)

Features:
  - Pre-flight checks: verifies background/ and rir/ directories are non-empty
  - Manifest-backed: marks augmentation complete so re-runs are idempotent
  - --dry-run: print without executing

Usage (from project root inside training/venv):
    python training/scripts/augment_samples.py --config training/configs/hey_roamin.yaml
    python training/scripts/augment_samples.py --config training/configs/hey_roamin.yaml --dry-run
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
    "background_paths",
    "rir_paths",
    "augmentation_rounds",
    "feature_data_files",
    "false_positive_validation_data_path",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OWW Stage 2: augment clips with background + RIR")
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


def preflight_checks(cfg: dict) -> None:
    """Verify background and RIR directories have audio files."""
    errors = []

    bg_paths = cfg.get("background_paths", [])
    for bg in bg_paths:
        bg_dir = PROJECT_ROOT / bg
        wavs = list(bg_dir.glob("*.wav")) if bg_dir.is_dir() else []
        if len(wavs) < 10:
            errors.append(
                f"ERROR: Background dir '{bg}' has only {len(wavs)} WAV(s) — need ≥ 10.\n"
                f"       Run training/setup/data_bootstrap.sh to download FMA background audio."
            )
        else:
            print(f"  Background : {bg_dir} — {len(wavs)} WAVs ✓")

    rir_paths = cfg.get("rir_paths", [])
    for rir in rir_paths:
        rir_dir = PROJECT_ROOT / rir
        wavs = list(rir_dir.glob("*.wav")) if rir_dir.is_dir() else []
        if len(wavs) == 0:
            print(
                f"  WARNING: RIR dir '{rir}' has no WAVs — augmentation will skip room simulation.\n"
                f"           Run training/setup/data_bootstrap.sh to download MIT RIR Survey."
            )
        else:
            print(f"  RIR        : {rir_dir} — {len(wavs)} WAVs ✓")

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


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    mpath = manifest_path(config_path)
    manifest = load_manifest(mpath)
    model_name = cfg["model_name"]

    print("=== augment_samples.py ===")
    print(f"  Config          : {config_path}")
    print(f"  Model           : {model_name}")
    print(f"  Aug rounds      : {cfg.get('augmentation_rounds', '?')}")
    print(f"  Dry-run         : {args.dry_run}")
    print()

    if not manifest.get("completed"):
        print(
            "WARNING: generate_samples.py manifest does not show Stage 1 complete.\n"
            "         Proceeding anyway — OWW will error if WAVs are missing.\n"
        )

    if manifest.get("augment_completed"):
        print(f"Manifest shows augmentation already complete for {model_name}. " f"Delete {mpath.name} to re-run.")
        return

    if not args.dry_run:
        preflight_checks(cfg)

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
        "--augment_clips",
        "--overwrite",  # always recompute features; prevents stale NPYs from aborted runs
    ]

    if args.dry_run:
        print(f"[DRY-RUN] Would run:\n  {' '.join(cmd)}")
        return

    print(f"+ Running: {' '.join(cmd)}")
    print(
        "  (OWW will mix WAVs with background + RIR and write feature NPY files;\n"
        "   this may take 20-60 minutes depending on augmentation_rounds)"
    )
    print()

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        sys.exit(
            f"\nERROR: openwakeword.train --augment_clips exited with code {result.returncode}\n"
            f"       Check output above for details.\n"
            f"       The manifest was NOT updated — re-running will retry."
        )

    manifest["augment_completed"] = True
    save_manifest(mpath, manifest)
    print(f"\nAugmentation complete. Manifest updated: {mpath}")
    print(f"Next step: python training/scripts/train_model.py --config {args.config}")


if __name__ == "__main__":
    main()
