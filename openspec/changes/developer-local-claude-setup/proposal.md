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

**All three point to the same LM Studio instance** on `localhost:1234`. Each tool has its own config (they do not share), but all point at the same endpoint.

> **Windows paths:** Throughout this document, `~` means your user home directory — on Windows that's `C:\Users\YourName\`. So `~/.continue/config.json` is `C:\Users\YourName\.continue\config.json`, etc.

> **Hardware note:** LM Studio can load multiple models in VRAM simultaneously. Whether you keep multiple loaded or swap depends on your GPU memory. For reference: Qwopus3.5-27B-v3 and similar 27B models at Q4 quantization need ~20 GB VRAM each; 7B models need ~6 GB.

> **Prerequisite setup:** Before running this three-tool setup, move `N.E.K.O./` and `framework/` directories to a separate workspace outside your main Roamin project directory. This prevents all three tools from accidentally reading/editing these directories, and keeps your Roamin workspace clean.

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
    ├─ Runs tests to verify changes (if you ask it to)
    ├─ Proposes a git commit — you approve before it runs
    └─ Reports: "Done. 3 files changed, all tests pass."
```

**When to use:** Primary workflow for complex coding tasks, refactoring, feature implementation.

**Installation:**
```bash
# VS Code Extensions marketplace
# Search: "Cline" by saoudrizwan → Install

# Or via command line:
code --install-extension saoudrizwan.claude-dev
```

**Configuration:**

1. Open VS Code → Click the Cline icon in the Activity Bar
2. Click the gear icon (⚙️) in the Cline sidebar
3. Set up your provider:
   - **Provider:** OpenAI-compatible
   - **Base URL:** `http://localhost:1234/v1`
   - **API Key:** `not-needed` (LM Studio ignores this; any string works)
   - **Model:** Cline queries `http://localhost:1234/v1/models` automatically and displays available models. Select the one you want to use (e.g., `qwopus3.5-27b-v3`, `qwen3-30b-a3b`, etc.)

**MCP Server Configuration:**

Cline supports MCP servers (same protocol as Claude Code). To add MCP servers:

1. In Cline sidebar, click the MCP plug icon
2. Click "Install MCP Server" and follow the prompts
3. Cline stores MCP config in its own location (you do not need to manually edit files)

You can wire Cline to the same MCPs you use with Claude Code for near-identical tool access.

### Cline → Aider Delegation

You don't have to choose between Cline and Aider — you can use Cline to tell Aider what to do:

```
You (in Cline):  "Run aider to refactor the database module across all files in src/db/"

Cline:           Executes: aider src/db/*.py   (model comes from ~/.aider.conf.yml)
                 Watches the output
                 Reports back: "Aider completed. 4 files changed. Review the diff?"
```

This means you stay in VS Code the whole time and let Cline decide when Aider is the right tool, launch it, and show you the result.

---

### Continue (Complement)
**VS Code Extension** — Inline assistance: autocomplete + quick chat.

```
While editing code:
  - Type normally → Continue suggests completions (latency varies by model/GPU)
  - Highlight code → Ctrl+I → "make this async" → inline edit
  - Ctrl+L → Ask questions: "Why does this function exist?"
```

**When to use:** Moment-to-moment assistance while actively coding. Quick answers without context-switching.

**Installation:**
```bash
# VS Code Extensions marketplace
# Search: "Continue" → Install
```

**Configuration** (`~/.continue/config.json`):

Create or edit `~/.continue/config.json`. Add one entry per model you want available in Continue's dropdown:

```json
{
  "models": [
    {
      "title": "Qwopus 27B (Chat)",
      "provider": "openai",
      "model": "qwopus3.5-27b-v3",
      "apiBase": "http://localhost:1234/v1",
      "apiKey": "not-needed"
    },
    {
      "title": "Qwen 7B (Fast)",
      "provider": "openai",
      "model": "qwen2.5-7b-instruct",
      "apiBase": "http://localhost:1234/v1",
      "apiKey": "not-needed"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Qwen Coder 7B (Autocomplete)",
    "provider": "openai",
    "model": "qwen2.5-coder-7b",
    "apiBase": "http://localhost:1234/v1",
    "apiKey": "not-needed"
  }
}
```

In the Continue sidebar, the model dropdown lets you switch between whichever models are listed here. Only models that are currently loaded in LM Studio will respond — if a model is listed but not loaded, requests to it will fail. **Continue adapts its behavior to each model's context window** — no manual configuration needed.

