"""system_specs.py — Hardware detection and model memory estimation for Roamin.

Provides:
  get_system_specs()     → CPU/RAM/GPU info dict
  estimate_model_memory() → VRAM/RAM estimate with guardrail verdict
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── GPU detection ────────────────────────────────────────────────────────────

_nvml_ok = False


def _init_nvml() -> bool:
    global _nvml_ok
    if _nvml_ok:
        return True
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        _nvml_ok = True
        return True
    except Exception:
        return False


def get_system_specs() -> dict[str, Any]:
    """Return a snapshot of CPU, RAM, and GPU specs.

    Returns:
        {
            cpu_cores_physical: int,
            cpu_cores_logical:  int,
            ram_total_gb:       float,
            ram_available_gb:   float,
            gpus: [
                {name, vram_total_gb, vram_free_gb, cuda_device_id}
            ]
        }
    """
    import psutil

    cpu_phys = psutil.cpu_count(logical=False) or 1
    cpu_logi = psutil.cpu_count(logical=True) or cpu_phys
    vm = psutil.virtual_memory()
    ram_total = round(vm.total / 1e9, 2)
    ram_avail = round(vm.available / 1e9, 2)

    gpus: list[dict[str, Any]] = []
    if _init_nvml():
        try:
            import pynvml  # type: ignore

            count = pynvml.nvmlDeviceGetCount()
            for i in range(count):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                gpus.append(
                    {
                        "name": name,
                        "vram_total_gb": round(mem.total / 1e9, 2),
                        "vram_free_gb": round(mem.free / 1e9, 2),
                        "cuda_device_id": i,
                    }
                )
        except Exception as e:
            logger.debug("[system_specs] NVML query failed: %s", e)

    return {
        "cpu_cores_physical": cpu_phys,
        "cpu_cores_logical": cpu_logi,
        "ram_total_gb": ram_total,
        "ram_available_gb": ram_avail,
        "gpus": gpus,
    }


# ─── GGUF metadata parsing ────────────────────────────────────────────────────
# We parse just the key-value section for the architecture fields we need.
# GGUF v3 format: magic(4) + version(4) + n_tensors(8) + n_kv(8) + kv pairs

_GGUF_MAGIC = b"GGUF"

# GGUF value types
_GGUFType = {
    0: ("B", 1),  # UINT8
    1: ("b", 1),  # INT8
    2: ("H", 2),  # UINT16
    3: ("h", 2),  # INT16
    4: ("I", 4),  # UINT32
    5: ("i", 4),  # INT32
    6: ("f", 4),  # FLOAT32
    7: ("?", 1),  # BOOL
    # 8 = STRING (special)
    # 9 = ARRAY  (special)
    10: ("Q", 8),  # UINT64
    11: ("q", 8),  # INT64
    12: ("d", 8),  # FLOAT64
}

_KEYS_WANTED = {
    "llm.block_count",
    "llm.embedding_length",
    "llm.attention.head_count",
    "llm.attention.head_count_kv",
    "general.architecture",
}


def _parse_gguf_meta(path: Path) -> dict[str, Any]:
    """Read GGUF header key-value pairs and return the subset we care about.

    Falls back gracefully on any parse error.
    """
    meta: dict[str, Any] = {}
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != _GGUF_MAGIC:
                return meta

            (version,) = struct.unpack("<I", f.read(4))
            (n_tensors,) = struct.unpack("<Q", f.read(8))
            (n_kv,) = struct.unpack("<Q", f.read(8))

            for _ in range(n_kv):
                # Read key
                (klen,) = struct.unpack("<Q", f.read(8))
                key = f.read(klen).decode("utf-8", errors="replace")

                # Read value type
                (vtype,) = struct.unpack("<I", f.read(4))

                if vtype == 8:  # STRING
                    (slen,) = struct.unpack("<Q", f.read(8))
                    val = f.read(slen).decode("utf-8", errors="replace")
                elif vtype == 9:  # ARRAY
                    (atype,) = struct.unpack("<I", f.read(4))
                    (alen,) = struct.unpack("<Q", f.read(8))
                    # Skip array contents
                    if atype in _GGUFType:
                        fmt, sz = _GGUFType[atype]
                        f.read(sz * alen)
                    else:
                        break  # unknown array element type, bail
                    val = None
                elif vtype in _GGUFType:
                    fmt, sz = _GGUFType[vtype]
                    (val,) = struct.unpack(f"<{fmt}", f.read(sz))
                else:
                    break  # unknown type, stop parsing

                if key in _KEYS_WANTED:
                    meta[key] = val

                # Short-circuit once we have everything
                if len(meta) == len(_KEYS_WANTED):
                    break

    except Exception as e:
        logger.debug("[system_specs] GGUF parse failed for %s: %s", path, e)

    return meta


# ─── Memory estimation ────────────────────────────────────────────────────────

_KV_DTYPE_BYTES = {
    "f32": 4,
    "f16": 2,
    "bf16": 2,
    "q8_0": 1,
    "q4_0": 0.5,
    "q4_1": 0.5,
    "iq4_nl": 0.5,
    "q5_0": 0.625,
    "q5_1": 0.625,
}

_GUARDRAIL_THRESHOLDS = {
    "off": {"warn": 9.9, "block": 9.9},
    "relaxed": {"warn": 1.05, "block": 9.9},  # warn >105% of VRAM, never block
    "balanced": {"warn": 0.90, "block": 9.9},  # warn >90% VRAM
    "strict": {"warn": 0.85, "block": 0.90},  # warn >85%, block >90%
}


def estimate_model_memory(
    gguf_path: str,
    n_ctx: int = 8192,
    n_gpu_layers: int = -1,  # -1 = auto (all layers)
    flash_attn: bool = True,
    type_k: str = "f16",
    type_v: str = "f16",
    guardrail_tier: str = "balanced",
) -> dict[str, Any]:
    """Estimate VRAM + RAM required to load a GGUF model with the given settings.

    Returns:
        {
            weight_gb:           float,  # model weight memory
            kv_cache_gb:         float,  # KV cache
            overhead_gb:         float,  # CUDA runtime + misc
            total_vram_gb:       float,  # estimated VRAM usage
            total_ram_gb:        float,  # estimated RAM usage (CPU-side)
            vram_available_gb:   float,
            ram_available_gb:    float,
            fits_in_vram:        bool,
            guardrail_verdict:   "ok" | "warn" | "block",
            reason:              str,
            meta:                dict,   # raw GGUF fields for UI display
        }
    """
    path = Path(gguf_path)
    specs = get_system_specs()
    vram_total = specs["gpus"][0]["vram_total_gb"] if specs["gpus"] else 0.0
    vram_free = specs["gpus"][0]["vram_free_gb"] if specs["gpus"] else 0.0
    ram_avail = specs["ram_available_gb"]

    # ── Weight memory ──
    file_size_gb = path.stat().st_size / 1e9 if path.exists() else 0.0
    # Q-quantised models: on-disk size ≈ in-memory weight footprint
    weight_gb = file_size_gb

    # ── GGUF metadata for KV calc ──
    meta = _parse_gguf_meta(path) if path.exists() else {}
    n_layers = int(meta.get("llm.block_count", 32))
    embedding = int(meta.get("llm.embedding_length", 4096))
    n_heads = int(meta.get("llm.attention.head_count", 32))
    n_kv_heads = int(meta.get("llm.attention.head_count_kv", n_heads))
    head_dim = embedding // n_heads if n_heads else 128

    # ── KV cache ──
    kv_dtype_bytes = _KV_DTYPE_BYTES.get(type_k, 2)  # use K-cache dtype
    # KV cache bytes = 2 (K+V) × n_ctx × n_layers × n_kv_heads × head_dim × dtype_bytes
    kv_bytes = 2 * n_ctx * n_layers * n_kv_heads * head_dim * kv_dtype_bytes
    kv_cache_gb = kv_bytes / 1e9
    # Flash attention reduces KV cache memory usage by ~4x
    if flash_attn:
        kv_cache_gb *= 0.25

    # ── GPU offload fraction ──
    if n_gpu_layers < 0 or n_gpu_layers >= n_layers:
        offload_frac = 1.0
    else:
        offload_frac = n_gpu_layers / max(n_layers, 1)

    # ── CUDA overhead ──
    overhead_gb = 0.5  # typical CUDA runtime + driver overhead

    # ── Split memory ──
    vram_weights = weight_gb * offload_frac
    ram_weights = weight_gb * (1.0 - offload_frac)
    # KV cache goes to VRAM when offload_kv=True (assumed default)
    vram_kv = kv_cache_gb * offload_frac
    ram_kv = kv_cache_gb * (1.0 - offload_frac)

    total_vram = round(vram_weights + vram_kv + overhead_gb, 2)
    total_ram = round(ram_weights + ram_kv, 2)

    # ── Guardrail verdict ──
    fits = total_vram <= vram_total
    tier = guardrail_tier.lower() if guardrail_tier.lower() in _GUARDRAIL_THRESHOLDS else "balanced"
    thresholds = _GUARDRAIL_THRESHOLDS[tier]

    verdict = "ok"
    reason = f"Estimated {total_vram:.1f} GB VRAM / {vram_total:.1f} GB available"

    if vram_total > 0:
        ratio = total_vram / vram_total
        if ratio > thresholds["block"]:
            verdict = "block"
            reason = (
                f"Would use {total_vram:.1f} GB ({ratio*100:.0f}% of {vram_total:.1f} GB VRAM)"
                f" — blocked by {tier} guardrail"
            )
        elif ratio > thresholds["warn"]:
            verdict = "warn"
            reason = f"Will use {total_vram:.1f} GB ({ratio*100:.0f}% of {vram_total:.1f} GB VRAM)"
        else:
            reason = f"Fits in VRAM ({total_vram:.1f} / {vram_total:.1f} GB)"
    elif not fits:
        verdict = "warn"
        reason = "No GPU detected — model will run on CPU only"

    return {
        "weight_gb": round(weight_gb, 2),
        "kv_cache_gb": round(kv_cache_gb, 2),
        "overhead_gb": round(overhead_gb, 2),
        "total_vram_gb": total_vram,
        "total_ram_gb": total_ram,
        "vram_total_gb": vram_total,
        "vram_free_gb": vram_free,
        "ram_available_gb": ram_avail,
        "fits_in_vram": fits,
        "guardrail_verdict": verdict,
        "reason": reason,
        "n_layers": n_layers,
        "n_kv_heads": n_kv_heads,
        "meta": meta,
    }
