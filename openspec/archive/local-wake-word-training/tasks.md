# Tasks — Local OpenWakeWord Training Pipeline

> **Pre-implementation gate (§0):** Complete all tasks in §0 before writing any code. Several decisions depend on the actual OpenWakeWord training API, which must be validated from source before `train_model.py` is authored.

## 0. Pre-implementation Validation (Do Before Coding Begins)

**Partially confirmed from source audit (2026-04-17):**
- Training CLI: `python -m openwakeword.train --training_config <yaml> --generate_clips | --augment_clips | --train_model`
- Python API: `openwakeword.Model.auto_train(X_train, X_val, false_positive_val_data, steps=45400, max_negative_weight=300, target_false_positives_per_hour=0.2)`
- piper-sample-generator: `git clone https://github.com/rhasspy/piper-sample-generator` (confirmed NOT pip-installable)
- OpenWakeWord internally uses `yaml.load(..., yaml.Loader)` — this is OWW's own code; our wrapper scripts use `yaml.safe_load()` for any configs we author

**Still required before coding:**
- [ ] 0.1 Confirm exact YAML field names accepted by the installed `openwakeword` version (`target_phrase` vs `target_phrases`, and whether a list is accepted for multi-phrase generation). Run:
    ```bash
    python -m openwakeword.train --help
    grep -n "target_phrase" $(python -c "import openwakeword; import os; print(os.path.dirname(openwakeword.__file__))")/train.py
    ```
- [ ] 0.2 Download `en_US-libritts_r-medium.pt` and record its SHA256 checksum for `wsl_bootstrap.sh`:
    ```bash
    wget https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt
    sha256sum en_US-libritts_r-medium.pt
    ```
    Hardcode the resulting hash in `wsl_bootstrap.sh`. Also verify `pip install piper-sample-generator` succeeds and `python -m piper_sample_generator --help` runs without error in the training venv.
- [ ] 0.3 Record SHA256 of `validation_set_features.npy` after download and hardcode in `data_bootstrap.sh`:
    ```bash
    wget https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy
    sha256sum validation_set_features.npy
    python -c "import numpy as np; d=np.load('validation_set_features.npy'); print(d.shape)"
    ```
    Confirm file loads without error and has expected shape (N, feature_dim).
- [ ] 0.5 Confirm background audio download source and URL for `data_bootstrap.sh`:
    - Preferred: FMA small subset — find the direct `wget`-able URL from `github.com/mdeff/fma` (AWS-hosted). Note: FMA small is ~7 GB total; `data_bootstrap.sh` should download a 1-hour subset only, not the full archive.
    - Alternative: use `yt-dlp` to pull ~1 hr of Creative Commons audio from a curated playlist (no large archive required).
    - Record chosen URL/method and any licence constraints.
- [ ] 0.6 Confirm MIT Room Impulse Response Survey download URL:
    - Expected at: `http://mcdermottlab.mit.edu/Reverb/IR_Survey.zip` — verify HTTPS availability and file size (~500 MB).
    - Record SHA256 and add to `data_bootstrap.sh` integrity check.
- [ ] 0.4 Find the SHA256 checksum for `en_US-lessac-medium.onnx` from the Piper/rhasspy release page or by downloading and computing `sha256sum en_US-lessac-medium.onnx`. Record this in `training/setup/piper_bootstrap.sh`

## 1. Prerequisite Verification (User-Performed, Documented in §9)

- [ ] 1.1 Confirm NVIDIA GPU present: `Get-WmiObject Win32_VideoController | Select Name` in PowerShell
- [ ] 1.2 Confirm NVIDIA driver ≥ 550 (required for CUDA 12.4 WSL2 passthrough): `nvidia-smi` on Windows host
- [ ] 1.3 Confirm Windows build ≥ 22621 (`winver`): required for WSL2 GPU passthrough
- [ ] 1.4 Confirm ≥ 40 GB free disk space on `C:` — breakdown:
    - `validation_set_features.npy`: ~2–4 GB (11 hrs of pre-computed features)
    - `en_US-libritts_r-medium.pt`: ~300 MB
    - Background audio (1 hr, 16kHz WAV): ~500 MB
    - MIT RIR Survey: ~500 MB
    - Generated positive WAVs (5000 × 2 models): ~5–10 GB
    - Augmented feature arrays: ~3–6 GB
    - Training venv + packages: ~5 GB
    - Safety buffer: ~5 GB
    - **Total: ~22–31 GB; require ≥ 40 GB free to be safe**
