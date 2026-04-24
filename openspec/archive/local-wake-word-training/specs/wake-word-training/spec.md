# Spec — `wake-word-training` capability

> **Scope note:** This spec covers producing and deploying the trained ONNX model files. It does NOT cover wiring stop-word detection to TTS playback — that is a pre-existing incomplete stub (`run_wake_listener.py:396` sets `on_stop_detect=None`) tracked in the separate `tts-stop-word-wiring` proposal.

---

## ADDED Requirements

### Requirement: Pre-implementation API validation

Before any training scripts are coded, the implementer SHALL validate the exact OpenWakeWord training API by inspecting the installed package source (`python -c "import openwakeword; help(openwakeword)"`) and document the actual function name, signature, return value, and exceptions. Training scripts MUST call the real API — not a guessed or assumed interface.

#### Scenario: Training API validated before coding

- **GIVEN** `openwakeword` is installed in the training venv
- **WHEN** the implementer runs the validation command in §0.1 of tasks.md
- **THEN** the exact entry point (module path, function or class name, full signature) is recorded in a comment at the top of `training/scripts/train_model.py` before any implementation begins

---

### Requirement: Local WSL2 + CUDA training environment

The repository SHALL provide idempotent shell scripts that establish a reproducible Python 3.10 + PyTorch (CUDA 12.4) + OpenWakeWord training environment inside WSL2 Ubuntu 22.04, isolated from the runtime Python environment.

#### Scenario: Fresh WSL2 bootstrap succeeds

- **GIVEN** a fresh WSL2 Ubuntu 22.04 install with NVIDIA drivers ≥ 550 on the Windows host
- **WHEN** the user runs `bash training/setup/wsl_bootstrap.sh`
- **THEN** the script installs Python 3.10, creates `training/venv/`, installs PyTorch CUDA 12.4 and all packages from `training/requirements-training.txt`, prints `torch.cuda.is_available() == True`, and exits 0

#### Scenario: Bootstrap aborts cleanly on missing GPU

- **GIVEN** WSL2 without NVIDIA GPU passthrough (`nvidia-smi` returns an error)
- **WHEN** the user runs `bash training/setup/wsl_bootstrap.sh`
- **THEN** the script exits non-zero with a message pointing to the Prerequisites section of `docs/WAKE_WORD_TRAINING.md`, and no partial installation remains

#### Scenario: Dry-run shows planned steps without executing

- **WHEN** the user runs `bash training/setup/wsl_bootstrap.sh --dry-run`
- **THEN** the script prints each planned action without executing any of them, and exits 0

#### Scenario: Training venv does not contaminate runtime

- **WHEN** `wsl_bootstrap.sh` completes successfully
- **THEN** the root `requirements.txt` is unchanged AND no packages are installed outside `training/venv/`

---

### Requirement: WSL2 memory configuration documented and required

`docs/WAKE_WORD_TRAINING.md` SHALL include creation of `C:\Users\<username>\.wslconfig` with explicit memory and processor allocation as a **required** step, not an optional one.

#### Scenario: .wslconfig present before training

- **WHEN** the user follows `WAKE_WORD_TRAINING.md` top-to-bottom
- **THEN** they create `.wslconfig` (with `memory=16GB`, `processors=8`, `swap=4GB`) and run `wsl --shutdown` before proceeding to any training step

#### Scenario: Insufficient memory causes clear failure, not silent OOM

- **GIVEN** WSL2 is allocated insufficient memory and the training job triggers an OOM condition
- **THEN** the training script exits with a non-zero code and a message referencing the `.wslconfig` section of `WAKE_WORD_TRAINING.md`, rather than silently crashing or leaving a corrupt checkpoint

---

### Requirement: Piper TTS voice provisioning with integrity verification

The repository SHALL provide a setup script that downloads the `en_US-lessac-medium` Piper voice, verifies its SHA256 checksum, and verifies it produces a non-empty WAV file on a canary input.

#### Scenario: Piper voice download, checksum pass, and sanity test

- **GIVEN** a successful `wsl_bootstrap.sh` completion
- **WHEN** the user runs `bash training/setup/piper_bootstrap.sh`
- **THEN** `en_US-lessac-medium.onnx` and its `.onnx.json` exist in `~/.local/share/piper/models/`, the SHA256 checksum of the `.onnx` file matches the hardcoded expected value, a sanity WAV ≥ 10 KB is produced, and the script exits 0

