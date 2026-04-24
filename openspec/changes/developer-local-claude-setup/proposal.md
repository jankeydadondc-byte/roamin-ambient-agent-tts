# Developer Local Claude Setup — Unified Development Environment

**Date:** 2026-04-24
**Status:** PROPOSED
**Goal:** Provide a seamless local Claude Code alternative when cloud API quota is exhausted

---

## Overview

When developing Roamin, you have Claude API quota limits. This spec establishes a **complete, unified local development environment** using three complementary tools that together replicate Claude Code's capabilities:

- **Cline** — Primary agentic coder (read codebase, make edits, run tests)
- **Aider** — Optional CLI tool (autonomous refactoring, scripting, CI/CD)
- **Continue** — Optional in-editor assistance (autocomplete + sidebar chat)

**All three point to the same LM Studio instance** on `localhost:1234`, so you have a single, cohesive development experience without context-switching or reconfiguration.

---

## The Three-Tool Architecture

### Cline (Primary)
**VS Code Extension** — Agentic coder, closest to Claude Code in a single tool.

```
User: "Refactor the authentication module"
    ↓
Cline (in VS Code sidebar)
    ├─ Reads entire codebase
    ├─ Understands Roamin's structure
    ├─ Makes multi-file edits with diffs
    ├─ Runs tests to verify changes
    ├─ Executes git commits with rationale
    └─ Reports: "Done. 3 files changed, all tests pass."
```

**When to use:** Primary workflow for complex coding tasks, refactoring, feature implementation.

**Installation:**
```bash
# VS Code Extensions marketplace
# Search: "Cline" → Install

# Or via command line:
code --install-extension Cline.cline
```

**Configuration:**
Edit `~/.continue/config.json` (Continue creates this):
```json
{
  "cline": {
    "provider": "openai",
    "model": "qwopus3.5-27b-v3",
    "apiBase": "http://localhost:1234/v1",
    "apiKey": "not-needed"
  }
}
```

---

### Continue (Complement)
**VS Code Extension** — Inline assistance: autocomplete + quick chat.

```
While editing code:
  - Type normally → Continue suggests completions (2-3s latency)
  - Highlight code → Ctrl+I → "make this async" → inline edit
  - Ctrl+L → Ask questions: "Why does this function exist?"
```

**When to use:** Moment-to-moment assistance while actively coding. Quick answers without context-switching.

**Installation:**
```bash
# VS Code Extensions marketplace
# Search: "Continue" → Install
```

**Configuration:**
Same `~/.continue/config.json`:
```json
{
  "models": [
    {
      "title": "LM Studio Chat",
      "provider": "openai",
      "model": "qwopus3.5-27b-v3",
      "apiBase": "http://localhost:1234/v1",
      "apiKey": "not-needed"
    }
  ],
  "tabAutocompleteModel": {
    "title": "LM Studio Code",
    "provider": "openai",
    "model": "qwen/qwen2.5-coder-32b",
    "apiBase": "http://localhost:1234/v1",
    "apiKey": "not-needed"
  }
}
```

---

### Aider (Optional)
**CLI Tool** — Terminal-based agentic coder. Use when you prefer command-line workflows or need automation.

```bash
$ aider --model openai/qwen3-30b-a3b --openai-api-base http://localhost:1234/v1

/add src/          # Add files to context
/add tests/

Describe the change:
> Extract authentication into separate module

[Aider reads codebase, makes edits, runs tests, commits]

✓ Done. 3 files changed, tests pass.
```

**When to use:** Terminal-first workflows, batch processing, CI/CD integration, scripting complex refactors.

**Installation:**
```bash
pip install aider-chat
```

**Configuration:**
Create `~/.aider.conf.yml`:
```yaml
model: openai/qwen3-30b-a3b
openai-api-base: http://localhost:1234/v1
openai-api-key: not-needed
```

Or use inline:
```bash
aider --model openai/qwen3-30b-a3b --openai-api-base http://localhost:1234/v1
```

---

## LM Studio Setup (Shared Foundation)

All three tools point to a single LM Studio instance running on `localhost:1234`.

### Prerequisites
- LM Studio installed and running
- 3+ models loaded (for variety by task type)

### Recommended Model Selection

| Task | Model | Why |
|---|---|---|
| Autocomplete (Continue) | `qwen/qwen2.5-coder-32b` | Code-optimized, fast |
| Chat/questions (Continue) | `qwopus3.5-27b-v3` | Balanced reasoning, responsive |
| Complex edits (Cline) | `qwen/qwen3-30b-a3b` | Largest, best multi-file reasoning |
| Autonomous refactor (Aider) | `qwen/qwen3-30b-a3b` | Understands large codebases |

### Verify LM Studio is accessible

```bash
curl http://localhost:1234/v1/models
# Should return: {"data": [...], "object": "list", ...}
```

