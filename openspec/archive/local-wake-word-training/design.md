# Design — Local OpenWakeWord Training Pipeline

## Context

Roamin already ships a complete wake-word runtime in `agent/core/voice/wake_word.py`. The `WakeWordListener` class loads `models/wake_word/hey_roamin.onnx` at startup; if absent, it falls back to OpenWakeWord's built-in `hey_jarvis` model. A second model at `models/wake_word/stop_roamin.onnx` is loaded on demand to detect stop phrases during TTS playback, with a per-frame RMS energy gate (`_ENERGY_GATE_RMS = 1500`) to suppress self-triggers from speaker echo.

The listener thread reads mic audio at 16 kHz in 80 ms frames (1,280 samples) via `sounddevice`, and feeds frames directly to `openwakeword.Model.predict()`. Both models honor a configurable detection threshold (`ROAMIN_WAKE_THRESHOLD`, default 0.5) and a 2-second detection cooldown. Pause/resume hooks exist for STT coexistence.

**Pre-existing gap:** `WakeWordListener` exposes `start_stop_listening()` and `stop_stop_listening()` hooks (lines 153, 168 of `wake_word.py`). However, `tts.py` never calls these hooks, and `run_wake_listener.py` passes `on_stop_detect=None` with the comment "Wired to TTS cancel in 11.2" — this stub was deferred and never completed. The TTS wiring is intentionally out of scope for this proposal and flagged as a follow-up (`tts-stop-word-wiring`).

The only gap **within this proposal's scope** is the model files themselves. The original plan (see archived `priority-11-ambient-presence/proposal.md`) specified training via a one-time Google Colab notebook. In practice, Colab has proven unsuitable:

- **Session instability**: Windows sleep mode kills long-running Colab sessions, and Colab provides no resume capability for interrupted cells.
- **Disk persistence**: piper-sample-generator writes batches to in-memory state by default — a disconnect loses everything.
- **Dependency conflicts**: Colab's pinned baseline (`google-colab 1.0.0`, `db-dtypes 1.5.1`, `gradio 5.50.0`, `bqplot 0.12.45`) requires `pandas==2.2.2`, but `datasets==2.14.6` pulls transitive dependencies that force `pandas 3.x` — and the resulting mixed-version environment triggers `ValueError: numpy.dtype size changed, may indicate binary incompatibility`.
- **Cascade failures**: Each fix (force-reinstall `pandas`, downgrade `datasets`, pin `dill`) breaks a different downstream package (`onnx2tf`, `onnxruntime`, `transformers`, `huggingface-hub`).

A local pipeline inside WSL2 Ubuntu 24.04 sidesteps all of these. The user has an RTX-class GPU already serving Roamin's runtime inference; there is no additional hardware needed.

## Goals / Non-Goals

**Goals:**

- Produce two ONNX files — `hey_roamin.onnx` and a **consolidated** `stop_roamin.onnx` covering 7 stop phrases — on the user's local machine, reproducibly, within 8–12 hours on an RTX 3060 or 2–4 hours on an RTX 4090.
- Make the pipeline resumable: an interrupted sample-generation or training run can be restarted without losing prior work (explicit response to the Colab sleep-mode problem).
- Keep training isolated from the runtime: training deps live in a separate `training/venv/`, and a separate `training/requirements-training.txt` never touches the runtime `requirements.txt`.
- Require zero changes to runtime code — the trained models drop into an existing directory the runtime already watches.
- Provide a single, linear, step-by-step user-facing doc (`docs/WAKE_WORD_TRAINING.md`) so the user can execute the full pipeline in one session without cross-referencing.
- Apply defensive security practices throughout: safe YAML loading, path sanitization, downloaded model checksum verification, and `subprocess` invocations without shell=True.

**Non-Goals:**

