"""tests/test_model_sync.py — Tests for model_sync filesystem-discovery module."""

import json
from pathlib import Path
from unittest.mock import patch

from agent.core.model_sync import (
    _build_ollama_manifest_map,
    _discover_filesystem,
    _discover_ollama_blobs,
    _infer_capabilities,
    sync_from_providers,
)


class TestInferCapabilities:
    def test_r1_name_includes_reasoning(self):
        caps = _infer_capabilities("deepseek-r1-8b")
        assert "reasoning" in caps

    def test_coder_name_includes_code(self):
        caps = _infer_capabilities("qwen3-coder-30b")
        assert "code" in caps

    def test_unknown_name_returns_default_set(self):
        caps = _infer_capabilities("some-random-model-7b")
        assert caps == ["fast", "general", "chat"]


class TestBuildOllamaManifestMap:
    def test_valid_manifest_parsed(self, tmp_path):
        lib_dir = tmp_path / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "8b"
        lib_dir.mkdir(parents=True)
        manifest = {
            "layers": [
                {
                    "mediaType": "application/vnd.ollama.image.model",
                    "digest": "sha256:abc123def456",
                }
            ]
        }
        (lib_dir / "latest").write_text(json.dumps(manifest), encoding="utf-8")

        with patch("agent.core.model_sync.Path.home", return_value=tmp_path):
            result = _build_ollama_manifest_map()

        assert result.get("abc123def456") == "qwen3:8b"

    def test_malformed_manifest_skipped(self, tmp_path):
        lib_dir = tmp_path / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "x" / "latest"
        lib_dir.mkdir(parents=True)
        (lib_dir / "latest").write_text("not json {{", encoding="utf-8")

        with patch("agent.core.model_sync.Path.home", return_value=tmp_path):
            result = _build_ollama_manifest_map()

        assert result == {}


class TestDiscoverOllamaBlobs:
    def test_blob_with_manifest_entry_returned(self, tmp_path):
        blobs_dir = tmp_path / ".ollama" / "models" / "blobs"
        blobs_dir.mkdir(parents=True)
        (blobs_dir / "sha256-deadbeef").write_bytes(b"fake gguf content")

        with (
            patch("agent.core.model_sync.Path.home", return_value=tmp_path),
            patch(
                "agent.core.model_sync._build_ollama_manifest_map",
                return_value={"deadbeef": "llama3:latest"},
            ),
        ):
            records = _discover_ollama_blobs()

        assert len(records) == 1
        assert records[0]["model_id"] == "llama3:latest"
        assert "sha256-deadbeef" in records[0]["file_path"]

    def test_blob_without_manifest_entry_excluded(self, tmp_path):
        blobs_dir = tmp_path / ".ollama" / "models" / "blobs"
        blobs_dir.mkdir(parents=True)
        (blobs_dir / "sha256-unknown999").write_bytes(b"fake")

        with (
            patch("agent.core.model_sync.Path.home", return_value=tmp_path),
            patch("agent.core.model_sync._build_ollama_manifest_map", return_value={}),
        ):
            records = _discover_ollama_blobs()

        assert records == []


class TestDiscoverFilesystem:
    def _config_with_scan_dirs(self, scan_dirs: list[str]) -> dict:
        return {
            "model_scan_dirs": scan_dirs,
            "models": [],
        }

    def test_gguf_file_included_with_mmproj(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        (model_dir / "my-model.Q4_K_M.gguf").write_bytes(b"fake")
        (model_dir / "my-model.mmproj-Q8_0.gguf").write_bytes(b"fake")

        with (
            patch("agent.core.model_sync._WELL_KNOWN_SCAN_DIRS", [model_dir]),
            patch("agent.core.model_sync._drive_walk", return_value=[]),
            patch("agent.core.model_sync._discover_ollama_blobs", return_value=[]),
        ):
            records = _discover_filesystem(self._config_with_scan_dirs([]))

        assert any("my-model.Q4_K_M.gguf" in r["file_path"] for r in records)
        main_rec = next(r for r in records if "my-model.Q4_K_M.gguf" in r["file_path"])
        assert main_rec["mmproj_path"] is not None
        assert "mmproj" in main_rec["mmproj_path"].lower()

    def test_mmproj_file_not_included_as_standalone_model(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        (model_dir / "net.Q4.gguf").write_bytes(b"fake")
        (model_dir / "net.mmproj.gguf").write_bytes(b"fake")

        with (
            patch("agent.core.model_sync._WELL_KNOWN_SCAN_DIRS", [model_dir]),
            patch("agent.core.model_sync._drive_walk", return_value=[]),
            patch("agent.core.model_sync._discover_ollama_blobs", return_value=[]),
        ):
            records = _discover_filesystem(self._config_with_scan_dirs([]))

        model_ids = [r["model_id"] for r in records]
        assert not any("mmproj" in m.lower() for m in model_ids)


class TestSyncFromProviders:
    def _make_config(self, tmp_path: Path, extra: dict | None = None) -> Path:
        config: dict = {
            "model_scan_dirs": [],
            "models": [
                {
                    "id": "existing-model",
                    "name": "Existing Model",
                    "provider": "llama_cpp",
                    "model_id": "existing-model.gguf",
                    "endpoint": "local://llama_cpp",
                    "file_path": "/fake/path/existing-model.gguf",
                    "capabilities": ["fast"],
                    "context_window": 4096,
                    "always_available": True,
                },
            ],
            "routing_rules": {"default": "existing-model"},
            "fallback_chain": ["existing-model"],
        }
        if extra:
            config.update(extra)
        path = tmp_path / "model_config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def test_new_model_appended(self, tmp_path):
        path = self._make_config(tmp_path)
        new_rec = {
            "model_id": "new-discovered.gguf",
            "file_path": "/fake/path/new-discovered.gguf",
            "provider": "llama_cpp",
            "mmproj_path": None,
        }
        with patch("agent.core.model_sync._discover_filesystem", return_value=[new_rec]):
            added = sync_from_providers(path)

        assert added == 1
        config = json.loads(path.read_text())
        model_ids = [m["model_id"] for m in config["models"]]
        assert "existing-model.gguf" in model_ids
        assert "new-discovered.gguf" in model_ids

    def test_idempotent_no_disk_write(self, tmp_path):
        path = self._make_config(tmp_path)
        mtime_before = path.stat().st_mtime_ns
        duplicate = {
            "model_id": "existing-model.gguf",
            "file_path": "/fake/path/existing-model.gguf",
            "provider": "llama_cpp",
            "mmproj_path": None,
        }
        with patch("agent.core.model_sync._discover_filesystem", return_value=[duplicate]):
            added = sync_from_providers(path)

        assert added == 0
        assert path.stat().st_mtime_ns == mtime_before

    def test_no_models_found_returns_zero(self, tmp_path):
        path = self._make_config(tmp_path)
        with patch("agent.core.model_sync._discover_filesystem", return_value=[]):
            added = sync_from_providers(path)
        assert added == 0

    def test_dedup_by_file_path(self, tmp_path):
        path = self._make_config(tmp_path)
        # Different model_id but same file_path as existing entry
        duplicate_path = {
            "model_id": "alias-for-existing",
            "file_path": "/fake/path/existing-model.gguf",
            "provider": "llama_cpp",
            "mmproj_path": None,
        }
        with patch("agent.core.model_sync._discover_filesystem", return_value=[duplicate_path]):
            added = sync_from_providers(path)

        assert added == 0
