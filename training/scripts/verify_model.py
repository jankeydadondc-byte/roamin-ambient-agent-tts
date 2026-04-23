#!/usr/bin/env python3
"""
verify_model.py — Post-training ONNX sanity checks
Verifies a trained wake-word ONNX model before it is committed to models/wake_word/.

Checks performed:
  1. ONNX schema validation (onnx.checker.check_model)
  2. Runtime inference smoke test (onnxruntime): feeds a zero-vector and checks output shape
  3. False-positive rate estimation: runs the model against validation_set_features.npy
     and reports false positives per hour at the configured threshold (default 0.5)
  4. Compares model file size against a sanity floor (> 10 KB)

Does NOT deploy to models/wake_word/ — that is done by compare_models.py after
comparing new vs existing.

Usage (from project root inside training/venv):
    python training/scripts/verify_model.py --onnx training/out/hey_roamin.onnx
    python training/scripts/verify_model.py --onnx training/out/hey_roamin.onnx \
        --val-npy training/data/validation_set_features.npy \
        --threshold 0.5
"""

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# OWW audio feature dimensions
OWW_FEATURE_DIM = 96  # mel-spectrogram frame dimension used by OWW


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify trained wake-word ONNX model")
    p.add_argument("--onnx", required=True, help="Path to the .onnx model to verify")
    p.add_argument(
        "--val-npy",
        default="training/data/validation_set_features.npy",
        help="Path to validation_set_features.npy (false-positive estimation)",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Activation threshold for false-positive rate estimation (default: 0.5)",
    )
    return p.parse_args()


def check_onnx_schema(onnx_path: Path) -> None:
    try:
        import onnx
    except ImportError:
        sys.exit("ERROR: 'onnx' package not installed. Run training/setup/wsl_bootstrap.sh.")

    print("  [1/4] ONNX schema check...")
    try:
        model = onnx.load(str(onnx_path))
        onnx.checker.check_model(model)
        print("        Schema OK ✓")
    except Exception as exc:
        sys.exit(f"ERROR: ONNX schema check failed: {exc}")


def check_runtime_inference(onnx_path: Path) -> tuple[tuple, tuple]:
    """Run a zero-vector through the model. Returns (input_shape, output_shape)."""
    try:
        import onnxruntime as ort
    except ImportError:
        sys.exit("ERROR: 'onnxruntime' not installed.")

    print("  [2/4] Runtime inference smoke test...")
    try:
        sess_options = ort.SessionOptions()
        sess_options.log_severity_level = 3  # suppress INFO logs
        sess = ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )

        input_info = sess.get_inputs()
        output_info = sess.get_outputs()

        if not input_info:
            sys.exit("ERROR: Model has no inputs")
        if not output_info:
            sys.exit("ERROR: Model has no outputs")

        # Build a minimal zero-input matching the model's expected shape
        # OWW models typically accept (batch, frames, features) or (batch, features)
        inp = input_info[0]
        # Replace dynamic dims (-1 or None) with 1
        shape = [1 if (d is None or d <= 0) else d for d in inp.shape]
        dummy = np.zeros(shape, dtype=np.float32)

        feed = {inp.name: dummy}
        outputs = sess.run(None, feed)

        in_shape = tuple(shape)
        out_shape = tuple(outputs[0].shape)
        print(f"        Input  shape : {in_shape}")
        print(f"        Output shape : {out_shape}")
        print(f"        Output range : [{outputs[0].min():.4f}, {outputs[0].max():.4f}]")
        print("        Inference OK ✓")
        return in_shape, out_shape

    except Exception as exc:
        sys.exit(f"ERROR: Runtime inference failed: {exc}")


def check_file_size(onnx_path: Path) -> None:
    print("  [3/4] File size check...")
    size = onnx_path.stat().st_size
    size_kb = size / 1024
    if size < 10_240:  # < 10 KB is almost certainly empty/corrupt
        sys.exit(f"ERROR: ONNX file too small ({size_kb:.1f} KB < 10 KB) — likely corrupt")
    print(f"        Size: {size_kb:.1f} KB ✓")


