# Local OpenWakeWord Training Pipeline

**Status:** APPROVED — Open questions resolved, ready for implementation
**Date:** 2026-04-17
**Scope:** Add a reproducible, local (WSL2 + CUDA) training pipeline that produces custom ONNX wake word and stop word models for Roamin, eliminating reliance on Google Colab (which has proven unstable due to session disconnects, dependency conflicts, and numpy/pandas version churn).

---

## Why

The current Roamin ambient agent has a fully implemented **wake word runtime** (`agent/core/voice/wake_word.py`) that already knows how to:

- Load a custom `hey_roamin.onnx` from `models/wake_word/`
- Load a custom `stop_roamin.onnx` from the same directory
- Fall back to the built-in `hey_jarvis` model when no custom model is present
- Run wake detection on a daemon thread at 16 kHz / 80 ms frames
- Gate stop-word detections via RMS energy thresholding during TTS playback (`_ENERGY_GATE_RMS = 1500`)
- Expose `start_stop_listening()` / `stop_stop_listening()` hooks for TTS integration

The **only missing piece** for wake-word detection is the ONNX model files themselves. Both `models/wake_word/hey_roamin.onnx` and `models/wake_word/stop_roamin.onnx` do not exist, forcing the runtime to fall back to `hey_jarvis`.

The original plan (documented in `openspec/changes/archive/priority-11-ambient-presence/proposal.md`) called for training via a Google Colab notebook. That path has repeatedly failed:

- Overnight Colab sessions are killed by Windows sleep mode, with no resume capability
- piper-sample-generator does not persist batches to disk — a disconnect loses all progress
- Colab's pinned `google-colab`/`db-dtypes`/`gradio`/`bqplot` packages force `pandas==2.2.2`, which conflicts with `datasets==2.14.6`'s transitive dependencies and produces numpy binary incompatibilities (`ValueError: numpy.dtype size changed`)
- Each fix cascades into new version conflicts (dill → fsspec → huggingface-hub → onnx)

A local WSL2 + CUDA pipeline sidesteps all of these by giving us full control over the Python environment and disk persistence.

Additionally, the original plan trained a **single stop word** (`stop_roamin`). The user now wants a **consolidated stop-words model** covering seven phrases in one ONNX file:

- "stop roamin"
- "roamin stop"
- "shutup"
- "hey shutup"
- "roamin shutup"
- "be quiet"
- "silence"

This is consistent with how commercial wake-word systems (Alexa, Siri) bundle many "stop"/"cancel" utterances into a single classifier — the user's intent is unambiguous ("make it stop"), so there is no need to distinguish *which* stop phrase was used. One model is simpler, faster (~50 ms inference vs. 200 ms across 4 separate models), and reduces training time from ~16 hours to ~8–12 hours.

## What Changes

### New Capability: `wake-word-training`

A fully local, reproducible training pipeline that produces two ONNX files:

1. **`models/wake_word/hey_roamin.onnx`** — custom wake word classifier for "hey roamin"
2. **`models/wake_word/stop_roamin.onnx`** — consolidated stop word classifier trained on all 7 stop phrases (the filename is preserved so no runtime path changes are needed)

The pipeline is driven by:

- A `training/` directory at the project root containing all setup scripts, config files, and sample-generation/training driver scripts
- A YAML config per model (`training/configs/hey_roamin.yaml`, `training/configs/stop_roamin.yaml`) defining phrase list, sample count, augmentation, and hyperparameters
- Setup scripts for WSL2 Ubuntu 22.04 + CUDA 12.4 + PyTorch with GPU, including `.wslconfig` memory allocation
- Per-phase driver scripts (sample generation, model training, model verification) invoked by the user from the WSL shell
- End-to-end documentation at `docs/WAKE_WORD_TRAINING.md` covering prerequisites, setup, execution, and integration

### Modified Capabilities

None. The runtime (`agent/core/voice/wake_word.py`) remains unchanged — it already loads `hey_roamin.onnx` and `stop_roamin.onnx` by path and falls back gracefully when missing. Integration is a pure drop-in: copy the trained `.onnx` files into `models/wake_word/` and restart Roamin.

### Pre-existing Gap: Stop-Word TTS Wiring (Out of Scope)

