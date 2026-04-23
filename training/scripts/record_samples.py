"""
Record real audio samples for wake word training.

Two modes:
  --mode positive   Record N clips of you saying "hey roamin" (one at a time,
                    with countdown). Saves to positive_train/.
  --mode ambient    Record M minutes of your ambient environment (no speaking),
                    auto-split into 2s clips. Saves to negative_train/.

Usage:
  python training/scripts/record_samples.py --mode positive --n 60
  python training/scripts/record_samples.py --mode ambient --minutes 5
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
CLIP_DURATION = 2.0  # seconds per positive clip
CLIP_SAMPLES = int(SAMPLE_RATE * CLIP_DURATION)

# Positive clips go here alongside synthetic ones
DEFAULT_POS_DIR = Path(__file__).parents[2] / "training" / "out" / "hey_roamin" / "positive_train"
# Ambient clips go here alongside existing negatives
DEFAULT_NEG_DIR = Path(__file__).parents[2] / "training" / "out" / "hey_roamin" / "negative_train"


def _save_wav(path: Path, audio: np.ndarray) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.astype(np.int16).tobytes())


def _record(duration: float) -> np.ndarray:
    """Record `duration` seconds from the default mic. Returns int16 array."""
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("sounddevice not installed — run: pip install sounddevice")

    n_samples = int(SAMPLE_RATE * duration)
    audio = sd.rec(n_samples, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return audio.flatten()


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))


def mode_positive(out_dir: Path, n: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("real_*.wav"))
    start_idx = len(existing)

    print("\n=== POSITIVE SAMPLE RECORDING ===")
    print(f"Recording {n} clips of you saying 'hey roamin'.")
    print(f"Output dir : {out_dir}")
    print(f"Already have: {start_idx} real clip(s)")
    print()
    print("Tips:")
    print("  - Speak naturally, at normal conversational volume")
    print("  - Vary your speed and tone slightly between clips")
    print("  - Stay at your normal mic distance")
    print("  - Don't wait for silence — just say it as if waking an assistant")
    print()
    input("Press Enter when ready to start...")

    saved = 0
    i = start_idx

    while saved < n:
        clip_num = saved + 1
        print(f"\n[{clip_num}/{n}]  Get ready...", end="", flush=True)
        time.sleep(0.5)
        for t in [3, 2, 1]:
            print(f" {t}...", end="", flush=True)
            time.sleep(0.8)
        print("  >>> SPEAK NOW <<<", flush=True)

        audio = _record(CLIP_DURATION)
        rms = _rms(audio)

        if rms < 200:
            print(f"  !! Too quiet (RMS={rms:.0f}) — did you speak? Retrying...")
            continue

        fname = out_dir / f"real_{i:04d}.wav"
        _save_wav(fname, audio)
        print(f"  Saved: {fname.name}  (RMS={rms:.0f})")
        i += 1
        saved += 1

    print(f"\nDone — {saved} real positive clips saved to {out_dir}")


def mode_ambient(out_dir: Path, minutes: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("ambient_*.wav"))
    start_idx = len(existing)

    duration = minutes * 60
    n_clips = int(duration / CLIP_DURATION)

    print("\n=== AMBIENT NOISE RECORDING ===")
    print(f"Recording {minutes:.1f} min of your ambient environment.")
    print(f"Output dir : {out_dir}")
    print(f"Will produce ~{n_clips} clips of {CLIP_DURATION:.0f}s each")
    print()
    print("Tips:")
    print("  - Do NOT speak during this recording")
    print("  - Leave fan on, ambient sounds as-is — that's the point")
    print("  - You can walk away; just don't talk")
    print()
    input("Press Enter to start recording ambient noise...")

    print(f"Recording {duration:.0f}s of ambient noise... (do not speak)")
    print("Progress: ", end="", flush=True)

    chunk_size = CLIP_SAMPLES
    all_clips = []
    start = time.time()
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("sounddevice not installed — run: pip install sounddevice")

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        while True:
            elapsed = time.time() - start
            if elapsed >= duration:
                break
            chunk, _ = stream.read(chunk_size)
            all_clips.append(chunk.flatten().copy())
            pct = int((elapsed / duration) * 20)
            print(f"\rProgress: [{'#'*pct}{'.'*(20-pct)}] {elapsed:.0f}s / {duration:.0f}s", end="", flush=True)

    print("\nSaving clips...")
    saved = 0
    for j, clip in enumerate(all_clips):
        # Skip clips where someone accidentally spoke (high energy)
        # Also skip clips that are pure silence (likely gaps)
        rms = _rms(clip)
        if rms < 10:
            continue  # absolute silence — probably a gap, skip
        if rms > 3000:
            print(f"  Skipping clip {j} — RMS {rms:.0f} too loud (possible speech), skipping")
            continue
        fname = out_dir / f"ambient_{start_idx + saved:04d}.wav"
        _save_wav(fname, clip)
        saved += 1

    print(f"\nDone — {saved} ambient clips saved to {out_dir}")
    print("(Skipped clips with RMS < 10 or > 3000)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record real audio samples for wake word training")
    parser.add_argument("--mode", choices=["positive", "ambient"], required=True)
    parser.add_argument("--n", type=int, default=60, help="Number of positive clips (mode=positive)")
    parser.add_argument("--minutes", type=float, default=5.0, help="Minutes of ambient noise (mode=ambient)")
    parser.add_argument("--pos-dir", type=Path, default=DEFAULT_POS_DIR)
    parser.add_argument("--neg-dir", type=Path, default=DEFAULT_NEG_DIR)
    args = parser.parse_args()

    if args.mode == "positive":
        mode_positive(args.pos_dir, args.n)
    else:
        mode_ambient(args.neg_dir, args.minutes)


if __name__ == "__main__":
    main()