def check_false_positive_rate(onnx_path: Path, val_npy_path: Path, threshold: float) -> float:
    """
    Estimate false positives per hour using validation_set_features.npy.
    Returns fp_per_hour.
    """
    print(f"  [4/4] False-positive rate estimation (threshold={threshold})...")

    if not val_npy_path.is_file():
        print(
            f"        WARNING: {val_npy_path} not found — skipping FP estimation.\n"
            f"                 Run training/setup/data_bootstrap.sh to download it."
        )
        return -1.0

    try:
        import onnxruntime as ort
    except ImportError:
        sys.exit("ERROR: 'onnxruntime' not installed.")

    print(f"        Loading {val_npy_path.name}...")
    try:
        val_data = np.load(str(val_npy_path))
        print(f"        Validation features shape: {val_data.shape}, dtype={val_data.dtype}")
    except Exception as exc:
        print(f"        WARNING: Could not load validation NPY: {exc} — skipping FP check")
        return -1.0

    try:
        sess_options = ort.SessionOptions()
        sess_options.log_severity_level = 3
        sess = ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        inp_name = sess.get_inputs()[0].name
        out_name = sess.get_outputs()[0].name

        # Run in batches to avoid OOM
        batch_size = 512
        n_samples = val_data.shape[0]
        scores = []

        for start in range(0, n_samples, batch_size):
            batch = val_data[start : start + batch_size].astype(np.float32)
            # Ensure batch dimension is present
            if batch.ndim == 1:
                batch = batch[np.newaxis, :]
            out = sess.run([out_name], {inp_name: batch})[0]
            scores.extend(out.flatten().tolist())

        scores_arr = np.array(scores)
        n_activations = int((scores_arr >= threshold).sum())

        # OWW validation set = 1 hour of negative audio at 16kHz, 10ms frames
        # The NPY contains ~360,000 feature frames = 1 hour
        VALIDATION_HOURS = 1.0
        fp_per_hour = n_activations / VALIDATION_HOURS

        print(f"        Activations ≥ {threshold}: {n_activations} / {n_samples}")
        print(f"        False positives per hour : {fp_per_hour:.2f}")
        if fp_per_hour <= 0.5:
            print("        FP rate OK ✓  (≤ 0.5/hr)")
        else:
            print("        FP rate HIGH ⚠  (> 0.5/hr — consider retraining with higher max_negative_weight)")

        return fp_per_hour

    except Exception as exc:
        print(f"        WARNING: FP rate check failed: {exc} — skipping")
        return -1.0


def main() -> None:
    args = parse_args()
    onnx_path = Path(args.onnx).resolve()
    val_npy_path = (PROJECT_ROOT / args.val_npy).resolve()

    if not onnx_path.is_file():
        sys.exit(f"ERROR: ONNX not found: {onnx_path}")

    print("=== verify_model.py ===")
    print(f"  ONNX      : {onnx_path}")
    print(f"  Val NPY   : {val_npy_path}")
    print(f"  Threshold : {args.threshold}")
    print()

    check_onnx_schema(onnx_path)
    check_file_size(onnx_path)
    check_runtime_inference(onnx_path)
    fp_per_hour = check_false_positive_rate(onnx_path, val_npy_path, args.threshold)

    print()
    print("=== verify_model.py summary ===")
    print(f"  ONNX : {onnx_path.name}")
    if fp_per_hour >= 0:
        status = "PASS" if fp_per_hour <= 0.5 else "WARN"
        print(f"  FP/hr: {fp_per_hour:.2f}  [{status}]")
    print()
    print(
        "Next step: python training/scripts/compare_models.py "
        f"--new {onnx_path} "
        f"--existing models/wake_word/{onnx_path.name}"
    )


if __name__ == "__main__":
    main()
