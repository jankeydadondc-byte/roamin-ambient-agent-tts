# Roamin Wake-Word Training

Custom OpenWakeWord ONNX models for the Roamin ambient agent.

## Models

| Model | Phrases | Output |
|---|---|---|
| `hey_roamin` | "hey roamin", "hey roaming", "hey rome in" | `models/wake_word/hey_roamin.onnx` |
| `stop_roamin` | "stop roamin", "roamin stop", "shutup", "hey shutup", "roamin shutup", "be quiet", "silence" | `models/wake_word/stop_roamin.onnx` |

## Requirements

- WSL2 (Ubuntu 24.04) with NVIDIA GPU passthrough (RTX 3090 recommended)
- NVIDIA driver ≥ 550, CUDA 13.x
- ~40 GB free disk space
- Internet access for data downloads

See `docs/WAKE_WORD_TRAINING.md` for full setup and training instructions.

## Quick Start

```bash
# 1. Set up training environment (run once)
bash training/setup/wsl_bootstrap.sh

# 2. Download piper TTS voice (run once)
bash training/setup/piper_bootstrap.sh

# 3. Download training data (run once, ~10 GB)
bash training/setup/data_bootstrap.sh

# 4. Train hey_roamin (inside tmux session)
tmux new -s train_hey
python training/scripts/generate_samples.py --config training/configs/hey_roamin.yaml
python training/scripts/augment_samples.py  --config training/configs/hey_roamin.yaml
python training/scripts/train_model.py      --config training/configs/hey_roamin.yaml

# 5. Verify and deploy
python training/scripts/verify_model.py  --onnx training/out/hey_roamin.onnx
python training/scripts/compare_models.py \
    --new training/out/hey_roamin.onnx \
    --existing models/wake_word/hey_roamin.onnx \
    --deploy
```

## Directory Structure

```
training/
  configs/          YAML training configs (one per model)
  data/             Downloaded external data (gitignored)
    background/     FMA small background audio (WAV, 16kHz)
    rir/            MIT IR Survey room impulse responses
    piper_models/   piper-sample-generator .pt model
  out/              Generated WAVs, feature NPYs, trained ONNX (gitignored)
  scripts/          Python wrapper scripts for each training stage
  setup/            Bootstrap shell scripts
  venv/             Isolated Python 3.12 training venv (gitignored)
  requirements-training.txt
```