> **Important:** The `WakeWordListener` class fully implements stop-word detection (`_check_stop_word`, energy gating, `on_stop_detect` callback). However, the TTS pipeline (`agent/core/voice/tts.py`) **does not yet call** `start_stop_listening()` before speech or `stop_stop_listening()` after speech. In `run_wake_listener.py` (line 396) `on_stop_detect` is explicitly set to `None` with the comment "Wired to TTS cancel in 11.2" — this was deferred and never completed.
>
> **Effect:** Training and deploying `stop_roamin.onnx` via this proposal will make the model available to the runtime, but stop-word interruption of TTS will not function until the TTS wiring is implemented in a separate change proposal.
>
> **Scope decision:** Fixing the TTS wiring is intentionally out of scope for this proposal. The training pipeline is independent of the runtime integration. A follow-up `tts-stop-word-wiring` change proposal should cover: calling `wake_word.start_stop_listening()` before `tts.speak()`, calling `wake_word.stop_stop_listening()` after speak completes or is cancelled, and wiring `on_stop_detect` to a TTS cancellation callback in `run_wake_listener.py`.

### What This Proposal Does NOT Do

- Does not change `wake_word.py`, `wake_listener.py`, `tts.py`, or any other runtime Python code
- Does not wire stop-word detection to TTS playback (separate proposal required — see above)
- Does not add new runtime dependencies to `requirements.txt` (training deps live in `training/requirements-training.txt`)
- Does not add a second wake word (user confirmed "hey roamin" is sufficient; adding the bare word "roamin" would cause excessive false positives)
- Does not replace the Google Colab option — the Colab notebook remains valid; this simply adds a local alternative
- Does not attempt to ship or auto-install WSL2/CUDA (those are user-performed one-time setup steps documented in the training guide)
- Does not train via real human voice recordings (synthetic Piper samples + augmentation only — consistent with the archived Priority 11.1 plan)

## Capabilities

### New Capabilities

- `wake-word-training`: A local training pipeline that produces `hey_roamin.onnx` and a consolidated `stop_roamin.onnx` from a documented, reproducible WSL2 + CUDA workflow. Includes setup scripts, YAML configs, sample generation, training, verification, and integration steps.

### Modified Capabilities

None.

## Impact

- **Files created**:
  - `training/` directory (new, not runtime)
  - `training/README.md` — quick-start overview
  - `training/configs/hey_roamin.yaml` — wake word training config
  - `training/configs/stop_roamin.yaml` — consolidated stop word training config (7 phrases)
  - `training/setup/wsl_bootstrap.sh` — installs Python 3.10 venv + PyTorch + OpenWakeWord + piper-sample-generator; verifies GPU with `torch.cuda.is_available()`
  - `training/setup/piper_bootstrap.sh` — downloads Piper voice model, verifies SHA256 checksum, runs sanity WAV test
  - `training/setup/data_bootstrap.sh` — downloads background audio (FMA/AudioSet), RIR files (MIT IR Survey), and false-positive validation data into `training/data/`
  - `training/scripts/generate_samples.py` — resumable clip generator; wraps `python -m openwakeword.train --generate_clips`; loops all phrases for consolidated stop model
  - `training/scripts/augment_samples.py` — augmentation step; wraps `python -m openwakeword.train --augment_clips`; validates background/RIR paths before invocation
  - `training/scripts/train_model.py` — training driver; wraps `python -m openwakeword.train --train_model`; tees output to log; writes `meta.json`
  - `training/scripts/verify_model.py` — sanity-check: tests all 7 stop phrases individually plus silence; actionable failure messages
  - `training/scripts/compare_models.py` — A/B comparison utility: runs verification on two ONNX files side-by-side
  - `training/scripts/clean.sh` — purges generated `training/data/` and `training/out/` to reclaim disk space
  - `training/requirements-training.txt` — training-only Python deps with explicit `numpy<2.0` and `pandas<3.0` version caps
  - `docs/WAKE_WORD_TRAINING.md` — end-to-end user guide (prereqs → WSL2 → CUDA → setup → generate → train → verify → integrate → tune → troubleshoot)
- **Files modified**:
  - `.gitignore` — add `training/data/`, `training/out/`, `training/venv/` (generated artifacts, large)
  - `README.md` — add a short "Custom Wake Word" section with a pointer to `docs/WAKE_WORD_TRAINING.md`
  - `models/wake_word/README.md` — NEW: describes expected filenames, how to produce them, and the TTS-wiring gap
- **Files NOT modified**:
  - `agent/core/voice/wake_word.py` — runtime already handles both files with graceful fallback
  - `agent/core/voice/wake_listener.py` — no changes
  - `agent/core/voice/tts.py` — no changes (TTS wiring is a separate proposal)
  - `run_wake_listener.py` — no changes
  - `requirements.txt` — runtime deps unchanged
