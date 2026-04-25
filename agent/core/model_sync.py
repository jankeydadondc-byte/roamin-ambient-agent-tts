"""
model_sync.py — Discovers GGUF models from the local filesystem and idempotently
appends net-new entries to model_config.json at startup. No external servers required.
"""

import json
import logging
import os
import re
import string
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "model_config.json"
logger = logging.getLogger(__name__)

# Ordered list of (substring, capabilities) heuristic rules.
# Applied in order; all matching rules are merged. Case-insensitive.
CAPABILITY_HEURISTICS: list[tuple[str, list[str]]] = [
    ("deepseek-r1", ["reasoning", "deep_thinking", "analysis"]),
    ("r1", ["reasoning", "deep_thinking", "analysis"]),
    ("coder", ["code", "json_output"]),
    ("-vl-", ["vision", "screen_reading"]),
    ("vision", ["vision", "screen_reading"]),
    ("reasoning", ["reasoning", "deep_thinking"]),
    ("instruct", ["fast", "general", "chat"]),
]

_DEFAULT_CAPABILITIES = ["fast", "general", "chat"]

# Well-known model dirs always scanned unconditionally
_WELL_KNOWN_SCAN_DIRS: list[Path] = [
    p
    for p in [
        Path.home() / ".lmstudio" / "models",
        Path("C:/AI"),
    ]
    if p.exists()
]

# Directory names (lowercase) to never descend into during drive walk
_SCAN_DIR_SKIP: frozenset[str] = frozenset(
    {
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "$recycle.bin",
        "system volume information",
        "recovery",
        "node_modules",
        ".git",
        "__pycache__",
        "site-packages",
    }
)

# Directory names (any path component, case-insensitive) that must never be
# recurse-scanned — prevents rglob from entering the project itself, forbidden
# sub-projects, and virtualenvs (#19).
_RGLOB_EXCLUSIONS: frozenset[str] = frozenset(
    {
        "roamin-ambient-agent-tts",
        ".venv",
        "n.e.k.o.",
        "framework",
        "node_modules",
        "__pycache__",
        ".git",
        "site-packages",
    }
)

# Timeout in seconds for scanning a single drive during _drive_walk() (#20)
_DRIVE_SCAN_TIMEOUT: float = 3.0


# ---------------------------------------------------------------------------
# Capability inference
# ---------------------------------------------------------------------------


def _infer_capabilities(model_id: str) -> list[str]:
    """Infer capabilities from model name using heuristic substring rules."""
    name = model_id.lower()
    merged: list[str] = []
    for substring, caps in CAPABILITY_HEURISTICS:
        if substring in name:
            for cap in caps:
                if cap not in merged:
                    merged.append(cap)
    return merged if merged else list(_DEFAULT_CAPABILITIES)


def _slugify(model_id: str) -> str:
    """Convert model_id to a URL/dict-safe slug."""
    slug = model_id.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _build_entry(
    model_id: str,
    file_path: str | None = None,
    mmproj_path: str | None = None,
) -> dict:
    """Build a new model config entry dict for a discovered model."""
    entry: dict = {
        "id": _slugify(model_id),
        "name": model_id,
        "provider": "llama_cpp",
        "model_id": model_id,
        "endpoint": "local://llama_cpp",
        "capabilities": _infer_capabilities(model_id),
        "context_window": 32768,
        "always_available": False,
    }
    if file_path is not None:
        entry["file_path"] = file_path
    if mmproj_path is not None:
        entry["mmproj_path"] = mmproj_path
    return entry


# ---------------------------------------------------------------------------
# Ollama manifest resolver
# ---------------------------------------------------------------------------


def _build_ollama_manifest_map() -> dict[str, str]:
    """Parse ~/.ollama/models/manifests/ and return {sha256_hex: 'name:tag'}."""
    manifests_dir = Path.home() / ".ollama" / "models" / "manifests"
    if not manifests_dir.exists():
        return {}

    result: dict[str, str] = {}
    for manifest_file in manifests_dir.rglob("*"):
        if not manifest_file.is_file():
            continue
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("model_sync: skipping malformed manifest: %s", manifest_file)
            continue
        # Derive name:tag from path: .../library/<name>/<tag>
        parts = manifest_file.parts
        try:
            lib_idx = next(i for i, p in enumerate(parts) if p == "library")
            name = parts[lib_idx + 1]
            tag = parts[lib_idx + 2]
            name_tag = f"{name}:{tag}"
        except (StopIteration, IndexError):
            continue
        for layer in data.get("layers", []):
            if layer.get("mediaType") == "application/vnd.ollama.image.model":
                digest = layer.get("digest", "")
                if digest.startswith("sha256:"):
                    hex_val = digest[len("sha256:") :]
                    result[hex_val] = name_tag
    return result


def _discover_ollama_blobs() -> list[dict]:
    """Resolve Ollama blob files to friendly names via manifest map."""
    blobs_dir = Path.home() / ".ollama" / "models" / "blobs"
    if not blobs_dir.exists():
        return []

    manifest_map = _build_ollama_manifest_map()
    records: list[dict] = []
    for blob in blobs_dir.iterdir():
        if not blob.is_file():
            continue
        name = blob.name  # e.g. sha256-abc123...
        if not name.startswith("sha256-"):
            continue
        hex_val = name[len("sha256-") :]
        friendly = manifest_map.get(hex_val)
        if friendly is None:
            continue
        records.append(
            {
                "model_id": friendly,
                "file_path": str(blob.resolve()),
                "provider": "llama_cpp",
                "mmproj_path": None,
            }
        )
    return records


# ---------------------------------------------------------------------------
# Filesystem scanner
# ---------------------------------------------------------------------------


