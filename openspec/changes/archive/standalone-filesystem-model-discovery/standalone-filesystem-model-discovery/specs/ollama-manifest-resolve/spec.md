## ADDED Requirements

### Requirement: Build SHA256-to-name map from Ollama manifests

The system SHALL parse all manifest files under `~/.ollama/models/manifests/` to build a `dict[str, str]` mapping each SHA256 hex digest to a `name:tag` friendly string, used to resolve blob filenames to model names.

#### Scenario: Valid manifest with model layer

- **WHEN** a manifest file is parsed and contains a layer with `mediaType == "application/vnd.ollama.image.model"`
- **THEN** the `digest` field of that layer (format `sha256:<hex>`) is mapped to the friendly `name:tag` string derived from the manifest's file path (`.../library/<name>/<tag>`)

#### Scenario: Manifest with no model layer

- **WHEN** a manifest file contains no layer with `mediaType == "application/vnd.ollama.image.model"`
- **THEN** no entry is added to the map for that manifest

#### Scenario: Malformed manifest JSON

- **WHEN** a manifest file cannot be parsed as valid JSON
- **THEN** that file is skipped with a warning log and parsing continues for remaining manifests

#### Scenario: Manifests directory absent

- **WHEN** `~/.ollama/models/manifests/` does not exist
- **THEN** the function returns an empty dict without raising

---

### Requirement: Resolve Ollama blob files using the SHA256 map

The system SHALL scan `~/.ollama/models/blobs/` and, for each file whose name matches `sha256-<hex>`, look up `<hex>` in the manifest map. Files with a match are included in discovery results using the friendly `name:tag` as the model name. Files with no match are skipped.

#### Scenario: Blob with manifest entry

- **WHEN** a blob file named `sha256-<hex>` is found and `<hex>` is in the manifest map
- **THEN** a discovery record is returned with `model_id = name:tag`, `file_path = absolute blob path`, and `provider = llama_cpp`

#### Scenario: Blob with no manifest entry

- **WHEN** a blob file is found but its SHA256 is not in the manifest map
- **THEN** that file is skipped and no discovery record is emitted for it

#### Scenario: Blobs directory absent

- **WHEN** `~/.ollama/models/blobs/` does not exist
- **THEN** no records are returned and no error is raised
