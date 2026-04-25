"""
setup_local_dev.py — Local Dev Tool Configurator

Scans LM Studio's model folder and GPU to generate accurate configs for
Cline (via display), Continue (~/.continue/config.json), and Aider
(~/.aider.conf.yml). Run this whenever you add or remove models.

Usage:
    python tools/setup_local_dev.py
    python tools/setup_local_dev.py --dry-run
"""

import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LMSTUDIO_MODELS_DIR = Path.home() / ".lmstudio" / "models"
LMSTUDIO_API = "http://127.0.0.1:1234/v1"
CONTINUE_CONFIG = Path.home() / ".continue" / "config.json"
AIDER_CONFIG = Path.home() / ".aider.conf.yml"

# VRAM overhead factor: GGUF file size * this = estimated VRAM needed
VRAM_OVERHEAD = 1.08

# Models to exclude from dev tool configs (embedding, vision-only, uncensored variants)
EXCLUDE_PATTERNS = [
    r"embed",
    r"nomic",
    r"mmproj",
    r"abliterated",
]

# Capability hints from model name — used to pick Aider default
REASONING_HINTS = ["qwopus", "reasoning", "distill", "r1", "deepseek"]
CODER_HINTS = ["coder"]


# ---------------------------------------------------------------------------
# GPU discovery
# ---------------------------------------------------------------------------


def get_gpu_info():
    """Query nvidia-smi for GPU name and VRAM (MB). Returns None if unavailable."""
    try:
        out = (
            subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                text=True,
                timeout=5,
            )
            .strip()
            .splitlines()[0]
        )
        name, total, free = [x.strip() for x in out.split(",")]
        return {"name": name, "total_mb": int(total), "free_mb": int(free)}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------


def scan_gguf_files(models_dir: Path):
    """
    Walk the LM Studio models directory and collect GGUF files with their sizes.
    Skips mmproj (multimodal projection) and excluded pattern files.
    Returns list of dicts: {path, name, family, file_size_mb, vram_estimate_mb}
    """
    results = []
    if not models_dir.exists():
        return results

    for gguf in models_dir.rglob("*.gguf"):
        fname = gguf.name.lower()

        # Skip excluded patterns
        if any(re.search(p, fname) for p in EXCLUDE_PATTERNS):
            continue

        size_mb = gguf.stat().st_size // (1024 * 1024)
        vram_mb = int(size_mb * VRAM_OVERHEAD)

        # Derive a clean model name from the parent folder
        # LM Studio stores as: publisher/ModelName-GGUF/file.gguf
        parts = gguf.parts
        try:
            # Find the .lmstudio/models index and take publisher/model
            idx = next(i for i, p in enumerate(parts) if p == "models")
            publisher = parts[idx + 1] if idx + 1 < len(parts) else ""
            model_folder = parts[idx + 2] if idx + 2 < len(parts) else gguf.stem
        except StopIteration:
            publisher = ""
            model_folder = gguf.parent.name

        results.append(
            {
                "path": gguf,
                "publisher": publisher,
                "folder": model_folder,
                "filename": gguf.name,
                "file_size_mb": size_mb,
                "vram_estimate_mb": vram_mb,
            }
        )

    return results


def get_lmstudio_api_ids():
    """
    Query LM Studio's /v1/models endpoint for the exact model IDs it serves.
    Returns a dict of {id: model_object} or empty dict if LM Studio is offline.
    """
    try:
        req = urllib.request.urlopen(f"{LMSTUDIO_API}/models", timeout=5)
        data = json.load(req)
        return {m["id"]: m for m in data.get("data", [])}
    except Exception:
        return {}


def match_gguf_to_api_id(gguf_info, api_ids):
    """
    Try to match a scanned GGUF file to an LM Studio API model ID.
    Strips publisher prefixes (qwen/, mistralai/), -gguf suffixes, and
    quantization suffixes before comparing.
    Returns the matched API ID or None.
    """
    # Clean folder: strip -gguf suffix, quantization, underscores
    folder_lower = re.sub(r"-gguf$", "", gguf_info["folder"].lower()).replace("_", "-")
    folder_clean = re.sub(r"-q\d[a-z0-9_]*$", "", folder_lower)

    filename_lower = gguf_info["filename"].lower().replace(".gguf", "").replace("_", "-")

    for api_id in api_ids:
        api_short = api_id.split("/")[-1].lower().replace("_", "-")
        api_full = api_id.lower().replace("/", "-").replace("_", "-")

        # Never match a GGUF to an excluded API ID (e.g. base model matched to uncensored variant)
        if any(re.search(p, api_short) for p in EXCLUDE_PATTERNS):
            continue

        # Forward: api_id (short or full) is substring of folder/filename
        for api_form in [api_short, api_full]:
            if api_form in folder_lower or api_form in filename_lower:
                return api_id

        # Reverse: cleaned folder/filename tokens overlap with api_id tokens
        # Use token overlap rather than substring to avoid partial matches
        # (e.g. "qwen3.5-9b" wrongly matching "qwen3.5-9b-uncensored-...")
        folder_tokens = set(re.split(r"[-.]", folder_clean))
        api_tokens = set(re.split(r"[-.]", api_short))
        overlap = folder_tokens & api_tokens
        # Require overlap covers >60% of folder tokens AND api_short contains folder_clean
        if overlap and len(overlap) / max(len(folder_tokens), 1) > 0.6:
            if folder_clean in api_short or api_short in folder_clean:
                return api_id

    return None