> **Model name format:** Use the exact identifier shown in LM Studio's Server tab (e.g., `qwopus3.5-27b-v3`, not `Qwopus3.5-27B-v3-Q4_K_M`). Capitalization and quantization suffix may differ depending on how you downloaded the model.

---

### Aider (Optional)
**CLI Tool** — Terminal-based agentic coder. Use when you want to run a task from the terminal, or when you ask Cline to delegate to Aider (see [Cline → Aider delegation](#cline--aider-delegation) above).

```bash
$ aider                 # uses default model from ~/.aider.conf.yml

/add src/agent/     # Tell Aider which files to work on
/add tests/

> Extract authentication into separate module

[Aider reads the files, makes edits, shows you a diff]

✓ Done. 3 files changed. (No commit yet — review first)
```

**When to use:** When you want to describe a task in plain English and let the model work through multiple files on its own, or when Cline routes a task to it.

**Installation:**
```bash
# Use a venv or --user flag — don't install to system Python on Windows
pip install --user aider-chat
```

**Configuration** (`~/.aider.conf.yml`):

```yaml
openai-api-base: http://localhost:1234/v1
openai-api-key: not-needed
model: openai/qwopus3.5-27b-v3    # default model; override per-session with --model
no-auto-commits: true              # IMPORTANT: review changes before committing
```

> **Model selection:** Unlike Cline, Aider requires a model to be specified — it does not present an interactive picker. Set your default in `.aider.conf.yml`. Override for a session with `aider --model openai/qwen3-30b-a3b`. Aider **automatically reads the model's context window** from LM Studio and adapts its repo map strategy — no manual tuning needed.

> **Auto-commits:** Aider commits after every accepted change by default. `no-auto-commits: true` prevents this so you can review the diff before committing. Highly recommended when working on Roamin.

---

## LM Studio Setup (Shared Foundation)

All three tools point to a single LM Studio instance running on `localhost:1234`.

**How each tool discovers models:**
- **Cline** — queries `http://localhost:1234/v1/models` on startup and shows a dropdown of all loaded models. Pick one.
- **Continue** — reads model names from `~/.continue/config.json`. The setup script (`tools/setup_local_dev.py`) generates this file automatically from your actual installed models.
- **Aider** — uses the model specified in `~/.aider.conf.yml`. The setup script picks the best default automatically.

All three tools **automatically read each model's context window** from LM Studio's metadata and adapt accordingly — no manual context window configuration needed.

### Intelligent Model Loading

LM Studio can load multiple models simultaneously, but you should adopt an **intelligent, deterministic strategy** based on your GPU's available VRAM:

**Decision logic:**

1. **Query your total GPU VRAM** (e.g., RTX 4090 = 24 GB)
2. **Check which models you use most:**
   - Light tasks (chat, autocomplete): small models (7B = ~6 GB)
   - Heavy tasks (multi-file refactor): large models (27B = ~20 GB)
3. **Apply this rule:**
   - **If you need a 27B model and it leaves <4 GB free:** Unload other models. Load only the 27B. When done, load smaller models back.
   - **If you're swapping between small models (7B + 9B = ~12 GB total) and still have >8 GB free:** Keep both loaded. No switching latency.
   - **If a task needs more VRAM than available:** Offload or use a smaller model variant.

This way, LM Studio's model management is **intelligent** (based on available resources) and **deterministic** (same conditions → same decision).

### Recommended Models — Auto-Discovered

Model names, VRAM estimates, and defaults are **not hardcoded in this proposal**. Run the setup script to generate accurate configs from your actual GPU and installed models:

```bash
python tools/setup_local_dev.py
```

The script:
1. Queries `nvidia-smi` for your actual GPU VRAM total and free
2. Queries LM Studio's API for the exact model IDs it is serving
3. Scans `~/.lmstudio/models` for GGUF files and measures their sizes
4. Computes VRAM estimates (file size × 1.08 overhead factor)
5. Determines which models can be co-loaded simultaneously vs must be swapped
6. Selects the best Aider default (largest reasoning model that fits with 2 GB headroom)
7. Selects the best autocomplete model (prefers coder-tagged models)
8. Writes `~/.continue/config.json` and `~/.aider.conf.yml` with verified model IDs

Re-run the script any time you add or remove models from LM Studio.

Use `--dry-run` to preview output without writing files:

```bash
python tools/setup_local_dev.py --dry-run
```

> **Context window auto-detection:** Cline and Aider automatically query each model's context window from LM Studio's metadata and adapt their code chunking and repo mapping strategies. You do not need to set this manually.

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
You: "Refactor the API routes to use middleware pattern"
Cline/Aider: reads codebase, makes edits across multiple files, shows you a diff
You: review diff → accept or reject → commit manually
```

---

## Config Files Summary

Each tool has its own config — there is no shared config file across all three.

| Tool | Config Location | How Configured |
|---|---|---|
| Cline | VS Code extension storage (managed by Cline) | Via Cline sidebar gear icon — no manual file editing |
| Continue | `~/.continue/config.json` | JSON file — list each model explicitly |
| Aider | `~/.aider.conf.yml` | YAML file — set default model and API base |

---

## Installation Checklist

**Prerequisite:**
- [ ] Move `N.E.K.O./` and `framework/` to a separate workspace outside the Roamin project

**Setup:**
- [ ] **LM Studio** installed and running with at least one model loaded
- [ ] **Cline** installed in VS Code (`code --install-extension saoudrizwan.claude-dev`)
- [ ] **Cline** configured via the gear icon (API provider, base URL)
- [ ] **Continue** installed in VS Code (search "Continue" in Extensions)
- [ ] **Aider** installed (`pip install --user aider-chat`)
- [ ] **Run setup script** — auto-generates `~/.continue/config.json` and `~/.aider.conf.yml`:
  ```bash
  python tools/setup_local_dev.py
  ```

**Verification:**
- [ ] Check LM Studio connectivity:
  ```bash
  curl http://localhost:1234/v1/models
  # Should return: {"data": [...], "object": "list", ...}
  ```
- [ ] Test Cline:
  - Open Roamin in VS Code
  - Cline sidebar → click model dropdown → see available models from LM Studio
  - Ask Cline: "Explain wake_listener.py"

- [ ] Test Continue:
  - Type code in any file → wait for autocomplete
  - Highlight code → Ctrl+L → ask a question

- [ ] Test Aider:
  - Terminal: `cd` to Roamin directory
  - Run: `aider` (uses default model from `.aider.conf.yml`)
  - Aider starts and shows which model it connected to
  - Type a simple request: `"explain what wake_listener.py does"` and confirm

---

## Typical Development Workflow

```
Morning:
  1. Open Roamin in VS Code (Cline + Continue ready)
  2. Check VRAM available → if total VRAM > (27B size + 7B size + 4 GB buffer), load both simultaneously
     Otherwise load only the 27B for heavy morning work
  3. Work on a feature using Cline for heavy lifting
  4. Use Continue for quick questions while actively editing
  5. When stuck on architectural decision → Cline sidebar chat

Afternoon:
  6. If switching to lighter tasks (reading, docs, small edits):
     If 27B is taking most VRAM, swap to 7B in LM Studio
     If VRAM allows both, keep 27B loaded (no need to switch)
  7. Small tweaks → Continue inline edits
  8. Need multi-file work again → Cline, or ask Cline to run Aider

Evening:
  9. Review staged changes (no-auto-commits means nothing committed yet)
  10. Commit selectively, prepare PR
  11. If Claude quota returns tomorrow, seamless switch back
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
| Model quality | Sonnet/Opus | Qwen 7B–27B local | Local models have lower ceiling on complex reasoning |
| Real-time collaboration | Yes | No | All local, single-user focus |
| Web search | Yes (tool-use) | No | No network access by default |
| Context window | 200k tokens | 32k–128k auto-detected | Qwen models auto-report context window; tools adapt automatically |
| Autocomplete latency | <100ms | 0.5–3s | Depends heavily on GPU; RTX 3090/4090 is near-instant on 7B |
| First-token latency | ~200ms | 300ms–2s | Hardware-dependent |
| MCP servers | Yes | Cline only | Cline supports MCP; Aider/Continue do not |
| Model selection | Cloud (fixed) | Local GGUF (flexible) | You choose which model is loaded; all three tools read whatever LM Studio is serving |

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

1. **Move forbidden dirs** (`N.E.K.O./`, `framework/`) to a separate workspace
2. **Install all three tools** (checklist above)
3. **Configure each tool** with your LM Studio endpoint and model names
4. **Test each tool** with a simple task (ask a question, make an edit, run a refactor)
5. **Adjust model assignments** based on what feels snappiest on your GPU
6. **Develop Roamin** using this setup when Claude quota is exhausted

---

## Files & Directories

| Path | Purpose |
|---|---|
| `~/.continue/config.json` | Continue configuration — lists models explicitly; points to LM Studio |
| `~/.aider.conf.yml` | Aider CLI configuration — sets default model and API endpoint |
| Cline VS Code settings panel | Cline configuration (gear icon in sidebar) |
| `cline_mcp_settings.json` | Cline's MCP server configuration (auto-managed via VS Code) |
| `~/.continue/logs/` | Continue logs (troubleshooting) |
| `~/.aider_history` | Aider conversation history |

All config is local. No data leaves your machine.

**Forbidden directories (moved to separate workspace, no ignore files needed):**
- `N.E.K.O./`
- `framework/`

These are no longer in your Roamin project directory, so Cline/Aider/Continue will not accidentally access them.

---

## Phase 2 (Optional): Local Dev Orchestrator

Once Phase 1 is stable, a lightweight **Python CLI orchestrator** can automate common tasks so you don't manually open Aider each time.

**Scope:** The orchestrator handles **Aider automation + direct LM Studio API calls only.** Cline and Continue remain interactive tools in VS Code.

**Why this scope?**
- **Aider:** Has a clean CLI/subprocess interface — easy to automate via `subprocess.run()`
- **Cline/Continue:** VS Code extensions with no external API. You cannot call them from Python; you must use them interactively in VS Code
- **Phase 1 focus:** Using Cline and Continue by hand is fast enough for daily work. Phase 2 is for when you find yourself typing the same Aider commands over and over and want to shortcut them

**Important:** This is a standalone developer tool — it lives outside the Roamin project, installed locally on your machine. It does not touch Roamin's codebase.

### What Phase 2 does

```bash
roamin-dev "refactor auth module"
→ Multi-file change detected → launches Aider automatically
→ Aider reads the prompt, makes edits, shows you the diff
→ You review and commit manually; nothing is committed automatically

roamin-dev --quick "why does this function return None?"
→ Quick question → calls LM Studio API directly
→ Returns answer to stdout (no tool bridge needed)

roamin-dev --batch "write tests for the entire voice module"
→ Autonomous batch work → launches Aider with --yes flag
→ Aider processes entire task non-interactively
```

### Routing logic

| Signal | Route to | Automation Level |
|---|---|---|
| Short question (no files mentioned) | LM Studio API direct (HTTP) | Fully automated |
| Multi-file refactor, `--batch` flag | Aider subprocess | Aider makes edits; you review diff and commit manually |
| Anything requiring human judgment | Manual Cline in VS Code | You stay interactive |

### Implementation notes

**Aider subprocess wrapper:**
```python
# ~/.aider.conf.yml already sets openai-api-base and no-auto-commits
# Only pass flags that override or extend the config
subprocess.run([
    "aider",
    "--yes",              # Non-interactive: don't ask for edit confirmations
    "--message", user_prompt,   # The task to perform
    *files_to_edit
])
```

**Direct LM Studio API:**
```python
response = requests.post("http://localhost:1234/v1/chat/completions", json={
    "model": selected_model,
    "messages": [{"role": "user", "content": user_prompt}],
    # omit max_tokens to use the model's default; avoids cutting off long answers
})
```

**Do NOT automate:**
- Cline (no external API — use it interactively in VS Code, or ask it to call Aider)
- Continue (no external API)
- Git commits (always require human review; `--no-auto-commits` keeps Aider from auto-committing)

**`--yes` vs `--no-auto-commits` in Aider:**
These are not contradictory — they control different things:
- `--yes` = don't ask "are you sure?" before making file edits (just do it)
- `--no-auto-commits` = do not run `git commit` after edits (you review and commit manually)
Together they mean: "make the edits without confirmation prompts, but stop before committing."

### Implementation approach

**Python + Click/Typer** (consistent with Roamin's Python environment):

```
~/dev-tools/roamin-dev/
├── roamin_dev/
│   ├── __init__.py
│   ├── cli.py          # Click/Typer entry point
│   ├── router.py       # Task classification → tool selection
│   ├── aider.py        # Aider subprocess wrapper
│   ├── lm_studio.py    # Direct LM Studio OpenAI-compatible API calls
│   └── config.py       # Reads ~/.aider.conf.yml; shared endpoint config
├── pyproject.toml
└── README.md
```

### What it does NOT do

- Does not modify or touch the Roamin project
- Does not run inside Roamin's process
- Does not hook into Roamin's agent loop
- Does not require Roamin to be running
- Does not share config with Roamin
- Does not drive Cline or Continue (no API exists for that without a VS Code extension)

### Status

**Not yet built.** Phase 1 (installing and using the three tools individually) should be stable first. The orchestrator is only valuable once you know how each tool behaves on your specific hardware and model setup.

When ready, open a new spec: `developer-local-orchestrator/proposal.md`.
