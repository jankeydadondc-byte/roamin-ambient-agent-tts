"""Diagnostic: run hey_roamin.onnx against silence, noise, and positive samples."""

import glob
import sys
import wave

import numpy as np
import openwakeword

model_path = sys.argv[1] if len(sys.argv) > 1 else "models/wake_word/hey_roamin.onnx"
pos_glob = sys.argv[2] if len(sys.argv) > 2 else "training/out/hey_roamin/positive_test/**/*.wav"

oww = openwakeword.Model(wakeword_models=[model_path], inference_framework="onnx")
chunk_size = 1280


def test(audio, label):
    oww.reset()
    max_s = 0.0
    for i in range(0, len(audio) - chunk_size, chunk_size):
        chunk = audio[i : i + chunk_size].astype(np.int16)
        pred = oww.predict(chunk)
        s = list(pred.values())[0]
        if s > max_s:
            max_s = s
    print(f"  {label:35s} max_score={max_s:.4f}")


print(f"[diagnostics] model={model_path}")

silence = np.zeros(16000 * 5, dtype=np.int16)
test(silence, "5s silence")

np.random.seed(42)
noise_quiet = (np.random.randn(16000 * 5) * 200).astype(np.int16)
test(noise_quiet, "5s quiet white noise")

noise_loud = (np.random.randn(16000 * 5) * 2000).astype(np.int16)
test(noise_loud, "5s louder white noise")

wavs = glob.glob(pos_glob, recursive=True)[:30]
if wavs:
    scores = []
    for w in wavs:
        with wave.open(w, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16)
        oww.reset()
        max_s = 0.0
        for i in range(0, len(audio) - chunk_size, chunk_size):
            chunk = audio[i : i + chunk_size].astype(np.int16)
            pred = oww.predict(chunk)
            s = list(pred.values())[0]
            if s > max_s:
                max_s = s
        scores.append(max_s)
    scores = np.array(scores)
    label = f"{len(scores)} positive samples"
    print(f"  {label:35s} mean={scores.mean():.4f} median={np.median(scores):.4f} >0.5={(scores > 0.5).mean():.0%}")
else:
    print(f"  No positive samples found at {pos_glob}")
