## ADDED Requirements

### Requirement: Idempotent upsert of discovered models

The system SHALL compare discovered model IDs against the `model_id` field of every existing entry in `model_config.json`. Models already present SHALL be silently skipped. Net-new models SHALL be appended with an inferred config entry.

#### Scenario: Model already in config

- **WHEN** a discovered model has a `model_id` that matches an existing entry in the `models` array
- **THEN** that entry is left completely unchanged and nothing is written to disk for it

#### Scenario: Net-new model discovered

- **WHEN** a discovered model ID has no matching entry in the `models` array
- **THEN** a new entry is inferred and appended to `model_config.json`

#### Scenario: No new models found

- **WHEN** all discovered models are already in the config
- **THEN** `model_config.json` is not written to disk at all

---

### Requirement: Atomic write of model_config.json

The system SHALL write changes to `model_config.json` atomically — write to a temp file, then rename — so a crash mid-write never produces a corrupt config file.

#### Scenario: Successful write

- **WHEN** the sync writes new entries
- **THEN** the existing file is replaced atomically and remains valid JSON

#### Scenario: Write fails partway through

- **WHEN** an I/O error occurs during the write
- **THEN** the original `model_config.json` is unchanged

---

### Requirement: Capability inference for new models

The system SHALL infer a `capabilities` array for each new model based on heuristic rules applied to the model name (case-insensitive substring matching).

#### Scenario: Model name contains "coder"

- **WHEN** the model name/ID contains "coder"
- **THEN** the inferred capabilities include `"code"` and `"json_output"`

#### Scenario: Model name contains "r1" or "deepseek-r1"

- **WHEN** the model name/ID contains "r1"
- **THEN** the inferred capabilities include `"reasoning"`, `"deep_thinking"`, and `"analysis"`

#### Scenario: Model name contains "vision" or "vl"

- **WHEN** the model name/ID contains "vision" or "-vl-"
- **THEN** the inferred capabilities include `"vision"` and `"screen_reading"`

#### Scenario: Model name matches no heuristic

- **WHEN** no heuristic rule matches the model name
- **THEN** the inferred capabilities default to `["fast", "general", "chat"]`

---

### Requirement: Sync runs once at startup before router is first used

The system SHALL invoke the model config sync during Roamin startup, before `ModelRouter` is used for any routing decision.

#### Scenario: Normal startup

- **WHEN** the Roamin process starts
- **THEN** `model_sync.sync_from_providers()` completes before the first call to `ModelRouter.select()`

#### Scenario: Sync raises an unexpected exception

- **WHEN** an unhandled error occurs inside the sync function
- **THEN** the error is logged and startup continues; Roamin SHALL NOT crash