If this fails:
1. Check LM Studio is running (blue Server tab shows "Running")
2. Verify a model is loaded (green checkmark next to model name)
3. Check port is 1234 (Server Settings → Server Port)

---

## Workflow: Three Levels of Intensity

### Level 1: Quick Q&A (Continue Chat)
**Time:** Seconds
**When:** Quick questions while coding
```
Highlight function → Ctrl+L → "Why does this return null?"
Continue: "Because line 42 doesn't handle the edge case..."
```

### Level 2: Inline Edits (Continue Edit Mode)
**Time:** 10–30 seconds
**When:** Small fixes, one-file changes
```
Highlight code → Ctrl+I → "Add error handling here"
Continue: [Makes the edit inline, you accept/reject]
```

### Level 3: Complex Refactoring (Cline or Aider)
**Time:** 1–5 minutes
**When:** Multi-file changes, major restructuring
```
Cline/Aider: "Refactor the API routes to use middleware pattern"
[Reads codebase, makes edits across multiple files, runs tests, commits]
Done.
```

---

## Unified Config File

All three tools read from the same location: **`~/.continue/config.json`**

This single file controls:
- Model selection (which LM Studio model for which task)
- LM Studio endpoint (defaults to localhost:1234)
- API key (can be dummy for local)
- Per-tool preferences

**Master `~/.continue/config.json` for all three tools:**

```json
{
  "models": [
    {
      "title": "LM Studio General",
      "provider": "openai",
      "model": "qwopus3.5-27b-v3",
      "apiBase": "http://localhost:1234/v1",
      "apiKey": "not-needed"
    },
    {
      "title": "LM Studio Code",
      "provider": "openai",
      "model": "qwen/qwen2.5-coder-32b",
      "apiBase": "http://localhost:1234/v1",
      "apiKey": "not-needed"
    },
    {
      "title": "LM Studio Reasoning",
      "provider": "openai",
      "model": "qwen/qwen3-30b-a3b",
      "apiBase": "http://localhost:1234/v1",
      "apiKey": "not-needed"
    }
  ],
  "tabAutocompleteModel": {
    "title": "LM Studio Code",
    "provider": "openai",
    "model": "qwen/qwen2.5-coder-32b",
    "apiBase": "http://localhost:1234/v1",
    "apiKey": "not-needed"
  },
  "slashCommands": [
    {
      "name": "test",
      "description": "Generate test code",
      "prompt": "Write comprehensive unit tests for the selected code."
    },
    {
      "name": "refactor",
      "description": "Suggest refactoring",
      "prompt": "Suggest a refactoring to improve readability and maintainability."
    }
  ]
}
```

