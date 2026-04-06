## ADDED Requirements

### Requirement: System-wide GGUF discovery via filesystem scan

The system SHALL scan the local filesystem for `.gguf` files and return a list of discovery records, each containing the file's absolute path and a human-readable model name derived from the filename.

#### Scenario: Well-known dirs always scanned

- **WHEN** `_discover_filesystem()` is called
- **THEN** `~/.lmstudio/models/`, `C:\AI\`, and any paths in `model_scan_dirs` config key are always included regardless of drive walk results

#### Scenario: Drive walk descends only into dirs named "models"

- **WHEN** a drive root is walked
- **THEN** the scanner only recurses into directories whose name is exactly `models` (case-insensitive), up to depth 5, never descending past depth 5

#### Scenario: System directories are never scanned

- **WHEN** the scanner encounters a directory named `Windows`, `Program Files`, `Program Files (x86)`, `ProgramData`, `$Recycle.Bin`, `System Volume Information`, `Recovery`, `node_modules`, `.git`, `__pycache__`, or `site-packages`
- **THEN** that directory and all its children are skipped entirely

#### Scenario: PermissionError does not abort scan

- **WHEN** `os.scandir()` raises `PermissionError` on a directory
- **THEN** that directory is skipped and the scan continues with remaining paths

---

### Requirement: mmproj sibling detection

The system SHALL check each discovered `.gguf` file's parent directory for a sibling file matching `*mmproj*` (case-insensitive glob) and, if found, include its path in the discovery record.

#### Scenario: mmproj sibling present

- **WHEN** a `.gguf` file is discovered and a sibling file matching `*mmproj*` exists in the same directory
- **THEN** the discovery record includes `mmproj_path` set to the sibling's absolute path

#### Scenario: No mmproj sibling

- **WHEN** a `.gguf` file is discovered and no sibling file matching `*mmproj*` exists
- **THEN** the discovery record omits `mmproj_path` (key absent or `null`)

---

### Requirement: mmproj files excluded from model list

The system SHALL NOT register files whose filename contains `mmproj` as standalone model entries.

#### Scenario: mmproj file encountered during scan

- **WHEN** the scanner encounters a `.gguf` file whose name contains `mmproj`
- **THEN** that file is not added to the discovery results as a model entry

---

### Requirement: Deduplication by absolute path

The system SHALL not return duplicate entries for the same absolute file path when a file is reachable via both a well-known dir and a drive walk.

#### Scenario: Same file found twice

- **WHEN** the same absolute path is found via a well-known dir scan and again via drive walk
- **THEN** only one discovery record is emitted for that path
