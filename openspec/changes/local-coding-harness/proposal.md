# Developer Local Coding Harness — Aider + Continue.dev + LM Studio

**Date:** 2026-04-24
**Status:** PROPOSED
**Goal:** Provide developers a local Claude Code alternative for building Roamin when cloud API quota is exhausted

**Note:** This is a developer tool guide for those working ON Roamin, not part of Roamin itself.

---

## Why

Developers building Roamin need a local coding harness for when Claude API quota runs out. This guide establishes
a **local, fully-capable coding environment** with the ability to:

1. Read and modify code across multiple files (like Claude Code `@codebase`)
2. Run shell commands, tests, git operations (like Claude Code `@terminal`)
3. Leverage agentic reasoning to decompose tasks and iterate

Claude Code's harness is built around Sonnet/Opus (4.0 family) — expensive and cloud-dependent.
This spec brings that capability entirely local via two complementary tools:

- **Aider:** Terminal-based agentic coder (closest to Claude Code for local models)
- **Continue.dev:** VS Code inline assistance (autocomplete + sidebar chat)

Together, they replace Oboto (which was too general-purpose and had integration issues) and provide
a focused, battle-tested local coding environment.

---

## Architecture

**For developers building Roamin:**

```
Developer's Local Claude Alternative
├── VS Code
│   ├── Cline extension (primary tool)
│   │   ├── Agentic coding (read codebase, make multi-file edits)
│   │   ├── Test execution & verification
│   │   ├── Git integration
│   │   └── Shell command execution
│   │
│   ├── Continue.dev extension (complement)
│   │   ├── Inline autocomplete (as-you-type)
│   │   ├── Sidebar chat: quick questions about code
│   │   └── Code explanation & refactoring suggestions
│   │
│   └── Terminal (integrated)
│       └── Aider CLI (optional, for terminal-first workflows)
│           ├── Autonomous refactoring tasks
│           ├── Smart context window management
│           ├── Auto git commits with rationale
│           └── Batch processing / CI integration
│
└── LM Studio (localhost:1234)
    ├── qwopus3.5-27b-v3       (Cline/Continue: chat, quick tasks)
    ├── qwen/qwen2.5-coder-32b (Aider: code-specific)
    └── qwen/qwen3-30b-a3b     (Cline: complex reasoning)

Roamin (unchanged)
└── Still runs independently as ambient voice agent
```

---

## Component 1 — Aider

### What it does

Command-line AI coder. You describe a task in English, Aider:
1. Reads your entire repository (built-in code map)
2. Understands the structure and existing patterns
3. Makes edits across multiple files
4. Runs tests to verify changes
5. Commits with a descriptive message
6. Asks clarifying questions if needed

**Example workflow:**
```bash
$ aider --model openai/qwen3-30b-a3b --openai-api-base http://localhost:1234/v1
Aider initialized. Type 'help' for commands.

/add src/        # Add src/ to the context window
/add tests/      # Add tests/ too

Describe the change:
> Extract the authentication logic from main.py into a new auth.py module, update imports in all files

[Aider reads code, makes edits, runs tests]

✓ Refactored authentication into auth.py
✓ Updated imports in 3 files
✓ Tests pass (5/5)

Committed: refactor(auth): extract authentication to separate module
```

### Installation & Setup

**1. Install Aider**
```bash
pip install aider-chat
```

**2. Configure for LM Studio**
```bash
# ~/.aider.conf.yml
model: openai/qwen3-30b-a3b
openai-api-base: http://localhost:1234/v1
openai-api-key: not-needed-for-local
```

Or inline:
```bash
aider --model openai/qwen3-30b-a3b --openai-api-base http://localhost:1234/v1
```

**3. Model selection**
- **General/reasoning:** `qwen/qwen3-30b-a3b` (largest, handles complex refactors)
- **Quick edits:** `qwopus3.5-27b-v3` (balanced speed/quality)
- **Code-specific:** `qwen/qwen2.5-coder-32b` (optimized for code tasks)