def build_model_list(models_dir, api_ids):
    """
    Combine filesystem scan with LM Studio API IDs.
    Returns a deduplicated list of model dicts with verified API IDs.
    """
    ggufs = scan_gguf_files(models_dir)
    seen_ids = set()
    models = []

    for g in sorted(ggufs, key=lambda x: x["vram_estimate_mb"], reverse=True):
        api_id = match_gguf_to_api_id(g, api_ids)

        # If no match from filesystem, fall back to API-only IDs
        if api_id is None:
            continue

        if api_id in seen_ids:
            continue
        seen_ids.add(api_id)

        # Determine role hints from name
        name_lower = api_id.lower()
        is_reasoning = any(h in name_lower for h in REASONING_HINTS)
        is_coder = any(h in name_lower for h in CODER_HINTS)

        role = "Coder" if is_coder else ("Reasoning" if is_reasoning else "Chat")
        title = _make_title(api_id, role, g["vram_estimate_mb"])

        models.append(
            {
                "api_id": api_id,
                "title": title,
                "vram_mb": g["vram_estimate_mb"],
                "file_size_mb": g["file_size_mb"],
                "is_reasoning": is_reasoning,
                "is_coder": is_coder,
                "role": role,
            }
        )

    # Also add any API IDs that had no filesystem match (loaded but file not in default dir)
    for api_id in api_ids:
        if api_id in seen_ids:
            continue
        name_lower = api_id.lower()
        # Apply same exclusion filter as filesystem scan
        if any(re.search(p, name_lower) for p in EXCLUDE_PATTERNS):
            continue
        # Also check the short name (after publisher prefix)
        short_lower = api_id.split("/")[-1].lower()
        if any(re.search(p, short_lower) for p in EXCLUDE_PATTERNS):
            continue
        is_reasoning = any(h in name_lower for h in REASONING_HINTS)
        is_coder = any(h in name_lower for h in CODER_HINTS)
        role = "Coder" if is_coder else ("Reasoning" if is_reasoning else "Chat")
        models.append(
            {
                "api_id": api_id,
                "title": _make_title(api_id, role, None),
                "vram_mb": None,
                "file_size_mb": None,
                "is_reasoning": is_reasoning,
                "is_coder": is_coder,
                "role": role,
            }
        )
        seen_ids.add(api_id)

    return models


def _make_title(api_id, role, vram_mb):
    """Generate a human-readable title from an API ID."""
    # Strip publisher prefix for display
    short = api_id.split("/")[-1] if "/" in api_id else api_id
    vram_str = f" (~{vram_mb // 1024}GB)" if vram_mb else ""
    return f"{short} [{role}]{vram_str}"


# ---------------------------------------------------------------------------
# Intelligent model selection
# ---------------------------------------------------------------------------


def pick_aider_default(models, gpu_info):
    """
    Pick the best default model for Aider:
    1. Prefer reasoning models
    2. Must fit in available VRAM (with 2GB headroom)
    3. Fall back to largest model that fits
    Returns the api_id string.
    """
    headroom_mb = 2048
    vram_budget = (gpu_info["total_mb"] - headroom_mb) if gpu_info else float("inf")

    candidates = [m for m in models if m["vram_mb"] is None or m["vram_mb"] <= vram_budget]

    # Prefer reasoning, then coder, then general
    for priority in ["is_reasoning", "is_coder"]:
        subset = [m for m in candidates if m[priority]]
        if subset:
            return subset[0]["api_id"]

    return candidates[0]["api_id"] if candidates else None


def pick_autocomplete_model(models):
    """
    Pick the best autocomplete model: prefer coder models.
    Falls back to smallest reasoning/chat model for speed.
    """
    coders = [m for m in models if m["is_coder"]]
    if coders:
        return coders[0]["api_id"]
    # Fall back to smallest available (sorted by vram_mb ascending)
    sized = [m for m in models if m["vram_mb"] is not None]
    if sized:
        return sorted(sized, key=lambda x: x["vram_mb"])[0]["api_id"]
    return models[0]["api_id"] if models else None