- [ ] 1.5 Disable Windows sleep mode: Settings → System → Power & Sleep → Sleep = Never
- [ ] 1.6 Create `C:\Users\<username>\.wslconfig` (if it doesn't exist) with:
    ```ini
    [wsl2]
    memory=16GB
    processors=8
    swap=4GB
    ```
    Close any WSL2 sessions and run `wsl --shutdown` in PowerShell to apply
- [ ] 1.7 Close LM Studio and other GPU-intensive apps during training to avoid VRAM contention

## 2. Directory & File Scaffolding

- [ ] 2.1 Create directory tree at project root:
    ```
    training/
    ├── configs/
    ├── setup/
    ├── scripts/
    ├── data/        ← gitignored
    └── out/         ← gitignored
    ```
- [ ] 2.2 Create `training/README.md` — one-page quick-start with links to `docs/WAKE_WORD_TRAINING.md` and a copy of the hardware time estimates table from `design.md`
- [ ] 2.3 Create `training/requirements-training.txt` (see §4)
- [ ] 2.4 Update root `.gitignore` — add these three entries (if not already present):
    ```
    training/data/
    training/out/
    training/venv/
    ```
- [ ] 2.5 Create `models/wake_word/README.md` describing:
    - Expected files: `hey_roamin.onnx`, `stop_roamin.onnx`
    - How to produce them: pointer to `docs/WAKE_WORD_TRAINING.md`
    - What happens if they're absent: runtime falls back to `hey_jarvis` (see `wake_word.py` line 196–214)
    - Pre-existing gap note: stop-word interruption of TTS requires the separate `tts-stop-word-wiring` proposal
- [ ] 2.6 Add a short "Custom Wake Word" section to root `README.md` pointing at `docs/WAKE_WORD_TRAINING.md`

## 3. WSL2 + CUDA Setup Scripts

- [ ] 3.1 Create `training/setup/wsl_bootstrap.sh` — idempotent installer:
    - Opens with `#!/usr/bin/env bash` and `set -euo pipefail`
    - Verifies it is running inside WSL2 Ubuntu 22.04 (checks `/etc/os-release`); aborts with clear message if not
    - Verifies `nvidia-smi` is accessible; aborts with "NVIDIA GPU passthrough not available — see Prerequisites in WAKE_WORD_TRAINING.md" if not
    - Runs `sudo apt-get update && sudo apt-get upgrade -y`
    - Installs: `python3.10 python3.10-venv python3.10-dev build-essential git wget ffmpeg` (exact package names, no variable interpolation)
    - Creates `training/venv/` and activates it
    - Upgrades pip/setuptools/wheel
    - Installs PyTorch with CUDA 12.4: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124`
    - Installs `-r training/requirements-training.txt`
    - Installs piper-sample-generator (pip is the primary method, confirmed from official README):
        ```bash
        pip install piper-sample-generator
        pip install piper-phonemize    # required dep not bundled in pip package
        pip install webrtcvad           # required dep not bundled in pip package
        ```
    - Downloads the LibriTTS-R generator model (`.pt` format, distinct from piper-tts `.onnx`):
        ```bash
        mkdir -p training/data/piper_models/
        wget https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt \
             -O training/data/piper_models/en_US-libritts_r-medium.pt
        ```
        Verifies SHA256 checksum of `.pt` file against hardcoded value recorded at §0.2; aborts on mismatch
    - Installs `tmux` for resilient training sessions: `sudo apt-get install -y tmux`
    - Verifies GPU: `python -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'"` — aborts on assertion error with instructions
    - Prints summary: installed package versions for `torch`, `openwakeword`, `speechbrain`, `onnxruntime-gpu`
    - Supports `--dry-run` flag: prints each step without executing; allows user to review before committing
    - Supports `--uninstall` flag: removes `training/venv/` and any repo clones made by the script
- [ ] 3.2 Create `training/setup/piper_bootstrap.sh` — idempotent Piper voice provisioner:
    - Creates `~/.local/share/piper/models/` if not present
    - Downloads `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json` via `wget` over HTTPS only (no HTTP fallback)
    - Verifies SHA256 checksum of the downloaded `.onnx` against the hardcoded expected value found in §0.4; aborts on mismatch
    - Runs sanity test: `echo "hey roamin" | piper --model en_US-lessac-medium --output_file /tmp/piper_sanity.wav` — verifies output file exists and is ≥ 10 KB
    - Is idempotent: if model files already exist and checksum matches, skips download and re-runs sanity test only
    - Supports `--dry-run` flag

- [ ] 3.3 Create `training/setup/data_bootstrap.sh` — downloads all external training data required by `--augment_clips` and `--train_model`:
    - Creates `training/data/background/`, `training/data/rir/`, and `training/data/` dirs if not present
    - Downloads background audio WAVs (≥ 1 hour, 16 kHz) into `training/data/background/`:
      - URL/method confirmed at §0.5 — script hardcodes the chosen source
      - Converts any non-16kHz audio to 16kHz mono with `ffmpeg -ar 16000 -ac 1`
      - Verifies total duration ≥ 3600 seconds after conversion using `ffprobe`; exits with error if insufficient
    - Downloads MIT Room Impulse Response Survey WAVs into `training/data/rir/`:
      - URL confirmed at §0.6 (expected: `http://mcdermottlab.mit.edu/Reverb/IR_Survey.zip`)
      - Verifies SHA256 of zip before extraction; extracts `.wav` files only
      - Verifies ≥ 1 RIR WAV file exists after extraction
    - Downloads `validation_set_features.npy` (confirmed pre-built; NOT auto-generated):
      ```bash
      wget https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy \
           -O training/data/validation_set_features.npy
      ```
      Verifies SHA256 checksum (recorded at §0.3); aborts on mismatch
    - Is idempotent: skips any file that already exists and has size > 0
    - Supports `--dry-run` flag
    - Prints final summary: total background audio duration (hours), RIR count, fp_val.npy size
    - Exits non-zero with actionable message if any required download fails

## 4. Training Dependencies

- [ ] 4.1 Create `training/requirements-training.txt` with pinned ranges that coexist on Python 3.10 + CUDA 12.4:
    ```
    # Training-only deps — install inside training/venv/ ONLY.
    # Do NOT add these to the root requirements.txt.
    openwakeword>=0.6.0
    speechbrain>=1.0.0
    onnx>=1.17.0
    onnxruntime-gpu>=1.20.0
    audiomentations>=0.39.0
    pronouncing>=0.2.0
    deep-phonemizer>=0.0.17
    datasets>=2.20.0
    piper-tts>=1.2.0
    pyyaml>=6.0
    numpy>=1.26,<2.0
    pandas>=2.2,<3.0
    ```
    NOTE: `torch`, `torchvision`, `torchaudio` are installed separately by `wsl_bootstrap.sh` from the CUDA 12.4 index URL — they are NOT listed here to avoid pip installing the CPU-only versions.
- [ ] 4.2 Add a comment header explaining the numpy and pandas version caps and why they exist (binary incompatibility history — see `design.md` D3)

## 5. YAML Configs

- [ ] 5.1 Create `training/configs/hey_roamin.yaml` using the confirmed OpenWakeWord YAML schema:
    ```yaml
    # Wake word training config — passed to: python -m openwakeword.train --training_config hey_roamin.yaml
    # All field names confirmed from openwakeword/train.py source (2026-04-17)
    # model_name must match ^[a-zA-Z0-9_-]+$ — used to construct output filename

    model_name: hey_roamin
    output_dir: "training/out/"          # ONNX saved as output_dir/model_name.onnx

    # Stage 1: --generate_clips (piper-sample-generator)
    # IMPORTANT: target_phrase MUST be a list — a bare string causes character-iteration bug
    target_phrase:
      - "hey roamin"
      - "hey roaming"                    # common mishearing
      - "hey rome in"                    # phonetic variation
    n_samples: 5000                      # total positive WAVs across all phrases
    n_samples_val: 500                   # held-out validation positives
    tts_batch_size: 100                  # piper-sample-generator GPU batch size

    # Stage 2: --augment_clips
    augmentation_batch_size: 100
    augmentation_rounds: 10              # n_samples × rounds = 50,000 total training examples
    background_paths:
      - "training/data/background/"      # downloaded by data_bootstrap.sh (§3.3)
    background_paths_duplication_rate:
      - 1
    rir_paths:
      - "training/data/rir/"            # MIT IR Survey; downloaded by data_bootstrap.sh

    # Model architecture
    model_type: "dnn"
    layer_size: 128
    batch_n_per_class: 500

    # Validation data (pre-downloaded by data_bootstrap.sh §3.3)
    # Source: https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy
    false_positive_validation_data_path: "training/data/validation_set_features.npy"

    # Feature file paths — script auto-populates 'positive' and 'adversarial_negative' keys;
    # provide empty dict so script can mutate it (required field, KeyError if absent)
    feature_data_files: {}

    # Stage 3: --train_model — locked hyperparameters
    steps: 45400                         # sequence-1 steps (Colab: number_of_training_steps)
    max_negative_weight: 300             # peak penalty  (Colab: false_activation_penalty)
    target_false_positives_per_hour: 0.2 # sequence-2 trigger threshold (OWW default)
    ```
- [ ] 5.2 Create `training/configs/stop_roamin.yaml` — consolidated 7-phrase stop model:
    ```yaml
    # Consolidated stop-word config — 7 phrases in one target_phrase list.
    # OWW natively iterates the list; single --generate_clips pass covers all phrases.
    # See docs/WAKE_WORD_TRAINING.md for all fields.

    model_name: stop_roamin
    output_dir: "training/out/"

    target_phrase:                       # all 7 — OWW distributes n_samples across list
      - "stop roamin"
      - "roamin stop"
      - "shutup"
      - "hey shutup"
      - "roamin shutup"
      - "be quiet"
      - "silence"
    n_samples: 5000                      # ~715 WAVs per phrase; confirm distribution at §0.1
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
- [ ] 5.3 Add inline YAML comments explaining each field, its Colab UI label equivalent where applicable, and a link to `docs/WAKE_WORD_TRAINING.md §Tuning`
- [ ] 5.4 After §0.1 confirms that `n_samples` is total-count-not-per-phrase, and confirms sample distribution across the `target_phrase` list, update the `n_samples` comment accordingly

## 6. Sample Generation Script

- [ ] 6.1 Create `training/scripts/generate_samples.py`:
    - **Role:** Wraps `python -m openwakeword.train --generate_clips` with resumability, disk-space checking, and multi-phrase looping for the consolidated stop model
    - CLI: `python generate_samples.py --config <path/to/yaml> [--preview N] [--dry-run]`
    - Loads config with `yaml.safe_load()` (never `yaml.load()` or `yaml.unsafe_load()`)
    - Validates `model_name` against `^[a-zA-Z0-9_-]+$`; raises `ValueError` on any other value
    - Resolves output dirs via `pathlib.Path`; asserts all paths are within `training/data/` before any write
    - For **hey_roamin**: invokes `--generate_clips` once; for **stop_roamin**: loops over all phrases in `target_phrase_alternative_pronunciations`, invoking `--generate_clips` once per phrase, each depositing WAVs into the shared `training/data/stop_roamin/positive/` directory
    - `--preview N`: generates only N positive samples (one phrase only), prints WAV count + sample path, exits. Used to verify Piper + piper-sample-generator integration before full run
    - `--dry-run`: prints what would be generated without running Piper or writing files
    - Checks disk space (via `shutil.disk_usage()`) before each phrase batch; if < 2 GB free, pauses with actionable warning pointing to `clean.sh` and waits for user input before continuing
    - Each WAV is verified ≥ 1,024 bytes before being added to the manifest; corrupt/empty WAVs are retried up to 3 times, then skipped with a warning
    - Manifest-based resume: on restart, reads manifest, verifies each listed file (size > 0), regenerates zero-byte or missing entries, skips already-complete phrase batches
    - SIGINT handler: flushes manifest, waits for in-flight OWW subprocess to exit cleanly (timeout 5 s), then exits
    - atexit handler: same as SIGINT (covers `kill -15` and clean exits)
- [ ] 6.2 On completion: prints summary — total positive samples by phrase, disk used, pointer to next step (`augment_samples.py`)

## 6b. Augmentation Script (NEW — previously missing)

- [ ] 6b.1 Create `training/scripts/augment_samples.py`:
    - **Role:** Wraps `python -m openwakeword.train --augment_clips`, which mixes positive WAVs with background audio and RIR files to produce augmented feature arrays
    - CLI: `python augment_samples.py --config <path/to/yaml> [--dry-run]`
    - Validates config with `yaml.safe_load()` and `model_name` regex before invoking OWW CLI
    - Checks that `background_paths` and `rir_paths` directories exist and are non-empty; exits with clear error if missing (pointer to `data_bootstrap.sh`)
    - Checks that `false_positive_validation_data_path` exists; exits with clear error if missing (pointer to `data_bootstrap.sh`)
    - Checks disk space before starting: augmented features can be 2–4 GB; warns if < 5 GB free
    - Invokes `python -m openwakeword.train --training_config <yaml> --augment_clips` via `subprocess.run(cmd_list, shell=False)`
    - On completion: prints summary — augmented feature file paths, sizes, pointer to next step (`train_model.py`)
    - `--dry-run`: validates all preconditions (paths, disk) without running augmentation

## 7. Training Script

- [ ] 7.1 Create `training/scripts/train_model.py`:
    - **Role:** Wraps `python -m openwakeword.train --train_model`, which internally calls `openwakeword.Model.auto_train(steps=45400, max_negative_weight=300, target_false_positives_per_hour=0.2)`
    - **No resume capability** — OWW writes zero checkpoints. If interrupted, re-run. Mitigations: sleep disabled, .wslconfig tuned, tmux/nohup recommended.
    - CLI: `python train_model.py --config <path/to/yaml> [--dry-run]`
    - Loads config with `yaml.safe_load()` only
    - Validates `model_name` before any path construction (same regex as §6.1)
    - Checks that augmented feature files exist in `training/data/<model_name>/` (produced by `augment_samples.py`); exits with clear error if missing
    - Prints pre-flight warning: "Training has NO checkpoint support — if interrupted you must restart from scratch. Recommend running in tmux or with nohup."
    - Invokes `python -m openwakeword.train --training_config <yaml> --train_model` via `subprocess.run(cmd_list, shell=False)`
    - Tees OWW training stdout to both terminal and `training/out/<model_name>.log` simultaneously
    - On completion: OWW exports ONNX to `output_dir/model_name.onnx` (as configured in YAML); script verifies file exists and is ≥ 150 KB, prints copy command for integration
    - Writes `training/out/<model_name>.meta.json` with all fields from `design.md §Observability`
    - `--dry-run`: validates config and checks feature files exist; prints expected duration estimate without running training
- [ ] 7.2 `WAKE_WORD_TRAINING.md` §Training section includes: recommended invocation `tmux new -s training && python train_model.py --config ...` so training survives terminal disconnects; also documents `nohup` alternative for users unfamiliar with tmux

## 8. Verification Script

- [ ] 8.1 Create `training/scripts/verify_model.py`:
    - CLI: `python verify_model.py --model <path/to/onnx> [--config <yaml>] [--audio <wav>]`
    - Validates that `--model` path has `.onnx` extension and exists within the project directory; rejects paths outside project root
    - Loads the ONNX model via `openwakeword.Model`
    - **Test 1 — Silence:** runs model against 3 s of zero-filled audio; confidence must be < 0.1. If ≥ 0.1: prints "FAIL: silence confidence {X:.3f} exceeds 0.1 — model has too many false positives. Retrain with higher `negative_samples` in config."
    - **Test 2 — All target phrases:** if `--config` is provided, generates a fresh Piper WAV for EACH phrase in `target_phrases` and tests each individually. Passes if ALL score ≥ 0.5. On failure: prints "FAIL: phrase '{phrase}' scored {score:.3f} < 0.5 — model doesn't reliably detect this phrase. Retrain with higher `n_samples` or rephrase." Reports the score for every phrase in a table.
    - **Test 3 — Provided audio (optional):** if `--audio` is given, runs the model against that WAV; prints the raw confidence score without a pass/fail gate (informational)
    - Prints a final PASS/FAIL summary with all scores
    - Exits 0 on PASS, non-zero on FAIL
- [ ] 8.2 On PASS: prints integration instructions (copy path, restart command)

## 9. Comparison Utility

- [ ] 9.1 Create `training/scripts/compare_models.py`:
    - CLI: `python compare_models.py --model-a <path> --model-b <path> --config <yaml>`
    - Runs verify_model logic against both models using the same phrase set from the config
    - Prints side-by-side table: per-phrase confidence for Model A vs. Model B
    - Prints recommendation: "Model A is better on {N} of {M} phrases — recommend deploying Model A"
    - Useful for A/B testing after a retrain or hyperparameter change

## 10. Cleanup Utility

- [ ] 10.1 Create `training/scripts/clean.sh`:
    - `--data`: removes `training/data/` contents only (keeps manifest structure for fast inspect)
    - `--out`: removes `training/out/*.onnx`, `*.ckpt`, `*.log`, `*.meta.json`
    - `--all`: removes both
    - `--dry-run`: prints what would be deleted without deleting
    - Always prints bytes-freed summary after deletion

## 11. Security Hardening (Apply to All Scripts)

- [ ] 11.1 Audit every `yaml.load()` call — replace with `yaml.safe_load()`. No exceptions
- [ ] 11.2 Audit every `subprocess` call — ensure `shell=False` everywhere. Replace any `os.system()` calls with `subprocess.run(cmd_list, shell=False)`
- [ ] 11.3 Add `model_name` validation (`^[a-zA-Z0-9_-]+$`) to every script that constructs a path from config
- [ ] 11.4 Add output path boundary check: resolve path and assert it is under `training/data/` or `training/out/` before any file write
- [ ] 11.5 In `piper_bootstrap.sh`: add SHA256 checksum verification of downloaded `en_US-lessac-medium.onnx` before first use (hardcode expected checksum from §0.4)
- [ ] 11.6 In `verify_model.py`: validate `--model` argument is a `.onnx` file inside the project root before loading

## 12. Documentation

- [ ] 12.1 Create `docs/WAKE_WORD_TRAINING.md` with exactly these sections:
    1. **Overview** — what this produces, why local vs Colab, pre-existing TTS wiring gap note
    2. **Prerequisites** — Windows build ≥ 22621, NVIDIA driver ≥ 550, ≥ 25 GB free, sleep mode disabled
    3. **WSL2 Installation** — `wsl --install Ubuntu-22.04`, verify version with `wsl --list --verbose`
    4. **WSL2 Memory Tuning** — `.wslconfig` creation, `wsl --shutdown` to apply, why this matters
    5. **CUDA 12.4 Installation** — inside WSL2, `nvcc --version` and `nvidia-smi` verification
    6. **Running `wsl_bootstrap.sh`** — exact command, expected output, how to interpret errors
    7. **Running `piper_bootstrap.sh`** — exact command, expected output, sanity WAV verification
    8. **Downloading training data** — exact `data_bootstrap.sh` command, expected output, disk usage
    9. **Generating samples: `hey_roamin`** — exact command with `--preview 10` first, then full run
    10. **Augmenting samples: `hey_roamin`** — exact `augment_samples.py` command, expected runtime, output paths
    11. **Training: `hey_roamin`** — exact command, reading the two-sequence output, estimated time per GPU
    12. **Verifying: `hey_roamin`** — exact command, interpreting PASS/FAIL, what to do on failure
    13. **Repeat for `stop_roamin`** — steps 9–12 with `stop_roamin.yaml`; note generate loops all 7 phrases; verify tests all 7 individually
    12. **Integration** — copy commands (Windows PowerShell paths), restart Roamin, what to look for in logs
    13. **TTS Wiring Gap** — explain that `stop_roamin.onnx` will load successfully but stop-word interruption of TTS requires the separate `tts-stop-word-wiring` proposal; link to it once it exists
    14. **Tuning** — `ROAMIN_WAKE_THRESHOLD` env var, when to lower vs raise, when to retrain vs tune
    15. **Adding new stop phrases** — update `target_phrases` in `stop_roamin.yaml`, rerun generate + train + verify + copy + restart
    16. **Troubleshooting** — table covering: `nvidia-smi` not found, PyTorch no GPU, Piper model not found, training OOM, disk full during generation, checkpoint corruption, low real-world recall
    17. **Hardware reference** — copy of time-estimate table from `design.md`
- [ ] 12.2 All code blocks use fenced syntax with explicit language tags (`bash`, `powershell`, `ini`, `yaml`)
- [ ] 12.3 All paths are absolute or repo-relative from `C:\AI\roamin-ambient-agent-tts\`; never "your project folder"
- [ ] 12.4 Add a note at the top: "Estimated time: 8–12 hours on RTX 3060 (mostly unattended). Read §4 .wslconfig before starting."

## 13. Integration Smoke Test

- [ ] 13.1 After training and copying both ONNX files to `models/wake_word/`, restart Roamin
- [ ] 13.2 Confirm startup log shows `Wake model loaded: hey_roamin.onnx` — NOT the `hey_jarvis` fallback message
- [ ] 13.3 Confirm startup log does NOT show "Custom wake model not found" (that would indicate path mismatch)
- [ ] 13.4 Say "hey roamin" — confirm log shows `Wake word detected: hey_roamin (score=...)` within 1 second
- [ ] 13.5 Say "hey jarvis" — confirm it does NOT trigger (false positive test)
- [ ] 13.6 Say each of the 7 stop phrases — confirm each logs `Stop word detected: stop_roamin (score=...)`
    - Note: stop-word detection will work at the runtime level, but TTS interruption will not function until `tts-stop-word-wiring` is complete
- [ ] 13.7 Verify `ctrl+space` hotkey still triggers STT normally — no regression
- [ ] 13.8 Run existing test suite: `python -m pytest tests/ -v` — no new failures
- [ ] 13.9 Confirm both `.onnx` files are ≥ 150 KB and ≤ 500 KB (sanity check on model integrity)
- [ ] 13.10 Commit trained models: `git add models/wake_word/hey_roamin.onnx models/wake_word/stop_roamin.onnx && git commit -m "feat(wake-word): add trained custom wake word and stop word models"`

## 14. Automated Verification Checklist

- [ ] 14.1 `bash training/setup/wsl_bootstrap.sh` exits 0 on a fresh WSL2 Ubuntu 22.04 with NVIDIA passthrough
- [ ] 14.2 `bash training/setup/wsl_bootstrap.sh --dry-run` prints all planned steps without executing any
- [ ] 14.3 `bash training/setup/piper_bootstrap.sh` exits 0 and produces a non-empty WAV from the sanity test
- [ ] 14.4 `python training/scripts/generate_samples.py --config training/configs/hey_roamin.yaml --preview 10` completes in under 60 seconds, produces 10 positive WAVs, exits 0
- [ ] 14.5 Interrupt `generate_samples.py` mid-run with Ctrl+C, re-run — confirm it resumes from where it left off (manifest continuity verified)
- [ ] 14.6 Full `generate_samples.py` run completes for `hey_roamin.yaml`, produces 5000 positive WAVs
- [ ] 14.6b `python training/scripts/augment_samples.py --config training/configs/hey_roamin.yaml` completes, produces augmented feature files in `training/data/hey_roamin/`
- [ ] 14.7 `train_model.py` for `hey_roamin.yaml` completes (both sequences), produces `.onnx` ≥ 150 KB and `.meta.json`
- [ ] 14.8 `verify_model.py` for `hey_roamin.onnx` exits 0 with all phrase scores ≥ 0.5 and silence score < 0.1
- [ ] 14.9 Repeat 14.4–14.8 for `stop_roamin.yaml` — all pass; confirm generate loops all 7 phrases; all 7 stop phrases individually score ≥ 0.5 in verify
- [ ] 14.10 `compare_models.py` runs without error against two ONNX files, prints a recommendation
- [ ] 14.11 `clean.sh --dry-run` prints expected deletions without deleting anything
- [ ] 14.12 `yaml.load()` and `yaml.unsafe_load()` do not appear anywhere in `training/scripts/`
- [ ] 14.13 `shell=True` does not appear anywhere in `training/scripts/`
- [ ] 14.14 `model_name` regex validation is present in every script that constructs a path from config