- Automating Windows/WSL2/CUDA installation. Those are one-time user-performed steps; the doc walks the user through them but the scripts only run *after* WSL2 is up.
- Replacing or deprecating the Colab notebook. Colab remains an option; this proposal adds a local path beside it.
- Multi-voice or accent-diverse sample generation. v1 uses `en_US-lessac-medium` Piper voice + audiomentations for variation.
- Training from real recorded human voice data. v1 is fully synthetic, matching the archived Priority 11.1 plan and OpenWakeWord's documented best practice for new custom phrases.
- Supporting training on non-NVIDIA hardware as a first-class path. CPU-only training is possible but not documented (estimated 24–48 hours; not needed given user's RTX GPU).
- Adding a second wake word (e.g., bare "roamin"). User confirmed this is not wanted due to false-positive risk.
- Wiring stop-word detection to TTS playback. That is a pre-existing incomplete stub tracked in a separate follow-up proposal (`tts-stop-word-wiring`).

## Decisions

### D1: Consolidated stop-words model (one `.onnx`, seven phrases)

**Decision:** Train a single `stop_roamin.onnx` whose positive training set contains all 7 stop phrases (`stop roamin`, `roamin stop`, `shutup`, `hey shutup`, `roamin shutup`, `be quiet`, `silence`). The file is still named `stop_roamin.onnx` so the runtime needs no path change.

**Rationale:** The runtime only cares *whether* a stop was issued, not which phrase was used. A single model runs in ~50 ms per frame vs. ~200 ms if we shipped 4 separate models, and total training time is ~4–6 hours instead of ~16. This matches how commercial voice assistants bundle many stop/cancel utterances into one classifier.

**Alternative considered:** Four separate models (`stop_roamin`, `shutup`, `be_quiet`, `silence`) for per-phrase logging. Rejected — the user doesn't need to know *which* stop phrase was uttered, and the runtime overhead and training time are materially worse.

**Risk:** A single classifier trained on 7 phonetically diverse phrases may generalize worse than 7 dedicated classifiers. Mitigation: training config sets `n_samples: 5000` distributed across phrases (~700 per phrase), which is within OpenWakeWord's documented healthy range for single-phrase models. The verification script tests each of the 7 phrases individually to catch weak phrases before deployment. If recall on rarer phrases (e.g., "silence") proves poor in verification, the fallback is to either (a) raise `n_samples` to 10,000 or (b) split into two models.

### D2: Isolated training venv — zero impact on runtime Python env

**Decision:** All training work happens inside `training/venv/` (created by `training/setup/wsl_bootstrap.sh`). Training dependencies are listed in `training/requirements-training.txt`, which is never imported from or referenced by the runtime `requirements.txt`.

**Rationale:** The runtime environment must remain stable. Training pulls in `speechbrain`, `audiomentations`, `piper-tts`, `datasets`, `deep-phonemizer`, and several heavyweight transitive deps. Mixing these into the runtime env risks the exact kind of cascade conflicts that broke the Colab run. By isolating, we also make the training pipeline trivially removable (`rm -rf training/venv/`).

### D3: Explicit version caps on `numpy<2.0` and `pandas<3.0`

**Decision:** Pin `numpy>=1.26,<2.0` and `pandas>=2.2,<3.0` in `training/requirements-training.txt`.

**Rationale:** The Colab failures trace back to numpy 2.x binary incompatibility with older compiled extensions, and pandas 3.x being incompatible with the dependency tree. Even in a clean training venv, these ceilings prevent future `pip install` runs from silently pulling in incompatible majors. They can be relaxed in a follow-up change once the ecosystem confirms compatibility.

### D4: `datasets>=2.20.0` instead of Colab's `datasets==2.14.6`

**Decision:** Use `datasets>=2.20.0`, which does not pull the old `dill<0.3.8` / `fsspec` / `huggingface-hub` transitive chain that caused the Colab cascade.

**Rationale:** The Colab notebook pinned `datasets==2.14.6` incidentally, not because OpenWakeWord's training code requires it. Dropping the pin eliminates the entire cascade. If a subtle API regression surfaces, fallback is `datasets==2.18.0` (last known-good before pre-3.0 API shifts).

### D5: Resumable sample generation via on-disk manifest + integrity verification

**Decision:** `training/scripts/generate_samples.py` writes every generated WAV immediately to disk and maintains a JSON manifest. On startup, if the manifest exists with N entries, the script skips to entry N+1. On resume, the script verifies each manifest-listed file has size > 0 bytes; corrupted or zero-byte entries are removed from the manifest and regenerated.

**Rationale:** Direct response to the Colab problem where a sleep-mode disconnect at batch 960/1000 lost all 960 batches. Disk-backed manifest + integrity check ensures only the in-flight batch is at risk, and even a corrupt WAV doesn't silently poison the dataset.

**Disk-full handling:** The script checks available disk space every 50 batches (via `shutil.disk_usage()`). If free space drops below 2 GB, generation pauses and prints an actionable warning with current disk usage and a pointer to `clean.sh`. It does not crash — the manifest is flushed first, allowing the user to free space and resume.

**SIGINT handling:** `atexit` and `signal.signal(signal.SIGINT, ...)` handlers flush the manifest and close any open Piper subprocess before exiting. The exit is clean within 5 seconds.

### D6: Training has no resume capability — mitigate via prerequisites

**Decision:** OpenWakeWord's training script (`openwakeword/train.py`) writes **zero checkpoint files** during training. `auto_train()` stores best models in memory only and exports a single ONNX at completion. There is no `--resume` flag and no `.pt` checkpoint is ever written. If training is interrupted, it must restart from scratch.

**Mitigation strategy (layered):**
1. **Sleep mode disabled** — §1.5 requires the user to disable Windows sleep before starting; eliminates the primary failure cause from the Colab experience
2. **WSL2 memory tuned** — D13 `.wslconfig` prevents silent OOM kills during the training run
3. **LM Studio closed** — §1.7 prevents VRAM contention that could cause CUDA OOM mid-run
4. **Training is the shortest stage** — on RTX 3090, training takes ~3–4 hours. Sample generation (~2–3 hours) IS resumable via manifest (D5). If training is killed, only the training time is lost, not the generated samples.
5. **`nohup` wrapper** — `WAKE_WORD_TRAINING.md` will recommend running training inside `nohup python train_model.py ... &` or a `tmux` session to survive terminal disconnects

**Risk accepted:** If training is killed mid-run, the user re-runs `train_model.py`. No data is lost; only training time. Given the RTX 3090's ~3–4 hour window and the mitigations above, mid-run kills should be rare.

### D7: Three-stage pipeline, each stage invoked manually via wrapper scripts

**Decision:** The pipeline is driven by OpenWakeWord's own training CLI (`python -m openwakeword.train --training_config <yaml> <flag>`) across three discrete stages, each wrapped by a thin custom script that adds resumability, disk-space checking, and progress reporting:

| Stage | OWW CLI flag | Wrapper script | What it does |
|---|---|---|---|
| 1. Generate clips | `--generate_clips` | `generate_samples.py` | Calls piper-sample-generator to synthesize positive WAVs |
| 2. Augment clips | `--augment_clips` | `augment_samples.py` | Mixes positives with background audio + RIR impulse responses |
| 3. Train model | `--train_model` | `train_model.py` | Calls `openwakeword.Model.auto_train()` on pre-computed features |

No single `run_everything.sh` driver. The user invokes each stage manually and sees its output before proceeding.

**Rationale:** Training is long-running and resource-intensive; the user must see what stage is running and be able to intervene. Each stage has distinct failure modes (Piper not found, disk full, CUDA OOM) that are best surfaced as clean per-stage errors. The user runs this a small number of times; orchestration overhead is net-negative. Using the OWW CLI as the engine avoids re-implementing data loading, augmentation, and feature extraction logic that OWW already provides.

### D8: No runtime code changes

**Decision:** This proposal introduces zero modifications to any file under `agent/`, `run_wake_listener.py`, or `requirements.txt`. The only "runtime" touch is dropping ONNX files into `models/wake_word/`.

**Rationale:** `agent/core/voice/wake_word.py` is already correctly structured: it loads `hey_roamin.onnx` by exact path, loads `stop_roamin.onnx` by exact path, and falls back gracefully when either is missing. The fallback-to-`hey_jarvis` behavior is valuable to preserve. Note: this means stop-word *model loading* requires no code changes, but stop-word *interruption of TTS* does require a separate code change (the `tts-stop-word-wiring` proposal).

### D9: Synthetic-only training data

**Decision:** v1 uses 100% synthetic Piper-generated samples + augmentations. No real human voice recordings.

**Rationale:** Matches the archived Priority 11.1 Colab plan. OpenWakeWord's own training guide recommends synthetic-first. Piper's `en_US-lessac-medium` + `audiomentations` (room reverb, background noise, speed variation, gain variation) produces sufficient diversity for the accuracy targets in the config. Collecting real recordings would require hundreds of user voice samples per phrase.

**Accuracy expectation:** Synthetic-only models typically achieve 90–95% True Positive Rate (TPR) on real human speech from users with similar accents to the training voice. If real-world recall is poor, the follow-up path is: (a) lower the threshold via `ROAMIN_WAKE_THRESHOLD`, or (b) a v2 fine-tune stage on a small set of user-recorded WAVs.

**Upgrade path:** A v2 change proposal can add a "real-voice fine-tune" stage that starts from the synthetic-trained ONNX and continues training on user-recorded WAVs.

### D10: Security — safe YAML loading, path sanitization, checksum verification

**Decision:** All scripts in the training pipeline apply these security practices:

1. **YAML loading**: All configs loaded with `yaml.safe_load()` only. `yaml.load()` and `yaml.unsafe_load()` are explicitly forbidden. No YAML deserialization of arbitrary Python objects.

2. **Path sanitization**: `model_name` from any config is validated against `^[a-zA-Z0-9_-]+$` before use in any filesystem path. Any value containing `..`, `/`, or `\` is rejected with a clear error. All output paths are resolved via `pathlib.Path` and verified to lie within `training/data/` or `training/out/` before any file write.

3. **Piper model checksum**: `piper_bootstrap.sh` verifies the SHA256 checksum of the downloaded `en_US-lessac-medium.onnx` against a hardcoded expected value before using it. Checksum mismatch aborts with a clear error.

4. **subprocess without `shell=True`**: All subprocess invocations (Piper CLI calls, pip installs, etc.) use `subprocess.run(cmd_list, shell=False)`. No user-controlled strings are ever interpolated into shell commands.

5. **No `shell=True` in bootstrap scripts**: Bootstrap shell scripts use `apt install` with specific package names only (no variable interpolation into apt commands). Package versions are specified as `python3.10` (not from a variable) so there is no injection surface.

**Rationale:** Training scripts run with elevated local privileges (WSL2 with GPU access). A path traversal or command injection vulnerability in training code could write arbitrary files or execute arbitrary commands. Defense-in-depth at the boundary of user-supplied YAML configs is necessary.

### D11: OpenWakeWord training API — confirmed from source

**Decision:** The training entry point is confirmed (validated from `openwakeword/train.py` source). The pipeline is:

1. **CLI driver:** `python -m openwakeword.train --training_config <yaml> <stage_flag>`
2. **Python class:** `openwakeword.Model` (instantiated by the CLI internally)
3. **Training method:** `Model.auto_train(X_train, X_val, false_positive_val_data, steps, max_negative_weight, target_false_positives_per_hour)`

`auto_train()` runs **two training sequences** automatically:
- Sequence 1: `steps` iterations with `max_negative_weight` ramping linearly from 1 → `max_negative_weight`
- Sequence 2: `steps/10` iterations at `lr/10`, with optional weight doubling if `false_positives_per_hour > target_false_positives_per_hour`

**Key confirmed parameters:**
- `steps=45400` — total steps for sequence 1 (our locked `number_of_training_steps`)
- `max_negative_weight=300` — peak negative example weight (our locked `false_activation_penalty`)
- `target_false_positives_per_hour=0.2` — default; governs whether sequence 2 doubles the weight

**Important caveat:** OpenWakeWord's own training script loads YAML with `yaml.load(open(...), yaml.Loader)` (unsafe). This is internal to OWW's code — not our code. Our wrapper scripts load our own auxiliary config (if any) with `yaml.safe_load()`. The OWW training YAML is passed directly to the OWW CLI without re-parsing.

**§0 validation still required** for: confirming exact YAML field names accepted by the installed version, piper-sample-generator source URL, and SHA256 of Piper model file.

### D14: Required background audio and RIR data — downloaded before training

**Decision:** OpenWakeWord's `--augment_clips` stage requires two external data sources that our scripts must download and organise before training begins. These are listed as required prerequisites in `docs/WAKE_WORD_TRAINING.md` and handled by a new `data_bootstrap.sh` script:

1. **Background audio** (`background_paths` YAML key) — directories of WAV files used as negative/ambient noise during augmentation. Recommended sources:
   - AudioSet balanced training set subset (≥ 1 hour; downloadable from HuggingFace or `yt-dlp` pipeline)
   - Free Music Archive (FMA) small subset (freely licensed audio)
   - Together placed in `training/data/background/` (gitignored)

2. **Room Impulse Response (RIR) files** (`rir_paths` YAML key) — WAV files used to simulate room acoustics during augmentation. Source: MIT IR Survey (permissive licence; `wget` downloadable). Placed in `training/data/rir/` (gitignored).

3. **False-positive validation data** (`false_positive_validation_data_path` YAML key) — a pre-computed `.npy` feature array (~11 hours of mixed audio), provided by OpenWakeWord's releases or generated from the background audio by the OWW augmentation step. Confirmed source URL is a §0 validation task.

**Disk estimate (full breakdown):**

| Item | Size |
|---|---|
| `validation_set_features.npy` | ~2–4 GB |
| `en_US-libritts_r-medium.pt` | ~300 MB |
| Background audio (1 hr, 16kHz WAV) | ~500 MB |
| MIT RIR Survey | ~500 MB |
| Generated positive WAVs (both models) | ~5–10 GB |
| Augmented feature arrays | ~3–6 GB |
| Training venv + packages | ~5 GB |
| Safety buffer | ~5 GB |
| **Total required free** | **≥ 40 GB** |

Prerequisite updated from 25 GB → **40 GB free** on the WSL2 drive.

**Rationale:** Without these files, `--augment_clips` and `--train_model` will fail with missing path errors. They must be present before any augmentation step. These are the only external data dependencies outside the Piper voice model.

### D15: Consolidated stop-word model: multi-phrase via native list support

**Decision:** OpenWakeWord's `target_phrase` config field is a **list** (confirmed from source: `for target_phrase in config["target_phrase"]:`). All 7 stop phrases are placed directly in the list in `stop_roamin.yaml`:

```yaml
target_phrase:
  - "stop roamin"
  - "roamin stop"
  - "shutup"
  - "hey shutup"
  - "roamin shutup"
  - "be quiet"
  - "silence"
```

A single `--generate_clips` invocation handles all 7 phrases. The D15 "loop once per phrase" strategy from the previous draft is replaced by native list support. `n_samples: 5000` is distributed across all phrases by the OWW generator (approximately 715 WAVs per phrase).

**§0.1 validation required:** Confirm that piper-sample-generator distributes samples evenly across a multi-item `target_phrase` list, and that `n_samples` refers to total positives not per-phrase count.

**Rationale:** Simpler than a wrapper loop, uses OWW's built-in multi-phrase support, and is consistent with how the `generate_adversarial_texts()` function already iterates over the list for negative sample generation.

### D12: piper-sample-generator — confirmed installation and model

**Decision:** `piper-sample-generator` IS pip-installable (`pip install piper-sample-generator`). This is the primary installation method per the official README. The `wsl_bootstrap.sh` script installs it via pip and downloads its required `.pt` generator model separately:

```bash
pip install piper-sample-generator
pip install piper-phonemize    # required dep (not bundled in pip package)
pip install webrtcvad           # required dep (not bundled in pip package)

# Download the LibriTTS-R generator model (confirmed URL from v2.0.0 release)
wget https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt \
     -O training/data/piper_models/en_US-libritts_r-medium.pt
```

**Two distinct Piper model files — do not confuse:**

| File | Format | Purpose | Downloaded by |
|---|---|---|---|
| `en_US-lessac-medium.onnx` | ONNX | Roamin's runtime TTS voice | `piper_bootstrap.sh` |
| `en_US-libritts_r-medium.pt` | PyTorch | Sample generation for training | `wsl_bootstrap.sh` |

The `.pt` file is a specialized neural vocoder ("generator model") with speaker embedding mixing. It is incompatible with piper-tts and only used by piper-sample-generator during training data synthesis.

**SHA256 checksum** for `en_US-libritts_r-medium.pt` must be recorded at §0.2 after download and hardcoded in `wsl_bootstrap.sh` for integrity verification.

**Alternative considered:** Directly calling the Piper TTS CLI (`piper --model en_US-lessac-medium.onnx --output_file <wav>`) without piper-sample-generator. Valid fallback — but loses speaker-diversity mixing from the LibriTTS-R generator, reducing training set variety.

### D13: `.wslconfig` memory allocation — required for training success

**Decision:** `docs/WAKE_WORD_TRAINING.md` will include explicit `.wslconfig` setup as a required prerequisite step, not an optional tuning step. Without adequate memory allocated to WSL2, the training run may experience silent OOM kills mid-epoch, leaving corrupt checkpoints.

**Recommended `.wslconfig` (written to `C:\Users\<username>\.wslconfig`):**
```ini
[wsl2]
memory=16GB
processors=8
swap=4GB
```

**Rationale:** WSL2's default memory allocation is half of total system RAM, which may be insufficient if other processes (LM Studio, browsers, games) are competing. The GPU training job + dataset loading can spike to 12+ GB RAM. Explicit allocation prevents silent OOM. The doc will also warn: "Close LM Studio and other GPU-intensive apps during training to avoid VRAM contention."

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|---|---|---|
| OpenWakeWord training API is different from assumed | Implementation blocked | D11: validate API before coding; implementer inspects package source first |
| piper-sample-generator is not pip-installable | Sample generation fails | D12: bootstrap script clones from repo; fallback is direct Piper CLI calls |
| WSL2 + CUDA 12.4 install fails | Pipeline cannot start | `wsl_bootstrap.sh` verifies `nvidia-smi` + `torch.cuda.is_available()` upfront; aborts with actionable message |
| OOM kill or interrupt during training | Full training restart required (no OWW checkpoint support) | D13: `.wslconfig` memory allocation; sleep mode disabled; `nohup`/`tmux` wrapper; RTX 3090 ~3–4 h window is manageable |
| Disk fills during sample generation | Pipeline blocks | D5: check every 50 batches; pause with actionable message pointing to `clean.sh` |
| Consolidated stop model generalizes poorly to "silence" | Stop word misses on real speech | Verification script tests each of the 7 phrases individually; clear threshold for retrain |
| Synthetic-only training produces poor real-voice recall | Wake word rarely triggers | Runtime threshold tunable via `ROAMIN_WAKE_THRESHOLD`; v2 fine-tune path documented |
| Path traversal via `model_name` config key | Arbitrary file write | D10: regex validation + pathlib boundary enforcement |
| Piper model download tampered or corrupt | Poisoned training data | D10: SHA256 checksum verification before use |
| TTS stop-word wiring missing | Trained `stop_roamin.onnx` doesn't interrupt TTS | Explicitly called out as pre-existing gap; separate `tts-stop-word-wiring` proposal |
| user commits `training/data/` (5–10 GB) | Repo bloats | `.gitignore` excludes `training/data/`, `training/out/`, `training/venv/` |

## Migration Plan

Additive change — no migration needed. To adopt:

1. Pull the updated repo
2. Follow `docs/WAKE_WORD_TRAINING.md` end-to-end (~8–12 hours mostly unattended on RTX 3060)
3. Copy `training/out/hey_roamin.onnx` and `training/out/stop_roamin.onnx` to `models/wake_word/`
4. Restart Roamin — models are picked up automatically

Rollback: delete both `.onnx` files, restart. Runtime reverts to `hey_jarvis`.

## Observability

Every stage writes structured artifacts:

- `training/data/<model_name>/manifest.json` — all samples with per-file metadata (path, phrase, duration, augmentations applied, file size bytes)
- `training/out/<model_name>.log` — complete training stdout per epoch
- `training/out/<model_name>.ckpt` — latest epoch checkpoint (PyTorch `.pt`)
- `training/out/<model_name>.ckpt.prev` — previous epoch checkpoint (corruption fallback)
- `training/out/<model_name>.meta.json` — full diagnostics package:
  ```json
  {
    "model_name": "hey_roamin",
    "model_input_shape": [1280],
    "sample_rate": 16000,
    "accuracy": 0.98,
    "true_positive_rate": 0.97,
    "false_positive_rate": 0.01,
    "false_reject_rate": 0.05,
    "training_duration_seconds": 14400,
    "epochs": 10,
    "final_loss": 0.025,
    "epoch_losses": [0.50, 0.30, 0.18, 0.12, 0.08, 0.05, 0.03, 0.027, 0.026, 0.025],
    "config_hash": "abc123...",
    "git_commit": "def456...",
    "hardware": "NVIDIA RTX 3060 12GB",
    "openwakeword_version": "0.6.0",
    "torch_version": "2.4.0+cu126",
    "piper_voice": "en_US-lessac-medium",
    "n_positive_samples": 5000,
    "n_negative_samples": 5000,
    "target_phrases": ["hey roamin", "hey roaming", "hey rome in"],
    "augmentations": ["background_noise", "room_reverb", "speed_variation", "gain_variation"]
  }
  ```

Users reporting issues ("hey roamin doesn't trigger reliably") can share `meta.json` for fast first-pass diagnosis without leaking any audio content.

## Training Configuration

Both models use the OpenWakeWord YAML config schema (field names confirmed from `openwakeword/train.py` source). The Colab notebook's slider labels map to real API parameters as follows:

| Colab UI label | Real YAML key / API param | Locked value |
|---|---|---|
| `number_of_examples` | `n_samples` × `augmentation_rounds` | 5000 × 10 = 50,000 total |
| `number_of_training_steps` | `steps` | 45400 |
| `false_activation_penalty` | `max_negative_weight` | 300 |

```yaml
# training/configs/hey_roamin.yaml
# Passed directly to: python -m openwakeword.train --training_config hey_roamin.yaml
# Field names confirmed from openwakeword/train.py source (2026-04-17)

model_name: hey_roamin
output_dir: "training/out/"          # ONNX saved as output_dir/model_name.onnx

# Stage 1: --generate_clips (piper-sample-generator)
target_phrase:                       # LIST required — string causes character-iteration bug
  - "hey roamin"
  - "hey roaming"                    # common mishearing
  - "hey rome in"                    # phonetic variation
n_samples: 5000                      # total positive WAVs across all phrases
n_samples_val: 500                   # held-out validation positives
tts_batch_size: 100                  # piper-sample-generator batch size

# Stage 2: --augment_clips
augmentation_batch_size: 100
augmentation_rounds: 10              # n_samples × rounds = 50,000 total training examples
background_paths:
  - "training/data/background/"      # downloaded by data_bootstrap.sh (§3.3)
background_paths_duplication_rate:
  - 1
rir_paths:
  - "training/data/rir/"            # MIT IR Survey, downloaded by data_bootstrap.sh

# Model architecture
model_type: "dnn"
layer_size: 128
batch_n_per_class: 500

# Validation — pre-downloaded by data_bootstrap.sh (§3.3)
# Source: https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy
false_positive_validation_data_path: "training/data/validation_set_features.npy"

# Feature file paths — required field; script auto-populates keys during augment/train stages
feature_data_files: {}               # empty dict; script adds 'positive' and 'adversarial_negative'

# Stage 3: --train_model — locked hyperparameters
steps: 45400                         # sequence-1 steps (Colab: number_of_training_steps)
max_negative_weight: 300             # peak penalty  (Colab: false_activation_penalty)
target_false_positives_per_hour: 0.2 # sequence-2 trigger (OWW default)
```

```yaml
# training/configs/stop_roamin.yaml
# 7-phrase consolidated stop model — all phrases in one target_phrase list
# OWW natively handles list; single --generate_clips pass covers all 7

model_name: stop_roamin
output_dir: "training/out/"

target_phrase:                       # all 7 phrases — OWW iterates this list natively
  - "stop roamin"
  - "roamin stop"
  - "shutup"
  - "hey shutup"
  - "roamin shutup"
  - "be quiet"
  - "silence"
n_samples: 5000                      # ~715 WAVs per phrase distributed across all 7
n_samples_val: 500
tts_batch_size: 100

augmentation_batch_size: 100
augmentation_rounds: 10
background_paths:
  - "training/data/background/"
background_paths_duplication_rate:
  - 1
rir_paths:
  - "training/data/rir/"

model_type: "dnn"
layer_size: 128
batch_n_per_class: 500

false_positive_validation_data_path: "training/data/validation_set_features.npy"

feature_data_files: {}               # required — script auto-populates positive/adversarial_negative keys

steps: 45400
max_negative_weight: 300
target_false_positives_per_hour: 0.2
```

> **§0.1 validation confirmed:** `n_samples` is the **total** count across all phrases in the list (script divides by `len(target_phrase)` internally for adversarial generation). So `n_samples: 5000` with 7 stop phrases = ~715 WAVs per phrase. No change to config values needed., and that piper-sample-generator distributes samples approximately evenly across phrases.

**Hyperparameter rationale:**

- **`n_samples: 5000` × `augmentation_rounds: 10` = 50,000 total examples** — at the high end of OpenWakeWord's recommended range; sufficient for good generalization on synthetic data.
- **`steps: 45400`** — maps to `max_steps` in `auto_train()` sequence 1; 4.5× OWW's default (10,000), ensures good convergence without excessive runtime.
- **`max_negative_weight: 300`** — linearly ramped from 1 → 300 over training; balanced for home-noise robustness without over-suppressing true positives. Tunable post-deployment via `ROAMIN_WAKE_THRESHOLD`.

## Hardware Reference Table

| GPU | VRAM | Sample Generation | Training (per model) | Total (2 models) |
|---|---|---|---|---|
| RTX 3060 | 12 GB | 2–3 hours | 4–6 hours | 10–16 hours |
| RTX 3090 | 24 GB | 1.5–3 hours | 3–4 hours | **7.5–11 hours** |
| RTX 4080 | 16 GB | 1.5–2 hours | 2–3 hours | 6–10 hours |
| RTX 4090 | 24 GB | 1–1.5 hours | 1–2 hours | 4–6 hours |

*Sample generation time is Piper CPU-bound, not GPU-bound. GPU only accelerates the training phase.*

*User's hardware (RTX 3090 24GB) will complete both models in **~7.5–11 hours** based on the above table.*

Minimum VRAM: 6 GB (RTX 2060) — `batch_size` may need reduction to 16 to avoid OOM.
Recommended VRAM: 12 GB or more.
