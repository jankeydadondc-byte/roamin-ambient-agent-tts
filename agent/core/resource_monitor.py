"""Resource monitor — CPU/RAM/VRAM usage and throttle decision logic."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

_CPU_THRESHOLD = 90.0
_RAM_THRESHOLD_MB = 16_000
_VRAM_THRESHOLD_MB = 20_000


def get_cpu_percent(interval: float = 0.5) -> float:
    """Return current CPU usage percentage (0–100)."""
    try:
        import psutil

        return psutil.cpu_percent(interval=interval)
    except Exception as exc:
        logger.debug("get_cpu_percent failed: %s", exc)
        return 0.0


def get_ram_usage_mb() -> int:
    """Return current RAM usage in MB."""
    try:
        import psutil

        return int(psutil.virtual_memory().used / (1024 * 1024))
    except Exception as exc:
        logger.debug("get_ram_usage_mb failed: %s", exc)
        return 0


def get_vram_usage_mb() -> int | None:
    """Return VRAM usage in MB via nvidia-smi, or None if unavailable."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return int(result.stdout.strip().splitlines()[0])
    except Exception as exc:
        logger.debug("get_vram_usage_mb failed: %s", exc)
    return None


def is_resource_exhausted(
    threshold_cpu: float = _CPU_THRESHOLD,
    threshold_ram_mb: int = _RAM_THRESHOLD_MB,
    threshold_vram_mb: int | None = _VRAM_THRESHOLD_MB,
) -> bool:
    """Return True if any monitored resource exceeds its threshold.

    Args:
        threshold_cpu: CPU % ceiling (default 90%).
        threshold_ram_mb: RAM ceiling in MB (default 16 GB).
        threshold_vram_mb: VRAM ceiling in MB (default 20 GB); None skips VRAM check.
    """
    if get_cpu_percent() > threshold_cpu:
        logger.debug("Resource exhausted: CPU > %.0f%%", threshold_cpu)
        return True

    if get_ram_usage_mb() > threshold_ram_mb:
        logger.debug("Resource exhausted: RAM > %d MB", threshold_ram_mb)
        return True

    if threshold_vram_mb is not None:
        vram = get_vram_usage_mb()
        if vram is not None and vram > threshold_vram_mb:
            logger.debug("Resource exhausted: VRAM > %d MB", threshold_vram_mb)
            return True

    return False


def get_throttle_status() -> dict:
    """Return current resource snapshot for the /health endpoint."""
    return {
        "cpu_percent": round(get_cpu_percent(interval=0.5), 2),
        "ram_mb": get_ram_usage_mb(),
        "vram_mb": get_vram_usage_mb(),
        "throttled": is_resource_exhausted(),
    }