#### Scenario: Checksum mismatch aborts immediately

- **GIVEN** the downloaded Piper model file has been tampered with or is corrupt
- **WHEN** `piper_bootstrap.sh` runs the checksum verification
- **THEN** the script exits non-zero with "SHA256 mismatch — downloaded file may be corrupt or tampered. Delete it and re-run this script." and does NOT proceed to use the file

#### Scenario: Piper bootstrap is idempotent

- **GIVEN** `piper_bootstrap.sh` has already been run successfully
- **WHEN** the user runs it a second time
- **THEN** the script detects existing files, verifies checksum, re-runs the sanity test, and exits 0 — no re-download

---

### Requirement: Secure input handling throughout

All training scripts SHALL apply defensive input handling: safe YAML loading, path boundary enforcement, path sanitization on config-derived values, and subprocess invocations without shell interpretation.

#### Scenario: YAML config loaded safely

- **WHEN** any training script loads a YAML config file
- **THEN** it uses `yaml.safe_load()` exclusively; `yaml.load()` and `yaml.unsafe_load()` MUST NOT appear anywhere in `training/scripts/`

#### Scenario: `model_name` sanitized before path construction

- **GIVEN** a config file with `model_name: "../../etc/passwd"`
- **WHEN** any training script reads this config
- **THEN** the script raises `ValueError: invalid model_name` and exits non-zero before constructing any filesystem path

#### Scenario: Output paths bounded to project directories

- **WHEN** any script constructs a path for writing files
- **THEN** the resolved `pathlib.Path` is asserted to be under `training/data/` or `training/out/`; any path that escapes those boundaries causes an immediate abort with a clear error

#### Scenario: No shell=True in subprocess calls

- **WHEN** any training script invokes a subprocess (Piper CLI, pip, etc.)
- **THEN** it uses `subprocess.run(cmd_list, shell=False)` with a list argument; `os.system()` and `subprocess.run(shell=True)` MUST NOT appear in any training script

---

### Requirement: YAML-driven training configuration

The training pipeline SHALL be driven by per-model YAML config files specifying target phrases, sample counts, augmentation settings, hyperparameters, and output path.

#### Scenario: Wake-word config file exists and is valid

- **WHEN** the proposal is applied
- **THEN** `training/configs/hey_roamin.yaml` exists, parses as valid YAML via `yaml.safe_load()`, and contains all confirmed OpenWakeWord schema fields: `model_name`, `output_dir`, `target_phrase` (list — NOT a bare string), `n_samples`, `n_samples_val`, `tts_batch_size`, `augmentation_batch_size`, `augmentation_rounds`, `background_paths` (list), `background_paths_duplication_rate` (list), `rir_paths` (list), `model_type`, `layer_size`, `batch_n_per_class`, `false_positive_validation_data_path`, `steps`, `max_negative_weight`, `target_false_positives_per_hour`

#### Scenario: target_phrase is always a list, never a bare string

- **GIVEN** any training config YAML
- **WHEN** the YAML is loaded and `target_phrase` is read
- **THEN** `target_phrase` is a YAML sequence (list) — a bare string value MUST NOT appear, because `openwakeword/train.py` iterates over it and a string causes character-by-character iteration, silently producing malformed adversarial text samples

#### Scenario: Consolidated stop-word config covers all 7 phrases

- **WHEN** `training/configs/stop_roamin.yaml` is loaded
- **THEN** `target_phrase` is a list containing exactly these 7 entries (any order): "stop roamin", "roamin stop", "shutup", "hey shutup", "roamin shutup", "be quiet", "silence" — all in the single `target_phrase` field

#### Scenario: Config output path produces correct filename for runtime

- **WHEN** either config is used to produce an ONNX file
- **THEN** the output filename is either `hey_roamin.onnx` or `stop_roamin.onnx` — matching the paths expected by `agent/core/voice/wake_word.py` lines 33–34 — so no runtime code changes are needed

---

### Requirement: Resumable, disk-backed synthetic sample generation