### Key Commands

```
/add <path>           # Add files/dirs to context
/drop <path>          # Remove from context
/ls                   # List context window
/run <cmd>            # Execute shell command
/test                 # Run test suite
/diff                 # Show pending changes
/undo                 # Revert last change
/commit <msg>         # Commit with message
```

### Typical workflow

```bash
cd ~/your-project
aider --model openai/qwen3-30b-a3b --openai-api-base http://localhost:1234/v1

/add .                # Add entire repo
Refactor the API routes to use the new error handling pattern we established
[Aider thinks, edits, tests]
/test                 # Verify tests pass
✓ Ready to commit

quit                  # Exit when done
```

---

## Component 2 — Continue.dev

### What it does

VS Code extension for in-editor AI assistance:

1. **Inline autocomplete** — as you type, suggests next lines of code
2. **Sidebar chat** — ask questions about code without leaving the editor
3. **Command palette** — quick actions (explain, refactor, generate tests, debug)
4. **Ctrl+I (Edit mode)** — highlight code → "make this async" → applies edit
5. **Ctrl+L (Chat mode)** — ask questions about selected code

**Example workflow:**
```
User: Highlight a function → Ctrl+I
User: "Add error handling for database exceptions"
Continue.dev: Makes the edit inline, you accept/reject

User: Highlight test file → Ctrl+L
User: "Why is this test flaky?"
Continue.dev: Analyzes, explains race condition, suggests fix
```

### Installation & Setup

**1. Install Continue.dev**
- VS Code: Extensions marketplace → search "Continue"
- Or: `code --install-extension Continue-Dev.continue`

**2. Configure for LM Studio**

Create/edit `~/.continue/config.json`:

```json
{
  "models": [
    {
      "title": "LM Studio Chat",
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
    }
  ],
  "tabAutocompleteModel": {
    "title": "LM Studio Autocomplete",
    "provider": "openai",
    "model": "qwen/qwen2.5-coder-32b",
    "apiBase": "http://localhost:1234/v1",
    "apiKey": "not-needed"
  },
  "slashCommands": [
    {
      "name": "test",
      "description": "Generate test code",
      "prompt": "Generate comprehensive tests for the selected code. Follow the existing test patterns in the codebase."
    },
    {
      "name": "refactor",
      "description": "Suggest a refactoring",
      "prompt": "Suggest a refactoring of the selected code to improve readability and maintainability."
    }
  ]
}
```

**3. VS Code settings.json (optional optimizations)**

```json
{
  "continue.enableTabAutocomplete": true,
  "continue.useManualTabAutocompleteOnlyOnDoubleNewline": false,
  "[python]": {
    "editor.defaultFormatter": "black",
    "editor.formatOnSave": true
  }
}
```

### Key Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+L` | Start chat sidebar (ask about selected code) |
| `Ctrl+I` | Edit mode (highlight code → edit in place) |
| `Ctrl+K` | Clear chat history |
| `Tab` (at end of line) | Accept autocomplete suggestion |
| `Escape` | Reject autocomplete |
| `Ctrl+Shift+I` | Open Continue sidebar |

### Typical workflow

```
1. Open a file in VS Code
2. Type code normally — Continue suggests completions
3. Select a block → Ctrl+I → "extract this into a helper function"
4. Continue makes the edit inline, you approve
5. Later: Ctrl+L → ask "why does this function exist?"
6. Continue reads codebase context, explains
```

---

## Model Selection by Task

| Task | Recommended Model | Why |
|---|---|---|
| Autocomplete (Continue) | qwen/qwen2.5-coder-32b | Fast, code-optimized, ~2-3s latency |
| Chat questions (Continue) | qwopus3.5-27b-v3 | Balanced reasoning + speed |
| Multi-file refactoring (Aider) | qwen/qwen3-30b-a3b | Largest, best at understanding complex codebases |
| Complex bug analysis | qwen/qwen3-30b-a3b | Deep reasoning |
| Quick edits | qwopus3.5-27b-v3 | Faster iteration |

