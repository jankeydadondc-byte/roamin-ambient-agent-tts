## MODIFIED Requirements

### Requirement: Idempotent upsert of discovered models

The system SHALL compare discovered model file paths against the `file_path` field (primary) and `model_id` field (secondary fallback) of every existing entry in `model_config.json`. Models already present SHALL be silently skipped. Net-new models SHALL be appended with an inferred config entry that includes `file_path`, `provider=llama_cpp`, and (if detected) `mmproj_path`.

#### Scenario: Model already in config by file_path

- **WHEN** a discovered model has a `file_path` that matches an existing entry's `file_path`
- **THEN** that entry is left completely unchanged and nothing is written to disk for it

#### Scenario: Model already in config by model_id (legacy entry without file_path)

- **WHEN** a discovered model's derived `model_id` matches an existing entry's `model_id` but no `file_path` is set on the existing entry
- **THEN** that entry is left unchanged (no backfill of `file_path` on existing entries)

#### Scenario: Net-new model discovered

- **WHEN** a discovered model has no matching `file_path` or `model_id` in the config
- **THEN** a new entry is inferred and appended to `model_config.json` with `file_path` and `provider=llama_cpp`

#### Scenario: No new models found

- **WHEN** all discovered models are already in the config
- **THEN** `model_config.json` is not written to disk at all

---

## ADDED Requirements

### Requirement: model_scan_dirs config key

The system SHALL read an optional `model_scan_dirs` array from `model_config.json` and include those paths as additional well-known scan roots, appended to the built-in defaults.

#### Scenario: model_scan_dirs present in config

- **WHEN** `model_config.json` contains `"model_scan_dirs": ["D:\\Models", "E:\\AI"]`
- **THEN** those directories are scanned for `.gguf` files in addition to the built-in well-known dirs

#### Scenario: model_scan_dirs absent from config

- **WHEN** `model_config.json` does not contain a `model_scan_dirs` key
- **THEN** only built-in well-known dirs and drive walk results are used; no error is raised