`training/scripts/generate_samples.py` SHALL produce synthetic training WAVs from Piper + audiomentations, persisting every file and manifest entry to disk so that an interrupted run can be resumed without redoing prior work.

#### Scenario: First-run generation completes

- **GIVEN** a valid YAML config and a bootstrapped training venv
- **WHEN** the user runs `python generate_samples.py --config training/configs/hey_roamin.yaml`
- **THEN** `n_samples` positive WAVs exist under `training/data/hey_roamin/positive/`, `negative_samples` negative WAVs exist under `training/data/hey_roamin/negative/`, and `manifest.json` lists every file with metadata, and the script exits 0

#### Scenario: Preview mode generates a small batch for inspection

- **WHEN** the user runs `python generate_samples.py --config training/configs/hey_roamin.yaml --preview 10`
- **THEN** exactly 10 positive + 10 negative samples are generated, the script prints a summary and exits 0; the manifest records these 10+10 entries so a subsequent full run resumes from entry 21

#### Scenario: Interrupted run resumes without data loss

- **GIVEN** a prior run produced 2,500 of 5,000 positive samples and was SIGKILL'd; manifest records 2,500 entries
- **WHEN** the user re-runs the same command
- **THEN** the script reads the manifest, verifies each listed file (size > 0), regenerates only the remaining 2,500, and exits 0

#### Scenario: Corrupt manifest entries are regenerated

- **GIVEN** 10 manifest entries point to zero-byte WAV files (from a crash during write)
- **WHEN** generate_samples.py resumes
- **THEN** those 10 entries are removed from the manifest and regenerated, without affecting the other valid entries

#### Scenario: Disk-full is caught proactively and handled gracefully

- **GIVEN** free disk space drops below 2 GB during generation
- **WHEN** the script detects this at its periodic disk-space check
- **THEN** it flushes the manifest, prints the current disk usage and a message pointing to `clean.sh`, pauses waiting for user input (do not crash), and resumes normally once the user frees space and presses Enter

#### Scenario: SIGINT triggers graceful shutdown

- **WHEN** the user presses Ctrl+C during sample generation
- **THEN** the script flushes the manifest, closes the Piper subprocess, and exits cleanly within 5 seconds; a subsequent invocation resumes from exactly the last successfully written sample

---

### Requirement: Background audio and RIR data provisioned before augmentation

`training/setup/data_bootstrap.sh` SHALL download all external data required by the `--augment_clips` stage before training begins.

#### Scenario: data_bootstrap.sh completes and all required paths exist

- **GIVEN** a successful `wsl_bootstrap.sh` and `piper_bootstrap.sh` completion
- **WHEN** the user runs `bash training/setup/data_bootstrap.sh`
- **THEN** `training/data/background/` contains ≥ 1 hour of 16kHz WAV audio, `training/data/rir/` contains ≥ 1 RIR WAV file, `training/data/fp_val.npy` exists (or the script confirms `--augment_clips` will generate it automatically), and the script exits 0

#### Scenario: Missing background data causes augment step to abort with clear error

- **GIVEN** `training/data/background/` is empty or missing
- **WHEN** the user runs `python augment_samples.py --config training/configs/hey_roamin.yaml`
- **THEN** the script exits non-zero with "Background audio directory is empty — run training/setup/data_bootstrap.sh first" before invoking any OWW CLI

---

### Requirement: Augmentation step produces feature arrays before training

`training/scripts/augment_samples.py` SHALL wrap `python -m openwakeword.train --augment_clips`, validate all preconditions, and produce the feature arrays required by the training step.

#### Scenario: Augmentation completes and feature files exist

- **GIVEN** positive WAVs exist in `training/data/<model_name>/positive/` and background/RIR data is present
- **WHEN** the user runs `python augment_samples.py --config training/configs/hey_roamin.yaml`
- **THEN** augmented feature `.npy` files exist in `training/data/hey_roamin/`, the script exits 0, and a pointer to `train_model.py` is printed

---

### Requirement: Training driver produces ONNX model with epoch checkpointing

`training/scripts/train_model.py` SHALL invoke the OpenWakeWord training API with YAML-configured hyperparameters, write per-epoch checkpoints, and export the resulting classifier as an ONNX file.

#### Scenario: Training completes with valid ONNX artifact

