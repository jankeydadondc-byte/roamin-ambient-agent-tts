"""
Piper shim for OpenWakeWord compatibility.

OWW's train.py does:
    sys.path.insert(0, config["piper_sample_generator_path"])
    from generate_samples import generate_samples
    generate_samples(text=..., max_samples=..., batch_size=..., output_dir=...,
                     noise_scales=..., noise_scale_ws=..., length_scales=...,
                     auto_reduce_batch_size=True, file_names=...)

Problem: piper_sample_generator.__main__ has a module-level import of
         `piper_train.vits` (not on PyPI) which causes ImportError.

Solution: implement generate_samples here directly using the installed
          `piper` package (PiperVoice / SynthesisConfig), which IS available.
          The .onnx model path is hardcoded to the one downloaded by
          piper_bootstrap.sh (en_US-lessac-medium.onnx).
"""

import itertools as it
import logging
import os
import wave
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn.functional as F

_LOGGER = logging.getLogger(__name__)

# OWW requires 16 kHz mono audio; piper ONNX outputs 22050 Hz
_TARGET_SR = 16000

# Path to the piper ONNX voice model downloaded by piper_bootstrap.sh
_ONNX_MODEL = os.path.expanduser("~/.local/share/piper/models/en_US-lessac-medium.onnx")


def _audio_float_to_int16(audio: np.ndarray, max_wav_value: float = 32767.0) -> np.ndarray:
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    return audio_norm.astype("int16")


def generate_samples(
    text: Union[List[str], str],
    output_dir: Union[str, Path],
    max_samples: Optional[int] = None,
    batch_size: int = 1,  # ignored for ONNX; kept for API compat
    slerp_weights: Tuple[float, ...] = (0.5,),
    length_scales: Tuple[float, ...] = (0.75, 1.0, 1.25),
    noise_scales: Tuple[float, ...] = (0.667,),
    noise_scale_ws: Tuple[float, ...] = (0.8,),
    max_speakers: Optional[int] = None,
    verbose: bool = False,
    phoneme_input: bool = False,
    file_names: Optional[Iterable[str]] = None,
    auto_reduce_batch_size: bool = False,  # no-op; kept for API compat
    **kwargs,
) -> None:
    """
    Generate synthetic speech clips using the piper ONNX voice model.

    Replaces piper_sample_generator.generate_samples for OWW training.
    Uses en_US-lessac-medium.onnx (downloaded by piper_bootstrap.sh).
    """
    from piper import PiperVoice, SynthesisConfig  # type: ignore

    model_path = _ONNX_MODEL
    _LOGGER.info("Loading piper voice: %s", model_path)
    voice = PiperVoice.load(model_path, use_cuda=torch.cuda.is_available())
    _LOGGER.info(
        "Piper voice loaded (sample_rate=%s, speakers=%s)", voice.config.sample_rate, voice.config.num_speakers
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    num_speakers = voice.config.num_speakers
    if max_speakers is not None:
        num_speakers = min(num_speakers, max_speakers)

    # Build cycling iterators
    if isinstance(text, str) and os.path.isfile(text):
        texts = it.cycle([line.strip() for line in open(text, encoding="utf-8") if line.strip()])
    elif isinstance(text, list):
        texts = it.cycle(text)
    else:
        texts = it.cycle([text])

    settings_iter = it.cycle(
        it.product(
            range(num_speakers),
            length_scales,
            noise_scales,
            noise_scale_ws,
        )
    )

    if file_names is not None:
        file_names_iter = it.cycle(file_names)
    else:
        file_names_iter = None

    if max_samples is None:
        max_samples = len(text) if isinstance(text, list) else 1

    sample_idx = 0
    for speaker_id, length_scale, noise_scale, noise_w in settings_iter:
        if sample_idx >= max_samples:
            break

        text_input = next(texts)

        if file_names_iter is not None:
            wav_path = output_dir / next(file_names_iter)
        else:
            wav_path = output_dir / f"{sample_idx}.wav"

        syn_config = SynthesisConfig(
            speaker_id=speaker_id,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w_scale=noise_w,
        )

        # Synthesize to a temp buffer, resample to 16kHz, write final WAV
        import io
        import struct  # noqa: F401

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text_input, wav_file=wav_file, syn_config=syn_config)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            orig_sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        # Convert raw bytes → float32 tensor → resample → int16 bytes
        audio_int16 = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if orig_sr != _TARGET_SR:
            # Use torch interpolation for fast resampling
            t = torch.from_numpy(audio_int16).unsqueeze(0).unsqueeze(0)  # [1,1,N]
            new_len = int(len(audio_int16) * _TARGET_SR / orig_sr)
            t = F.interpolate(t, size=new_len, mode="linear", align_corners=False)
            audio_int16 = t.squeeze().numpy()
        audio_out = (np.clip(audio_int16, -1.0, 1.0) * 32767).astype(np.int16)

        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setframerate(_TARGET_SR)
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.writeframes(audio_out.tobytes())

        sample_idx += 1
        if sample_idx % 100 == 0:
            _LOGGER.info("Generated %d / %d samples", sample_idx, max_samples)

    _LOGGER.info("Done — generated %d samples in %s", sample_idx, output_dir)
