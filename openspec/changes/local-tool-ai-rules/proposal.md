# Local Tool AI Rules — Per-Tool Instruction Files

**Date:** 2026-04-25
**Status:** PROPOSED
**Goal:** Give each local AI tool (Cline, Aider, Continue) its own rules file so known constraints and project context are loaded automatically, without relying on the user to re-explain them each session.

---

## Overview

Each tool in the local dev bundle reads instructions from a different location. This spec defines what goes in each, and where to put it. The rules are tool-specific files — completely independent of Claude Code.

A separate `CLAUDE.md` is also created at the project root so that Claude Code (when used directly) shares the same constraints. This is kept independent and does not affect the local bundle.

---

## Rules to Propagate

These are the known constraints and context that every AI tool in the bundle needs:

| Rule | Why |
|---|---|
| Run Aider from PowerShell or CMD only | Git Bash's terminal emulation conflicts with Aider's interactive UI (prompt-toolkit error) |
| Never auto-commit | `no-auto-commits: true` is in `.aider.conf.yml` but the AI should understand the intent: always show diff, let user commit |
| Forbidden directories are in external workspace | `N.E.K.O./`, `framework/` live in `C:\AI\roamin-external-workspace\` — not in this project |
| Roamin project context | This is a voice-activated ambient AI agent with TTS, wake word detection, and LM Studio integration |

---

## Per-Tool Implementation

### Cline → `.clinerules`

Cline reads `.clinerules` from the project root automatically. No configuration needed — just the file existing is enough.

**File:** `<project root>/.clinerules`

```markdown
# Roamin Project Rules

## Terminal
- When running Aider, always launch it from PowerShell or CMD — never from Git Bash.
  Git Bash's terminal emulation (xterm-256color) conflicts with Aider's interactive UI
  and causes a prompt-toolkit crash. Use: `Start-Process powershell -ArgumentList "aider"`,
  or instruct the user to run `aider` themselves from a PowerShell terminal.

## Git
- Never auto-commit. Always show the user a diff and let them commit manually.
- Use `--no-auto-commits` when invoking Aider.

## Project Context
- This is Roamin: a voice-activated ambient AI agent.
- Core pipeline: wake word (OpenWakeWord + Whisper validation) → chime → LLM → TTS playback (streaming).
- All AI inference goes through LM Studio at http://localhost:1234/v1.

## Off-Limits Directories
- `N.E.K.O./` and `framework/` are NOT in this project.
  They have been moved to C:\AI\roamin-external-workspace\. Do not reference,
  read, or create these directories inside this project.
```

---

### Aider → `.aider.rules.md`

Aider does not have a `--system-prompt` flag. The correct approach is `--read`,
which loads a file as **read-only context** — the model sees and respects its
contents but cannot edit it. Add it to `.aider.conf.yml` so it loads automatically
every session.

**File:** `<project root>/.aider.rules.md`

```markdown
# Roamin Project Rules

## Terminal
You are running on Windows 11. Aider must be launched from PowerShell or CMD —
never from Git Bash. Git Bash's terminal emulation conflicts with Aider's UI.
If instructing the user to open a terminal, specify PowerShell.

## Git
Never auto-commit changes. Always show the diff and wait for the user to commit.
The project uses `no-auto-commits: true` in .aider.conf.yml — respect this intent.

## Project Context
- This is Roamin: a voice-activated ambient AI agent (Python 3.12, Windows 11)
- Wake word detection: OpenWakeWord → Whisper post-validation → chime → LLM
- TTS: streaming playback, interruptible
- LLM inference: LM Studio at http://localhost:1234/v1 (OpenAI-compatible API)

## Off-Limits Directories
- N.E.K.O./, framework/ are in an external workspace at
  C:\AI\roamin-external-workspace\. Do not touch or reference them.
```

**Add to `<project root>/.aider.conf.yml`** (project-level, not global):
```yaml
read:
  - .aider.rules.md
```

> **Note:** `read:` must go in the **project-level** `.aider.conf.yml` at the Roamin root,
> not in `~/.aider.conf.yml`. The global config applies to every project — adding a
> project-relative path there causes a file-not-found error when Aider runs elsewhere.
> The path is relative to wherever you run `aider` from — always run from the project root.

---

### Continue → `.continuerc.json`

Continue reads `.continuerc.json` from the project root automatically and merges
it with your global `~/.continue/config.json`. This is the correct file-based
approach — no UI steps needed, and it can be committed to git.

**File:** `<project root>/.continuerc.json`

```json
{
  "systemMessage": "You are helping develop Roamin, a voice-activated ambient AI agent (Python 3.12, Windows 11). Core components: wake word (OpenWakeWord + Whisper), streaming TTS, LM Studio inference at http://localhost:1234/v1. Do not auto-commit. Always show diffs before committing. Avoid referencing N.E.K.O./, or framework/ — they are not in this project. If Aider needs to be run, instruct the user to do so from PowerShell, not Git Bash.",
  "mergeBehavior": "merge"
}
```

`mergeBehavior: merge` layers these instructions on top of the global config
rather than replacing it. Continue picks this up automatically when the Roamin
project is open in VS Code.

---

## CLAUDE.md (Claude Code — Separate)

`CLAUDE.md` is read by Claude Code (the Anthropic CLI) only. It is independent
of Cline, Aider, and Continue. Adding the same rules here ensures consistency
if Claude Code is ever used to call Aider directly.

**File:** `<project root>/CLAUDE.md`

The file covers the same four rule categories as the bundle files:
- **Terminal:** Aider must be launched from PowerShell/CMD, never Git Bash
- **Git:** Never auto-commit; always show diff and let user commit
- **Project Context:** Roamin pipeline, LM Studio endpoint
- **Off-Limits Directories:** `N.E.K.O./`, `framework/` in external workspace

---

## File Summary

| File | Tool | Auto-loaded | Location |
|---|---|---|---|
| `.clinerules` | Cline | Yes — on project open | Project root |
| `.aider.rules.md` | Aider | Yes — via `read:` in project-level `.aider.conf.yml` | Project root |
| `.continuerc.json` | Continue | Yes — on project open, merged with global config | Project root |
| `CLAUDE.md` | Claude Code | Yes — on session start | Project root |

---

## Installation Checklist

- [ ] Create `.clinerules` in project root (see content above)
- [ ] Create `.aider.rules.md` in project root (see content above)
- [ ] Add `read:` entry to project-level `.aider.conf.yml` (not global `~/.aider.conf.yml`):
  ```yaml
  read:
    - .aider.rules.md
  ```
- [ ] Create `.continuerc.json` in project root (see content above)
- [ ] Verify `CLAUDE.md` exists in project root
- [ ] Commit `.clinerules`, `.aider.rules.md`, `.continuerc.json`, and `.aider.conf.yml` to git

### Verification

After creating the files, confirm each tool loaded its rules:

| Tool | Verification |
|---|---|
| Cline | Open VS Code in this project → ask Cline: "What terminal should I use for Aider?" → should say PowerShell |
| Aider | Run `aider` from project root → check startup output for `.aider.rules.md` in the read-only files list |
| Continue | Open VS Code → ask Continue: "What should I avoid committing?" → should mention diffs/manual commit |
| Claude Code | Run `claude` from project root → it reads `CLAUDE.md` automatically on session start |

---

## What This Does NOT Do

- Does not change how any tool connects to LM Studio
- Does not modify model selection or context window behavior
- Does not affect Roamin's runtime — these are developer tooling files only