- **GIVEN** `training/data/hey_roamin/` is populated and a valid YAML config exists
- **WHEN** the user runs `python train_model.py --config training/configs/hey_roamin.yaml`
- **THEN** the two-sequence training output is printed to stdout and logged, `training/out/hey_roamin.onnx` is produced (size 150 KB–500 KB, written by OWW to `output_dir/model_name.onnx` as configured), `training/out/hey_roamin.meta.json` is written with all fields from `design.md §Observability`, and the script exits 0

#### Scenario: Interrupted training requires full restart

- **GIVEN** training was interrupted mid-run (OOM, Ctrl+C, terminal close)
- **WHEN** the user re-runs `python train_model.py --config training/configs/hey_roamin.yaml`
- **THEN** the script starts training from scratch (OWW writes no checkpoint files at any point); previously generated WAVs and augmented features are intact and do not need to be regenerated; only training time is lost

#### Scenario: Pre-flight warning is printed before training starts

- **WHEN** `train_model.py` is invoked (without `--dry-run`)
- **THEN** the script prints "Training has NO checkpoint support — if interrupted you must restart from scratch. Recommend running inside tmux or with nohup." before invoking the OWW CLI

#### Scenario: Training log is written for post-hoc diagnosis

- **WHEN** `train_model.py` completes (success or error)
- **THEN** `training/out/<model_name>.log` contains the full stdout of the training run, including every epoch's loss and accuracy

---

### Requirement: Verification script tests all 7 stop phrases individually

`training/scripts/verify_model.py` SHALL test a trained ONNX model against silence AND against each individual phrase in the model's config, exiting 0 only if all tests pass.

#### Scenario: A well-trained stop model passes all 7 phrase tests

- **GIVEN** a trained `training/out/stop_roamin.onnx` and `training/configs/stop_roamin.yaml`
- **WHEN** the user runs `python verify_model.py --model training/out/stop_roamin.onnx --config training/configs/stop_roamin.yaml`
- **THEN** the script generates a fresh Piper WAV for each of the 7 phrases, runs the ONNX against each (scores must all be ≥ 0.5), tests silence (score must be < 0.1), prints a per-phrase score table, and exits 0

#### Scenario: Weak phrase fails verification with actionable message

- **GIVEN** the model scores 0.31 on "silence" (the phrase, not quiet audio) but ≥ 0.5 on the other 6 phrases
- **WHEN** verification runs
- **THEN** the script exits non-zero and prints:
  ```
  FAIL: phrase "silence" scored 0.310 < 0.500
  → Retrain with higher n_samples in stop_roamin.yaml, or consider splitting into two models.
  ```

#### Scenario: Model false-positives on silence

- **GIVEN** the model scores 0.72 on 3 s of zero-filled audio
- **WHEN** verification runs
- **THEN** the script exits non-zero and prints:
  ```
  FAIL: silence confidence 0.720 exceeds 0.100
  → Model has excessive false positives. Retrain with higher negative_samples in config.
  ```

#### Scenario: Verify script rejects paths outside project

- **GIVEN** the user runs `python verify_model.py --model /etc/passwd`
- **WHEN** the script validates the `--model` argument
- **THEN** it exits non-zero with "Invalid model path — must be a .onnx file within the project directory"

---

### Requirement: Consolidated stop-word model in a single ONNX file

The `stop_roamin.onnx` produced SHALL be a single ONNX classifier trained on all 7 stop phrases, not 7 separate per-phrase classifiers.

#### Scenario: Only one stop-word ONNX file exists

- **WHEN** the pipeline completes for `stop_roamin.yaml`
- **THEN** `training/out/` contains exactly one file matching `stop_*.onnx` (named `stop_roamin.onnx`)

#### Scenario: Single file is loaded by the runtime without code changes

- **GIVEN** `models/wake_word/stop_roamin.onnx` exists
- **WHEN** Roamin starts
- **THEN** `agent/core/voice/wake_word.py` loads it at `_STOP_MODEL_PATH` (line 34) without any code modification

---

### Requirement: Zero runtime code changes for model loading integration

Deploying trained models SHALL require ONLY copying the ONNX files to `models/wake_word/` and restarting Roamin. No Python code changes are required for model loading. (TTS wiring for stop-word interruption is a separate concern and a separate proposal.)