- **Dependencies (training-only, isolated in `training/venv/`)**:
  - Python 3.10 (WSL2 Ubuntu 22.04)
  - `torch`, `torchvision`, `torchaudio` (CUDA 12.4 build)
  - `openwakeword>=0.6.0`, `speechbrain>=1.0.0`, `onnx>=1.17.0`, `onnxruntime-gpu>=1.20.0`
  - `audiomentations>=0.39.0`, `pronouncing>=0.2.0`, `deep-phonemizer>=0.0.17`
  - `datasets>=2.20.0` (avoids the pandas/dill cascade from 2.14.6)
  - `piper-tts>=1.2.0` + `en_US-lessac-medium` voice (downloaded by bootstrap, SHA256 verified)
  - `piper-sample-generator` (git clone from `github.com/rhasspy/piper-sample-generator`, pip editable install)
  - `pyyaml>=6.0`, `numpy>=1.26,<2.0`, `pandas>=2.2,<3.0`
- **External training data** (downloaded by `training/setup/data_bootstrap.sh` into gitignored `training/data/`):
  - `validation_set_features.npy` (~2–4 GB): pre-computed OWW validation features from HuggingFace (`davidscripka/openwakeword_features`) — **must be pre-downloaded; NOT auto-generated**
  - Background audio WAVs (~500 MB, 1 hr at 16 kHz): FMA subset or equivalent (source URL confirmed at §0.5)
  - Room Impulse Response WAVs (~500 MB): MIT IR Survey (URL confirmed at §0.6)
  - `en_US-libritts_r-medium.pt` (~300 MB): piper-sample-generator voice model (distinct from piper-tts runtime `.onnx`)
- **Disk requirement: ≥ 40 GB free** on the WSL2 filesystem (was 25 GB — raised to account for all training data downloads + generated features)
- **Breaking changes**: None. Adding the trained ONNX files is a pure drop-in.
- **Reversibility**: Trivially reversible — delete `models/wake_word/*.onnx`, and the runtime falls back to `hey_jarvis`. Delete `training/` directory, and nothing in the runtime is affected.

## Resolved Decisions (formerly Open Questions)

1. **Trained `.onnx` files committed to the repo.** ✅ Both `hey_roamin.onnx` and `stop_roamin.onnx` will be committed to `models/wake_word/` once trained. Consistent with the existing `models/` directory already containing multi-GB model weights.

2. **`training/data/` retained after training.** ✅ The ~5–10 GB of synthetic WAV samples will be kept on disk indefinitely. A `training/scripts/clean.sh` utility will be provided for manual cleanup if the user wants to reclaim disk space later. `.gitignore` excludes `training/data/` so the files are retained locally but never committed.

3. **No CPU-only training path documented.** ✅ The pipeline targets NVIDIA RTX hardware only. CPU-only training (~24–48 hours) is not worth documenting since: (a) the user has a capable GPU, and (b) wake-word model training is a developer/maintainer activity — not something an end user of Roamin would ever do. `WAKE_WORD_TRAINING.md` will not mention CPU-only as an option.

4. **Piper voice hardcoded to `en_US-lessac-medium`.** ✅ The training scripts will hardcode this voice. For clarity: Piper is the text-to-speech engine used to *generate the synthetic training audio* — it speaks "hey roamin" thousands of times to create practice examples for the model. `en_US-lessac-medium` is a high-quality neutral American English voice. `audiomentations` then layers on room reverb, background noise, and speed variation to give the model enough diversity to recognize the wake phrase in real-world conditions. No user configuration needed.

5. **Training hyperparameters locked.** ✅ Both YAML configs will use the confirmed OpenWakeWord field names (validated from `openwakeword/train.py` source):
   - `n_samples: 5000` × `augmentation_rounds: 10` = **50,000 total training examples** (maps to Colab's `number_of_examples`)
   - `steps: 45400` — sequence-1 training steps; 4.5× the OWW default (maps to Colab's `number_of_training_steps`)
   - `max_negative_weight: 300` — linearly ramped peak false-activation penalty (maps to Colab's `false_activation_penalty`)

## Follow-up Proposal Flagged

- **`tts-stop-word-wiring`** (separate change proposal, not part of this scope): Wire `WakeWordListener.start_stop_listening()` / `stop_stop_listening()` into `tts.py` speak methods and connect `on_stop_detect` in `run_wake_listener.py` to a TTS cancellation callback. This is the remaining work from Priority 11.2 and is a prerequisite for stop-word interruption to function at runtime.
