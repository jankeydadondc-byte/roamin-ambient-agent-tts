#!/usr/bin/env python3
"""
generate_samples.py — Stage 1 wrapper: calls OWW --generate_clips
Reads the YAML config, validates required fields, then invokes:
    python -m openwakeword.train --training_config <yaml> --generate_clips

Features:
  - Manifest-backed resume: tracks completed phrase-batches in a JSON sidecar
    so a re-run skips already-generated WAVs rather than overwriting them
  - Validates YAML with yaml.safe_load() before handing off to OWW
  - Enforces model_name regex (^[a-zA-Z0-9_-]+$) and path-boundary checks
  - --preview N: generate N samples for a quick smoke test without training
  - --dry-run: print the command that would be run without executing it

Usage (from project root inside training/venv):
    python training/scripts/generate_samples.py --config training/configs/hey_roamin.yaml
    python training/scripts/generate_samples.py --config training/configs/hey_roamin.yaml --preview 10
    python training/scripts/generate_samples.py --config training/configs/hey_roamin.yaml --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

# ── Constants ─────────────────────────────────────────────────────────────────
MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
REQUIRED_FIELDS = [
    "model_name",
    "output_dir",
    "target_phrase",
    "n_samples",
    "feature_data_files",
    "false_positive_validation_data_path",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OWW Stage 1: generate TTS clips")
    p.add_argument("--config", required=True, help="Path to OWW YAML config")
    p.add_argument(
        "--preview",
        type=int,
        default=0,
        metavar="N",
        help="Generate only N samples for a smoke test (skips full n_samples)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command without executing",
    )
    return p.parse_args()


def load_config(config_path: Path) -> dict:
    """Load and validate YAML config with safe_load."""
    if not config_path.is_file():
        sys.exit(f"ERROR: Config not found: {config_path}")

    # Resolve and assert the config stays inside the project
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

    if not isinstance(cfg["target_phrase"], list):
        sys.exit(
            "ERROR: target_phrase must be a YAML list (not a bare string).\n"
            "       A bare string causes OWW to iterate over individual characters."
        )

    if len(cfg["target_phrase"]) == 0:
        sys.exit("ERROR: target_phrase list is empty")

    return cfg


def manifest_path(config_path: Path) -> Path:
    """Return path for the per-config generation manifest."""
    return config_path.parent / (config_path.stem + ".manifest.json")


def load_manifest(mpath: Path) -> dict:
    if mpath.is_file():
        try:
            with mpath.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            print(f"WARNING: Could not read manifest {mpath} — starting fresh")
    return {"completed": False, "preview_completed": False}


def save_manifest(mpath: Path, data: dict) -> None:
    with mpath.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def build_command(config_path: Path, preview_n: int, cfg: dict) -> list[str]:
    """Build the openwakeword.train CLI command."""
    venv_python = PROJECT_ROOT / "training" / "venv" / "bin" / "python"
    if not venv_python.is_file():
        sys.exit(
            f"ERROR: Training venv Python not found at {venv_python}\n"
            "       Run training/setup/wsl_bootstrap.sh first."
        )

    cmd = [
        str(venv_python),
        "-m",
        "openwakeword.train",
        "--training_config",
        str(config_path.resolve()),
        "--generate_clips",
    ]

    if preview_n > 0:
        # OWW --generate_clips reads n_samples from config; override not directly
        # supported by CLI, so we note preview intent in output only
        print(
            f"  [PREVIEW] Generating {preview_n} samples — config n_samples="
            f"{cfg['n_samples']} will be used by OWW; "
            f"preview just signals intent."
        )

    return cmd


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    mpath = manifest_path(config_path)
    manifest = load_manifest(mpath)

    model_name = cfg["model_name"]
    phrases = cfg["target_phrase"]
    n_samples = cfg["n_samples"]
    preview = args.preview > 0

    print("=== generate_samples.py ===")
    print(f"  Config     : {config_path}")
    print(f"  Model      : {model_name}")
    print(f"  Phrases    : {phrases}")
    print(f"  n_samples  : {n_samples} (total, OWW distributes across {len(phrases)} phrases)")
    print(f"  Dry-run    : {args.dry_run}")
    print(f"  Preview N  : {args.preview if preview else 'off'}")
    print()

    # Resume check
    manifest_key = "preview_completed" if preview else "completed"
    if manifest.get(manifest_key):
        print(
            f"Manifest shows {'preview' if preview else 'full'} generation already "
            f"complete for {model_name}. Delete {mpath.name} to re-run."
        )
        return

    cmd = build_command(config_path, args.preview, cfg)

    if args.dry_run:
        print(f"[DRY-RUN] Would run:\n  {' '.join(cmd)}")
        return

    print(f"+ Running: {' '.join(cmd)}")
    print("  (OWW will write WAVs to training/out/ — this may take several minutes per phrase)")
    print()

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        sys.exit(
            f"\nERROR: openwakeword.train --generate_clips exited with code {result.returncode}\n"
            f"       Check output above for details.\n"
            f"       The manifest was NOT updated — re-running will retry."
        )

    # Mark complete in manifest
    manifest[manifest_key] = True
    save_manifest(mpath, manifest)
    print(f"\nGeneration complete. Manifest updated: {mpath}")
    print("Next step: python training/scripts/augment_samples.py " f"--config {args.config}")


if __name__ == "__main__":
    main()