For Aider, keep `~/.aider.conf.yml` separate (Aider doesn't read Continue config):

```yaml
model: openai/qwen3-30b-a3b
openai-api-base: http://localhost:1234/v1
openai-api-key: not-needed
```

---

## Installation Checklist

- [ ] **LM Studio** running with 3+ models loaded
- [ ] **Cline** installed in VS Code (`code --install-extension Cline.cline`)
- [ ] **Continue** installed in VS Code (search "Continue" in Extensions)
- [ ] **Aider** installed (`pip install aider-chat`)
- [ ] **`~/.continue/config.json`** created with LM Studio endpoints
- [ ] **`~/.aider.conf.yml`** created with LM Studio endpoint
- [ ] **Verify connectivity:**
  ```bash
  curl http://localhost:1234/v1/models
  ```
- [ ] **Test each tool:**
  - Cline: Open Roamin codebase → sidebar → "Explain wake_listener.py"
  - Continue: Type code in any file → wait 3s → autocomplete appears
  - Aider: Terminal → `aider --model openai/qwen3-30b-a3b --openai-api-base http://localhost:1234/v1`

---

## Typical Development Workflow

```
Morning:
  1. Open Roamin in VS Code (Cline + Continue ready)
  2. Work on a feature using Cline for heavy lifting
  3. Use Continue for quick questions while coding
  4. When stuck on architectural decision, use Cline sidebar chat

Afternoon:
  5. Need to refactor 5 files → Cline handles it autonomously
  6. Small tweaks → Continue inline edits
  7. Verify with "Write tests for this module" → Cline generates tests

Evening:
  8. Review git log (Cline auto-committed)
  9. Prepare PR from local commits
  10. If Claude quota returns tomorrow, seamless switch back
```

---

## Cost & Licensing

- **Cline:** Free (open source, GitHub)
- **Continue:** Free (open source, GitHub)
- **Aider:** Free (open source, GitHub)
- **LM Studio:** Free (local, runs on your machine)
- **Models:** Free (GGUF files you've downloaded)

**Total cost: $0**

---

## Limitations vs Claude Code

| Feature | Claude Code | This Setup | Notes |
|---|---|---|---|
| Model quality | Sonnet/Opus | Qwen 30B local | Local models have lower ceiling on complex reasoning |
| Real-time collaboration | Yes | No | All local, single-user focus |
| Web search | Yes | No (Aider has workaround via tool) | No network access |
| Context window | 200k tokens | 4k–8k | Aider's code map mitigates; limits large codebases |
| Autocomplete latency | <100ms | 2–3s | Local inference is slower but free |
| First-token latency | ~200ms | 500ms–1s | Trade-off for local operation |

**The honest truth:** This setup won't match Claude Code's quality on very complex reasoning. But for day-to-day coding (refactoring, bug fixes, test writing, documentation), it's 80–90% as capable and **completely free**.

---

## When to Use vs When to Stick with Claude Code

**Use This Setup When:**
- Your Claude API quota is exhausted
- You want zero per-token costs
- You're working on Roamin (keep your project data local)
- You prefer open-source tools

**Stick with Claude Code When:**
- You're on a complex architectural task (Claude's reasoning is superior)
- You need real-time collaboration
- Your quota is available and cost isn't a concern
- You need web search or advanced tool integration

---

## Next Steps

1. **Install all three tools** (checklist above)
2. **Configure `~/.continue/config.json`** with your LM Studio endpoint
3. **Test each tool** with a simple task (ask a question, make an edit, run a refactor)
4. **Adjust model assignments** based on your workflow (what feels snappiest?)
5. **Develop Roamin** using this unified setup when Claude quota is exhausted

---

## Files & Directories

| Path | Purpose |
|---|---|
| `~/.continue/config.json` | Master config for Cline and Continue |
| `~/.aider.conf.yml` | Aider CLI configuration |
| `~/.continue/logs/` | Cline/Continue logs (if troubleshooting) |
| `~/.aider_history` | Aider conversation history |

All config is local. No data leaves your machine.

---

## Phase 2 (Optional): Local Dev Orchestrator

Once Phase 1 is stable, wrap all three tools with a lightweight **Python CLI orchestrator** that routes tasks intelligently so you don't have to decide which tool to use.

**Important:** This is a standalone developer tool — it lives outside the Roamin project, installed locally on your machine. It does not touch Roamin's codebase.

### What it does

Instead of manually choosing between Cline, Aider, and Continue, one command routes to the right tool automatically:

```bash
# Install locally (separate from Roamin)
pip install --user roamin-dev   # or: pip install -e ~/dev-tools/roamin-dev

# Usage
roamin-dev "refactor auth module"
→ Multi-file change detected → routes to Cline

roamin-dev --quick "why does this function return None?"
→ Quick question → routes to Continue sidebar chat

roamin-dev --batch "write tests for the entire voice module"
→ Autonomous batch work → routes to Aider CLI

roamin-dev --model reasoning "explain this architecture decision"
→ Complex reasoning → forces qwen/qwen3-30b-a3b via Cline
```

### Routing logic

| Signal | Route to | Model |
|---|---|---|
| Short question, single file | Continue (chat) | qwopus3.5-27b-v3 |
| Inline edit, single file | Continue (edit mode) | qwopus3.5-27b-v3 |
| Multi-file, mentions "refactor/extract/rename" | Cline | qwen/qwen3-30b-a3b |
| "write tests", "generate tests" | Cline | qwen/qwen3-30b-a3b |
| `--batch` flag or CI context | Aider | qwen/qwen2.5-coder-32b |
| `--quick` flag | Continue | qwopus3.5-27b-v3 |

### Implementation approach

**Python + Click/Typer** (recommended):

- Consistent with Roamin's Python environment — no new languages
- Direct access to LM Studio's OpenAI-compatible client
- Reads existing `~/.continue/config.json` and `~/.aider.conf.yml` — no new config format
- Lives in its own directory outside the Roamin repo (e.g., `~/dev-tools/roamin-dev/`)
- Version-controlled in its own separate git repo (not Roamin's)

```
~/dev-tools/roamin-dev/
├── roamin_dev/
│   ├── __init__.py
│   ├── cli.py          # Click/Typer entry point
│   ├── router.py       # Task classification → tool selection
│   ├── cline.py        # Cline VS Code API bridge
│   ├── aider.py        # Aider subprocess wrapper
│   ├── continue.py     # Continue.dev API bridge
│   └── config.py       # Reads ~/.continue/config.json
├── pyproject.toml
└── README.md
```

### What it does NOT do

- Does not modify or touch the Roamin project
- Does not run inside Roamin's process
- Does not hook into Roamin's agent loop
- Does not require Roamin to be running
- Does not share config with Roamin

It is a completely separate tool that happens to be useful for developing Roamin (and any other project).

### Status

**Not yet built.** Phase 1 (installing and using the three tools individually) should be stable first. The orchestrator is only valuable once you know how each tool behaves on your specific hardware and model setup.

When ready, open a new spec: `developer-local-orchestrator/proposal.md`.