def apply_vram_loading_strategy(models, gpu_info):
    """
    Given GPU total VRAM, determine which models can be co-loaded.
    Returns a human-readable strategy string.
    """
    if not gpu_info:
        return "GPU info unavailable — load models one at a time."

    total = gpu_info["total_mb"]
    headroom = 2048

    lines = [f"GPU: {gpu_info['name']} - {total // 1024} GB total VRAM"]
    lines.append(f"Safe budget (with {headroom // 1024}GB headroom): {(total - headroom) // 1024} GB")
    lines.append("")

    # Check which pairs can co-exist
    sized = [m for m in models if m["vram_mb"] is not None]
    if not sized:
        lines.append("No VRAM estimates available.")
        return "\n".join(lines)

    lines.append("Single-model fits:")
    for m in sized:
        fits = m["vram_mb"] <= (total - headroom)
        lines.append(f"  {'YES' if fits else 'NO '} {m['title']} ({m['vram_mb'] // 1024}GB)")

    lines.append("")
    lines.append("Co-load pairs (both fit simultaneously):")
    for i, a in enumerate(sized):
        for b in sized[i + 1 :]:
            combined = (a["vram_mb"] or 0) + (b["vram_mb"] or 0)
            fits = combined <= (total - headroom)
            lines.append(
                f"  {'YES' if fits else 'NO '} {a['api_id'].split('/')[-1]} + "
                f"{b['api_id'].split('/')[-1]} = {combined // 1024}GB"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Config writers
# ---------------------------------------------------------------------------


def build_continue_config(models):
    """Generate ~/.continue/config.json content."""
    autocomplete_id = pick_autocomplete_model(models)
    autocomplete_model = next((m for m in models if m["api_id"] == autocomplete_id), models[0])

    return {
        "models": [
            {
                "title": m["title"],
                "provider": "openai",
                "model": m["api_id"],
                "apiBase": f"{LMSTUDIO_API}",
                "apiKey": "not-needed",
            }
            for m in models
        ],
        "tabAutocompleteModel": {
            "title": autocomplete_model["title"],
            "provider": "openai",
            "model": autocomplete_model["api_id"],
            "apiBase": f"{LMSTUDIO_API}",
            "apiKey": "not-needed",
        },
    }


def build_aider_config(aider_default_id):
    """Generate ~/.aider.conf.yml content."""
    return (
        f"model: openai/{aider_default_id}\n"
        f"openai-api-base: {LMSTUDIO_API}\n"
        f"openai-api-key: not-needed\n"
        f"no-auto-commits: true\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Configure local dev tools from LM Studio.")
    parser.add_argument("--dry-run", action="store_true", help="Print configs without writing files.")
    args = parser.parse_args()

    print("=" * 60)
    print("Local Dev Tool Configurator")
    print("=" * 60)

    # GPU
    gpu = get_gpu_info()
    if gpu:
        print(f"\nGPU: {gpu['name']}")
        print(f"     Total VRAM : {gpu['total_mb']:,} MB ({gpu['total_mb'] // 1024} GB)")
        print(f"     Free  VRAM : {gpu['free_mb']:,} MB ({gpu['free_mb'] // 1024} GB)")
    else:
        print("\nGPU: not detected (nvidia-smi unavailable)")

    # LM Studio API
    print(f"\nQuerying LM Studio at {LMSTUDIO_API}...")
    api_ids = get_lmstudio_api_ids()
    if api_ids:
        print(f"  {len(api_ids)} model(s) available via API")
    else:
        print("  LM Studio not responding — using filesystem scan only")

    # Filesystem scan
    print(f"\nScanning {LMSTUDIO_MODELS_DIR}...")
    models = build_model_list(LMSTUDIO_MODELS_DIR, api_ids)
    print(f"  {len(models)} usable model(s) found\n")

    if not models:
        print("No models found. Make sure LM Studio has models downloaded.")
        return

    # Model summary
    print("Models discovered:")
    for m in models:
        vram = f"{m['vram_mb'] // 1024}GB" if m["vram_mb"] else "?"
        print(f"  [{m['role']:<9}] {m['api_id']:<50} ~{vram} VRAM")

    # VRAM strategy
    print("\n" + apply_vram_loading_strategy(models, gpu))

    # Pick defaults
    aider_default = pick_aider_default(models, gpu)
    autocomplete_default = pick_autocomplete_model(models)
    print("\nSelected defaults:")
    print(f"  Aider default      : openai/{aider_default}")
    print(f"  Autocomplete model : {autocomplete_default}")

    # Build configs
    continue_cfg = build_continue_config(models)
    aider_cfg = build_aider_config(aider_default)

    if args.dry_run:
        print("\n--- DRY RUN: ~/.continue/config.json ---")
        print(json.dumps(continue_cfg, indent=2))
        print("\n--- DRY RUN: ~/.aider.conf.yml ---")
        print(aider_cfg)
        return

    # Write configs
    CONTINUE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONTINUE_CONFIG.write_text(json.dumps(continue_cfg, indent=2))
    print(f"\nWrote: {CONTINUE_CONFIG}")

    AIDER_CONFIG.write_text(aider_cfg)
    print(f"Wrote: {AIDER_CONFIG}")

    print("\nDone. Re-run this script any time you add or remove models from LM Studio.")


if __name__ == "__main__":
    main()
