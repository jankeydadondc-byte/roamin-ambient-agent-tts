#!/usr/bin/env python3
"""
compare_models.py — Compare new vs existing ONNX model and optionally deploy
Runs the new and existing models side-by-side against validation_set_features.npy
and prints a comparison table. If --deploy is passed (or --auto-deploy with a
better FP rate), copies the new model to models/wake_word/.

Usage (from project root inside training/venv):
    # Dry comparison only:
    python training/scripts/compare_models.py \
        --new training/out/hey_roamin.onnx \
        --existing models/wake_word/hey_roamin.onnx

    # Compare and deploy if new model wins:
    python training/scripts/compare_models.py \
        --new training/out/hey_roamin.onnx \
        --existing models/wake_word/hey_roamin.onnx \
        --auto-deploy

    # Force deploy without comparison (first-time install):
    python training/scripts/compare_models.py \
        --new training/out/hey_roamin.onnx \
        --existing models/wake_word/hey_roamin.onnx \
        --deploy
"""

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_VAL_NPY = "training/data/validation_set_features.npy"
DEFAULT_THRESHOLD = 0.5


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare new vs existing wake-word ONNX model")
    p.add_argument("--new", required=True, help="Path to newly trained .onnx")
    p.add_argument("--existing", required=True, help="Path to currently deployed .onnx")
    p.add_argument(
        "--val-npy",
        default=DEFAULT_VAL_NPY,
        help=f"Path to validation_set_features.npy (default: {DEFAULT_VAL_NPY})",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Activation threshold (default: {DEFAULT_THRESHOLD})",
    )
    p.add_argument(
        "--deploy",
        action="store_true",
        help="Always copy new model to --existing path after comparison",
    )
    p.add_argument(
        "--auto-deploy",
        action="store_true",
        help="Copy new model only if its FP/hr is ≤ existing model's FP/hr",
    )
    return p.parse_args()