def _rglob_safe(base: Path) -> list[Path]:
    """rglob '*.gguf' under *base*, skipping excluded directories (#19).

    Prevents recursing into the project itself, forbidden sub-projects, and
    virtualenvs that happen to sit inside a scan root like C:/AI.
    """
    results: list[Path] = []
    for p in base.rglob("*.gguf"):
        # Check only path components *relative to base* so that an excluded name
        # appearing in the scan root's own ancestors (e.g. "roamin-ambient-agent-tts"
        # in .pytest_tmp paths) doesn't incorrectly filter the file.
        try:
            rel_parts = p.relative_to(base).parts
        except ValueError:
            rel_parts = p.parts
        if any(part.lower() in _RGLOB_EXCLUSIONS for part in rel_parts):
            continue
        results.append(p)
    return results


def _scan_dir_for_ggufs(directory: Path) -> list[Path]:
    """Return all .gguf files in directory (non-recursive), skipping mmproj files."""
    results: list[Path] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(".gguf"):
                    if "mmproj" not in entry.name.lower():
                        results.append(Path(entry.path).resolve())
    except OSError:
        pass
    return results


def _find_mmproj(gguf_path: Path) -> Path | None:
    """Return the first sibling *mmproj* file in the same directory, or None."""
    parent = gguf_path.parent
    matches = list(parent.glob("*mmproj*")) + list(parent.glob("*MMPROJ*"))
    # Case-insensitive: also try lower
    for f in parent.iterdir():
        if "mmproj" in f.name.lower() and f not in matches:
            matches.append(f)
    for m in matches:
        if m.is_file() and m != gguf_path:
            return m.resolve()
    return None


def _drive_walk(extra_dirs: list[Path], max_depth: int = 5) -> list[Path]:
    """Walk all Windows drives looking for dirs named 'models', collect GGUFs."""
    seen: set[Path] = set()
    results: list[Path] = []

    def _recurse(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    name_lower = entry.name.lower()
                    if name_lower in _SCAN_DIR_SKIP:
                        continue
                    child = Path(entry.path)
                    if name_lower == "models":
                        for p in _scan_dir_for_ggufs(child):
                            if p not in seen:
                                seen.add(p)
                                results.append(p)
                    _recurse(child, depth + 1)
        except OSError:
            pass

    drives = [Path(f"{letter}:/") for letter in string.ascii_uppercase if Path(f"{letter}:/").exists()]

    # Scan each drive with a per-drive timeout — prevents blocking on network
    # drives or removable media that hang at startup (#20)
    def _scan_drive(drive: Path) -> list[Path]:
        _recurse(drive, 0)
        return results  # shared list — caller collects after all futures complete

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_recurse, drive, 0): drive for drive in drives}
        for fut, drive in futures.items():
            try:
                fut.result(timeout=_DRIVE_SCAN_TIMEOUT)
            except FuturesTimeout:
                logger.debug("[model_sync] Drive %s: scan timeout, skipped", drive)
            except Exception as exc:
                logger.debug("[model_sync] Drive %s: scan error: %s", drive, exc)

    return results


def _discover_filesystem(config: dict) -> list[dict]:
    """Scan the filesystem for GGUF models and return discovery records."""
    extra_dirs = [Path(p) for p in config.get("model_scan_dirs", []) if Path(p).exists()]

    seen_paths: set[Path] = set()
    raw_paths: list[Path] = []

    # Well-known dirs + user-configured dirs — use _rglob_safe to skip forbidden dirs (#19)
    for scan_root in _WELL_KNOWN_SCAN_DIRS + extra_dirs:
        for p in _rglob_safe(scan_root):
            if "mmproj" in p.name.lower():
                continue
            resolved = p.resolve()
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                raw_paths.append(resolved)

    # Drive walk (depth-limited, only into 'models' dirs)
    for p in _drive_walk(extra_dirs):
        if p not in seen_paths:
            seen_paths.add(p)
            raw_paths.append(p)

    records: list[dict] = []
    for p in raw_paths:
        mmproj = _find_mmproj(p)
        records.append(
            {
                "model_id": p.stem,
                "file_path": str(p),
                "provider": "llama_cpp",
                "mmproj_path": str(mmproj) if mmproj else None,
            }
        )

    # Merge Ollama blob records
    records.extend(_discover_ollama_blobs())
    return records


# ---------------------------------------------------------------------------
# Sync entry point
# ---------------------------------------------------------------------------


def sync_from_providers(config_path: Path | None = None) -> int:
    """Discover models from the filesystem and append net-new entries to config.

    Returns the number of new entries added.
    """
    path = config_path or _CONFIG_PATH
    config = json.loads(path.read_text(encoding="utf-8"))
    models: list[dict] = config["models"]

    # Build dedup sets — check both model_id and file_path
    existing_model_ids: set[str] = {m["model_id"].strip().lower() for m in models}
    existing_file_paths: set[str] = {m["file_path"].lower() for m in models if m.get("file_path")}

    discovered = _discover_filesystem(config)
    new_entries: list[dict] = []

    for rec in discovered:
        mid = rec["model_id"].strip().lower()
        fp = rec.get("file_path", "").lower()

        if mid in existing_model_ids or (fp and fp in existing_file_paths):
            continue

        entry = _build_entry(
            model_id=rec["model_id"],
            file_path=rec.get("file_path"),
            mmproj_path=rec.get("mmproj_path"),
        )
        new_entries.append(entry)
        existing_model_ids.add(mid)
        if fp:
            existing_file_paths.add(fp)

    if not new_entries:
        return 0

    config["models"].extend(new_entries)

    # Atomic write via temp file + os.replace()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)

    return len(new_entries)
