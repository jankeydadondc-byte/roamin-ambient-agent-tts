## ADDED Requirements

### Requirement: Discover available models from LM Studio

The system SHALL query `GET /v1/models` on the LM Studio endpoint and return the list of model IDs currently loaded or available.

#### Scenario: LM Studio is reachable with models loaded

- **WHEN** LM Studio is running and has at least one model loaded
- **THEN** the discovery returns a non-empty list of model ID strings

#### Scenario: LM Studio is unreachable

- **WHEN** the LM Studio endpoint returns a connection error or timeout
- **THEN** the discovery returns an empty list and logs a warning; it SHALL NOT raise an exception

#### Scenario: LM Studio returns no models

- **WHEN** the endpoint is reachable but no models are loaded
- **THEN** the discovery returns an empty list

---

### Requirement: Discover available models from Ollama

The system SHALL query `GET /api/tags` on the Ollama endpoint and return the list of model name strings.

#### Scenario: Ollama is reachable with models pulled

- **WHEN** Ollama is running and has at least one model pulled
- **THEN** the discovery returns a non-empty list of model name strings

#### Scenario: Ollama is unreachable

- **WHEN** the Ollama endpoint returns a connection error or timeout
- **THEN** the discovery returns an empty list and logs a warning; it SHALL NOT raise an exception
