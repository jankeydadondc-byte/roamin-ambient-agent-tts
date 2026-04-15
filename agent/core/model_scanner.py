"""
model_scanner.py — Discover GGUF model files on the filesystem.

Scans configured directories for .gguf files and returns structured metadata
including model name, quantization level, file size, and paired mmproj files.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default scan locations (can be overridden via settings.local.json)
_DEFAULT_SCAN_PATHS: list[str] = [
    r"C:\AI\roamin-ambient-agent-tts\models",
    os.path.expanduser(r"~\.lmstudio\models"),
]


def _parse_gguf_name(path: Path) -> dict[str, str]:
    """Extract model name and quantization from a GGUF filename."""
    stem = path.stem
    # Match common quantization suffixes: Q4_K_M, Q8_0, IQ3_XXS, etc.
    quant_match = re.search(r"[-.]([QIF]\d[A-Za-z0-9_]*?)$", stem, re.IGNORECASE)
    quant = quant_match.group(1) if quant_match else ""
    name = stem[: quant_match.start()] if quant_match else stem
    # Clean up trailing dashes/dots
    name = name.rstrip("-. ")
    return {"name": name, "quantization": quant}


def scan_models(scan_paths: list[str] | None = None) -> list[dict[str, Any]]:
    """Scan configured directories for GGUF model files.

    Args:
        scan_paths: List of directory paths to scan. Uses defaults if None.

    Returns:
        List of model dicts with id, name, file_path, mmproj_path, size_gb, quantization.
    """
    paths = scan_paths or _DEFAULT_SCAN_PATHS
    found: dict[str, dict[str, Any]] = {}  # keyed by file_path to dedup
    mmproj_files: dict[str, Path] = {}  # base_name -> mmproj path

    for scan_dir in paths:
        root = Path(scan_dir)
        if not root.exists():
            logger.debug("[model_scanner] Skipping non-existent path: %s", scan_dir)
            continue

        logger.info("[model_scanner] Scanning: %s", scan_dir)

        for gguf_path in root.rglob("*.gguf"):
            try:
                fname = gguf_path.name.lower()
                # Classify: mmproj files are projections, not standalone models
                if "mmproj" in fname:
                    # Map to base model name for pairing
                    base = re.sub(r"\.?mmproj[-._].*$", "", gguf_path.stem, flags=re.IGNORECASE)
                    mmproj_files[base.lower()] = gguf_path
                    continue

                parsed = _parse_gguf_name(gguf_path)
                size_bytes = gguf_path.stat().st_size
                size_gb = round(size_bytes / (1024**3), 2)

                model_id = gguf_path.stem  # unique per file
                found[str(gguf_path)] = {
                    "id": model_id,
                    "name": parsed["name"],
                    "file_path": str(gguf_path),
                    "mmproj_path": "",
                    "size_gb": size_gb,
                    "quantization": parsed["quantization"],
                    "provider": "llama_cpp",
                    "status": "available",
                }
            except Exception as exc:
                logger.debug("[model_scanner] Error scanning %s: %s", gguf_path, exc)

    # Pair mmproj files with their base models
    for _fpath, model in found.items():
        base_lower = re.sub(r"[-.]?[QIF]\d[A-Za-z0-9_]*$", "", model["id"], flags=re.IGNORECASE).lower()
        if base_lower in mmproj_files:
            model["mmproj_path"] = str(mmproj_files[base_lower])

    results = sorted(found.values(), key=lambda m: m["name"].lower())
    logger.info("[model_scanner] Found %d models across %d directories", len(results), len(paths))
    return results
