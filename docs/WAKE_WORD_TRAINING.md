# Wake Word Training Guide

This guide covers training custom OpenWakeWord ONNX models for Roamin:
- `hey_roamin.onnx` — wake word (activates the agent)
- `stop_roamin.onnx` — stop word (7 consolidated stop phrases)

---

## Prerequisites

| Requirement | Details |
|---|---|
| OS | Ubuntu 24.04 LTS inside WSL2 on Windows 11 |
| GPU | NVIDIA RTX 3090 (or similar, ≥ 8 GB VRAM) |
| NVIDIA driver | ≥ 550 (Windows-side) |
| CUDA | 13.x (driver passthrough via WSL2) |
| Disk (WSL2) | ≥ 40 GB free |
| Python | 3.12 (pre-installed on Ubuntu 24.04) |

### WSL2 GPU passthrough verification

```bash
nvidia-smi   # should show your GPU and CUDA version
```

If `nvidia-smi` is missing or errors, install the NVIDIA CUDA toolkit for WSL:
```
https://developer.nvidia.com/cuda-downloads (select: Linux → x86_64 → WSL-Ubuntu → 2.0)
```

---

## Step 0 — First-time setup (run once)

All setup scripts are idempotent — safe to re-run.

### §0.1 — Training environment

```bash
# From WSL2, in the project root:
bash training/setup/wsl_bootstrap.sh
```

This installs:
- Python 3.12 virtualenv at `training/venv/`
- PyTorch with CUDA 12.6 (`cu126` index)
- OpenWakeWord, piper-sample-generator, speechbrain, onnxruntime-gpu
- ffmpeg, tmux, libsndfile1

**After running:** record the SHA256 printed for `en_US-libritts_r-medium.pt`
and paste it into `PIPER_PT_SHA256` in `wsl_bootstrap.sh`.

### §0.2 — Piper TTS voice model

```bash
bash training/setup/piper_bootstrap.sh
```

Downloads `en_US-lessac-medium.onnx` to `~/.local/share/piper/models/` and
runs a sanity test ("hey roamin" → WAV ≥ 10 KB).

**After running:** record the printed SHA256 into `EXPECTED_SHA256` in `piper_bootstrap.sh`.

### §0.3 — Training data

```bash
bash training/setup/data_bootstrap.sh
```

Downloads (~10 GB total):
- `validation_set_features.npy` (~2-4 GB, HuggingFace)
- FMA small background audio → converted to 16kHz WAV (~500 files)
- MIT Room Impulse Response Survey (~500 MB, ~270 WAVs)

**After running:** record the SHA256 printed for `validation_set_features.npy`
into `VAL_NPY_SHA256` in `data_bootstrap.sh`.

---

## Step 1 — Generate TTS samples (Stage 1)

```bash
# Start a tmux session so disconnects don't interrupt the run
tmux new -s generate_hey

source training/venv/bin/activate

# Quick smoke test first (verify piper-sample-generator works)
python training/scripts/generate_samples.py \
    --config training/configs/hey_roamin.yaml \
    --preview 10

# Full generation (~5000 WAVs, may take 20-40 min)
python training/scripts/generate_samples.py \
    --config training/configs/hey_roamin.yaml
```

OWW writes WAVs to `training/out/`. The manifest sidecar
(`training/configs/hey_roamin.manifest.json`) tracks completion so re-runs skip
already-generated files.

---

## Step 2 — Augment clips (Stage 2)

```bash
python training/scripts/augment_samples.py \
    --config training/configs/hey_roamin.yaml
```

Mixes positive WAVs with background noise and room impulse responses.
Produces feature NPY files in `training/out/`.

Expected output: `hey_roamin_features_*.npy` (positive + adversarial_negative).

---

## Step 3 — Train model (Stage 3)

> ⚠️ **OWW writes no checkpoints.** If training is interrupted, Stage 3 must
> restart from scratch. Keep your tmux session alive and disable system sleep.

```bash
# Use tmux (or nohup) to guard against disconnects
tmux new -s train_hey   # or attach: tmux attach -t train_hey

python training/scripts/train_model.py \
    --config training/configs/hey_roamin.yaml
```

Training runs two sequences:
- **Sequence 1**: 45,400 steps, `max_negative_weight` ramped linearly 1 → 300
- **Sequence 2**: 4,540 steps at lr/10, weight doubled if FP/hr > 0.2

Estimated time: **2–6 hours** on RTX 3090.

Output: `training/out/hey_roamin.onnx`

---

## Step 4 — Verify

```bash
python training/scripts/verify_model.py \
    --onnx training/out/hey_roamin.onnx
```

Checks:
1. ONNX schema valid
2. File size > 10 KB
3. Runtime inference (zero-vector smoke test)
4. False-positive rate against `validation_set_features.npy` (target ≤ 0.5/hr)

---

## Step 5 — Deploy

```bash
python training/scripts/compare_models.py \
    --new training/out/hey_roamin.onnx \
    --existing models/wake_word/hey_roamin.onnx \
    --auto-deploy
```

`--auto-deploy` replaces the deployed model only if the new one has an equal or
better false-positive rate. Use `--deploy` to force replacement regardless.

---

## Repeat for stop_roamin

Run the same Steps 1–5 using `--config training/configs/stop_roamin.yaml`
and target `models/wake_word/stop_roamin.onnx`.

---

## §0.6 — Alternative RIR sources

If the MIT RIR Survey download fails:
- **OpenRIR**: https://openslr.org/28/
- **ABER impulse responses**: https://www.aber.ac.uk/en/media/departmental/cs/research/impulse-responses.zip

Place WAV files directly in `training/data/rir/`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `nvidia-smi` not found in WSL | GPU passthrough not configured | Install CUDA WSL toolkit |
| `torch.cuda.is_available()` → False | Wrong PyTorch build | Re-run wsl_bootstrap.sh |
| `KeyError: feature_data_files` | Old OWW config missing required field | Ensure `feature_data_files: {}` in YAML |
| WAV files found: 0 | piper-sample-generator not installed | Re-run wsl_bootstrap.sh |
| Training loses progress on disconnect | No tmux/nohup | Use `tmux new -s train` before running |
| FP rate > 0.5/hr | `max_negative_weight` too low | Retrain with higher value (e.g. 350–400) |
| `numpy.dtype size changed` | numpy 2.x binary incompatibility | Ensure `numpy<2.0` in requirements |

---

## Disk space management

```bash
# See what's using space (dry-run, shows sizes):
bash training/scripts/clean.sh

# Delete generated artifacts only (keeps downloaded data):
bash training/scripts/clean.sh --confirm

# Full clean (re-download required):
bash training/scripts/clean.sh --all --confirm
```

Approximate space usage:

| Directory | Size |
|---|---|
| training/venv/ | ~5 GB |
| training/data/piper_models/ | ~300 MB |
| training/data/ (validation + FMA + RIR) | ~10–12 GB |
| training/out/ (WAVs + NPYs + ONNX) | ~5–10 GB |
| **Total** | **~22–28 GB** |