def score_model(onnx_path: Path, val_data: np.ndarray, threshold: float) -> dict:
    """Run a model against val_data and return stats dict."""
    try:
        import onnxruntime as ort
    except ImportError:
        sys.exit("ERROR: 'onnxruntime' not installed.")

    sess_options = ort.SessionOptions()
    sess_options.log_severity_level = 3
    sess = ort.InferenceSession(
        str(onnx_path),
        sess_options=sess_options,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    inp_name = sess.get_inputs()[0].name
    out_name = sess.get_outputs()[0].name

    batch_size = 512
    n_samples = val_data.shape[0]
    scores = []

    for start in range(0, n_samples, batch_size):
        batch = val_data[start : start + batch_size].astype(np.float32)
        if batch.ndim == 1:
            batch = batch[np.newaxis, :]
        out = sess.run([out_name], {inp_name: batch})[0]
        scores.extend(out.flatten().tolist())

    scores_arr = np.array(scores)
    n_act = int((scores_arr >= threshold).sum())
    fp_per_hour = float(n_act)  # validation set ≈ 1 hour
    max_score = float(scores_arr.max())
    mean_score = float(scores_arr.mean())

    return {
        "n_samples": n_samples,
        "n_activations": n_act,
        "fp_per_hour": fp_per_hour,
        "max_score": max_score,
        "mean_score": mean_score,
        "size_kb": onnx_path.stat().st_size / 1024,
    }


def main() -> None:
    args = parse_args()
    new_path = Path(args.new).resolve()
    existing_path = Path(args.existing).resolve()
    val_npy_path = (PROJECT_ROOT / args.val_npy).resolve()

    print("=== compare_models.py ===")
    print(f"  New model      : {new_path}")
    print(f"  Existing model : {existing_path}")
    print(f"  Val NPY        : {val_npy_path}")
    print(f"  Threshold      : {args.threshold}")
    print()

    if not new_path.is_file():
        sys.exit(f"ERROR: New model not found: {new_path}")

    has_existing = existing_path.is_file()
    if not has_existing:
        print(f"  No existing model at {existing_path} — first-time install mode.")

    # Load validation data
    if not val_npy_path.is_file():
        print(
            f"  WARNING: {val_npy_path} not found — skipping numerical comparison.\n"
            f"           Run training/setup/data_bootstrap.sh first."
        )
        val_data = None
    else:
        print(f"  Loading {val_npy_path.name}...")
        val_data = np.load(str(val_npy_path))
        print(f"  Validation shape: {val_data.shape}")
        print()

    if val_data is not None:
        print("  Scoring new model...")
        new_stats = score_model(new_path, val_data, args.threshold)

        if has_existing:
            print("  Scoring existing model...")
            existing_stats = score_model(existing_path, val_data, args.threshold)
        else:
            existing_stats = None

        # Print comparison table
        print()
        print(f"  {'Metric':<28} {'New':>12} {'Existing':>12}")
        print(f"  {'-'*28} {'-'*12} {'-'*12}")
        metrics = [
            ("FP / hour", "fp_per_hour", ".2f"),
            ("Max activation score", "max_score", ".4f"),
            ("Mean activation score", "mean_score", ".6f"),
            ("File size (KB)", "size_kb", ".1f"),
            ("Activations ≥ thresh", "n_activations", "d"),
        ]
        for label, key, fmt in metrics:
            new_val = new_stats[key]
            ex_val = existing_stats[key] if existing_stats else "—"
            new_str = f"{new_val:{fmt}}"
            ex_str = f"{ex_val:{fmt}}" if existing_stats else "—"
            print(f"  {label:<28} {new_str:>12} {ex_str:>12}")

        print()
        new_fp = new_stats["fp_per_hour"]
        if existing_stats:
            ex_fp = existing_stats["fp_per_hour"]
            if new_fp < ex_fp:
                verdict = f"NEW is BETTER ({new_fp:.2f} < {ex_fp:.2f} FP/hr)"
            elif new_fp == ex_fp:
                verdict = f"EQUAL FP rate ({new_fp:.2f} FP/hr)"
            else:
                verdict = f"EXISTING is BETTER ({ex_fp:.2f} < {new_fp:.2f} FP/hr)"
            print(f"  Verdict: {verdict}")
        else:
            print(f"  New model FP/hr: {new_fp:.2f}")

        new_wins = (not existing_stats) or (new_stats["fp_per_hour"] <= existing_stats["fp_per_hour"])
    else:
        new_wins = True  # no data to compare, assume new is better
        new_fp = -1.0

    # Deploy decision
    should_deploy = args.deploy or (args.auto_deploy and new_wins)

    if not should_deploy and not has_existing:
        # First time — suggest deploy
        print()
        print("  First-time install: run with --deploy to copy to models/wake_word/")

    if should_deploy:
        # Ensure destination directory exists
        existing_path.parent.mkdir(parents=True, exist_ok=True)

        # Back up existing if present
        if has_existing:
            backup = existing_path.with_suffix(".onnx.bak")
            shutil.copy2(existing_path, backup)
            print(f"\n  Backed up existing model → {backup}")

        shutil.copy2(new_path, existing_path)
        size_kb = existing_path.stat().st_size / 1024
        print(f"  Deployed: {new_path.name} → {existing_path} ({size_kb:.1f} KB)")
    elif args.auto_deploy and not new_wins:
        print("\n  --auto-deploy: existing model has better FP rate — NOT replacing.")
    elif not args.deploy and not args.auto_deploy:
        print(
            f"\n  Pass --deploy to overwrite {existing_path.name},\n"
            f"  or --auto-deploy to deploy only if new model wins."
        )

    print()
    print("=== compare_models.py complete ===")
    if should_deploy:
        print(
            "  Next step: restart Roamin and run the integration smoke test (§13).\n"
            "  See docs/WAKE_WORD_TRAINING.md for test procedure."
        )


if __name__ == "__main__":
    main()
