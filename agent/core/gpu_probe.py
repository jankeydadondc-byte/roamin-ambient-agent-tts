"""agent/core/gpu_probe.py

Lightweight GPU probe used at agent startup. Safe by default (no allocation).
"""

from collections.abc import Callable


def probe_gpu(log_fn: Callable[[str], None] = print, do_alloc: bool = False):
    """Return a small dict describing GPU availability.

    log_fn: callable to receive short status strings
    do_alloc: if True, perform a tiny allocation on the GPU to verify runtime (disabled by default)
    """
    try:
        import torch
    except Exception as e:
        log_fn(f"gpu_probe: torch import failed: {e}")
        return None

    try:
        info = {
            "torch": str(torch.__version__),
            "cuda_version": getattr(torch.version, "cuda", None),
            "cuda_available": torch.cuda.is_available(),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        }
        log_fn(f"gpu_probe: {info}")
        if info["cuda_available"] and do_alloc:
            # allocate a tiny tensor and run a simple op
            t = torch.zeros(1, device="cuda")
            t += 1
            info["alloc_ok"] = True
        return info
    except Exception as e:
        log_fn(f"gpu_probe: runtime error: {e}")
        return None