#### Scenario: Drop-in integration for wake word

- **GIVEN** `models/wake_word/hey_roamin.onnx` exists
- **WHEN** Roamin restarts
- **THEN** the startup log shows `Wake model loaded: hey_roamin.onnx` — not the `hey_jarvis` fallback message; no files under `agent/` were modified

#### Scenario: Drop-in integration for stop word model loading

- **GIVEN** `models/wake_word/stop_roamin.onnx` exists
- **WHEN** `WakeWordListener._load_stop_model()` is called
- **THEN** the model loads at `_STOP_MODEL_PATH` without error; stop-word frame scoring is active at the runtime level (TTS triggering of stop listening is a separate concern)

#### Scenario: Removing trained models falls back gracefully

- **GIVEN** both trained `.onnx` files are deleted from `models/wake_word/`
- **WHEN** Roamin restarts
- **THEN** the startup log shows the `hey_jarvis` fallback message and wake-word detection remains functional via the built-in model

---

### Requirement: Complete meta.json diagnostics artifact

Every training run SHALL produce `training/out/<model_name>.meta.json` with a complete set of diagnostic fields sufficient to diagnose real-world accuracy problems without requiring the audio data.

#### Scenario: meta.json contains all required fields

- **WHEN** `train_model.py` completes successfully
- **THEN** `<model_name>.meta.json` contains at minimum: `model_name`, `model_input_shape`, `sample_rate`, `accuracy`, `true_positive_rate`, `false_positive_rate`, `false_reject_rate`, `training_duration_seconds`, `epochs`, `final_loss`, `epoch_losses` (full list), `config_hash`, `git_commit`, `hardware`, `openwakeword_version`, `torch_version`, `piper_voice`, `n_positive_samples`, `n_negative_samples`, `target_phrases`, `augmentations`

---

### Requirement: Training artifacts excluded from version control

The root `.gitignore` SHALL exclude `training/data/`, `training/out/`, and `training/venv/` to prevent accidental commits of multi-GB synthetic datasets, checkpoints, and local Python environments.

#### Scenario: Large generated artifacts are gitignored

- **GIVEN** the user has run full sample generation (5+ GB in `training/data/`)
- **WHEN** the user runs `git status`
- **THEN** nothing under `training/data/`, `training/out/`, or `training/venv/` appears as untracked

#### Scenario: Config files, scripts, and docs ARE tracked

- **WHEN** the user runs `git status` after applying the proposal
- **THEN** `training/configs/*.yaml`, `training/setup/*.sh`, `training/scripts/*.py`, `training/README.md`, and `training/requirements-training.txt` appear as tracked (or newly added) files

#### Scenario: Trained ONNX models ARE committed

- **GIVEN** `models/wake_word/hey_roamin.onnx` and `models/wake_word/stop_roamin.onnx` have been verified and are ready to deploy
- **WHEN** the user runs `git add models/wake_word/*.onnx`
- **THEN** both files are staged normally (`.gitignore` does not exclude `models/wake_word/`)

---

### Requirement: End-to-end documentation is complete and linear

`docs/WAKE_WORD_TRAINING.md` SHALL be a single linear walkthrough covering every phase from WSL2 installation through model integration.

#### Scenario: Doc covers all required phases

- **WHEN** the proposal is applied
- **THEN** `WAKE_WORD_TRAINING.md` contains sections for: prerequisites (including Windows build ≥ 22621 and NVIDIA driver ≥ 550), WSL2 install, `.wslconfig` memory tuning, CUDA install, bootstrap scripts, `--preview` mode sample inspection, full sample generation, training, verification (including the per-phrase table), TTS wiring gap explanation, integration, tuning, adding new stop phrases, troubleshooting, and hardware time estimates

#### Scenario: Doc uses exact absolute paths

- **WHEN** `WAKE_WORD_TRAINING.md` references a file or command
- **THEN** all paths are absolute (`C:\AI\roamin-ambient-agent-tts\...`) or unambiguous repo-relative; "your project folder" never appears

#### Scenario: TTS wiring gap is explicitly called out

- **WHEN** the integration section is reached
- **THEN** the doc includes a clearly marked note: "Stop-word TTS interruption not yet wired — see tts-stop-word-wiring proposal"; this is not buried in a footnote