---

## Workflow: From Voice to Code

Roamin's voice-first interface stays intact. New capability:

1. **User (voice):** "Roamin, refactor the authentication system"
   - Roamin processes via agent loop (reads docs, understands intent)
   - Response: "I'll start the refactoring. Open VS Code and follow along."

2. **User opens VS Code**
   - Continue.dev is already configured, ready for chat
   - Aider is ready in terminal
   - User can guide the refactoring in real-time via Aider CLI
   - Or ask Continue.dev inline questions as they code

3. **Back to voice**
   - Once code changes are done, user can ask Roamin to verify: "Did the tests pass?"
   - Roamin can read the git log or test output

This bridges voice (what to do) and code (how to do it).

---

## Files & Configuration

### New files created

| Path | Purpose |
|---|---|
| `~/.continue/config.json` | Continue.dev model + command config |
| `~/.aider.conf.yml` | Aider CLI defaults |
| `~/.aider_model_settings.json` | Aider per-model tuning (optional) |

### Existing Roamin files (no changes needed)

- `agent/core/voice/wake_listener.py` — remains as-is, voice interface unchanged
- `agent/core/agent_loop.py` — can optionally accept task input from Aider (future enhancement)

### Documentation to add

| Path | Content |
|---|---|
| `docs/LOCAL_CODING_HARNESS.md` | User guide for Aider + Continue.dev |
| `docs/LM_STUDIO_SETUP.md` | How to load models, verify endpoint, troubleshoot |
| `docs/AIDER_RECIPES.md` | Common Aider tasks and workflows |
| `docs/CONTINUE_TIPS.md` | Continue.dev keyboard shortcuts and workflow patterns |

---

## Phases

### Phase 1 — Setup & Verification (this spec)
1. Install Aider via pip
2. Install Continue.dev in VS Code
3. Configure both to point at `http://localhost:1234/v1`
4. Test both tools with simple tasks (autocomplete, chat, single-file edit)
5. Verify LM Studio models are loaded and responding

### Phase 2 — Integration Testing (after Phase 1 ships)
Run 10+ coding tasks:
- Aider: multi-file refactoring, test generation, bug fixes
- Continue: autocomplete quality, chat latency, edit accuracy
- Measure: task success rate, model latency, token usage
- Adjust model selection based on observed performance

### Phase 3 — Bridge to Roamin Voice (future)
- Optional: wire Aider CLI output back to voice (Roamin reads back what it did)
- Optional: accept voice input as Aider task descriptions
- Keep the two systems separate unless bridge adds clear value

---

## What This Does NOT Include

- **Copilot-style hosted features** (GitHub Copilot subscription, Claude API)
- **Real-time collaboration** (all local, single-user focus)
- **Mobile/remote access** (designed for local desktop)
- **Proprietary models** (uses whatever LM Studio has loaded)

All processing happens on your machine. No data leaves localhost.

---

## Success Criteria

✓ Aider can read entire repo and make multi-file edits
✓ Continue.dev autocomplete triggers after 2–3s of idle typing
✓ Continue.dev sidebar chat responds in < 10s
✓ Both tools use LM Studio models (no cloud API calls)
✓ 80%+ success rate on common coding tasks (refactor, test gen, debug)

---

## Known Limitations

- **Model ceiling:** Local models (30B max) struggle with very large codebases (100k+ LOC). Aider's code map helps but won't match Sonnet/Opus on complex reasoning.
- **First-token latency:** Autocomplete has ~2–3s TTFT (time to first token). More than Claude Code but reasonable for local inference.
- **Context window:** Most loaded models have 4–8k context. Aider's code map mitigates by reading the most relevant files, not the entire repo.
- **No web browsing:** Aider can't search the web. Limited to local code + LLM reasoning.
- **Token efficiency:** Local models are less efficient. Same task may consume 2–3x more tokens than Sonnet.

These are fundamental trade-offs of "local Claude Code" — the alternative is to accept these limits or use Claude Code in the cloud.
