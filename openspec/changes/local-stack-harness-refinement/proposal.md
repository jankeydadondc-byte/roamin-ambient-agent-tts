# Local Stack Harness Refinement

**Date:** 2026-04-25
**Status:** PROPOSED
**Goal:** Extend the Cline/Aider/Continue rule files beyond project constraints into
behavioral, operational, security, and design discipline — drawing from GPT-5 Codex,
Cursor IDE, and the official Anthropic Claude Code plugin repository as reference,
adapted for Roamin's local LLM stack.

---

## Background

The `local-tool-ai-rules` spec established the harness: `.clinerules`,
`.aider.rules.md`, and `.continuerc.json` give each tool project context, git
constraints, terminal rules, and off-limits directory guards.

What was missing: *how* the AI tools should work, not just what they shouldn't touch.
Local LLMs (via LM Studio) are significantly more prone to sycophancy, verbosity,
over-planning, and insecure code generation than hosted models — behavioral and
security guardrails matter more here, not less.

This spec adds four new rule categories to all harness files:

1. **Behavior** — operational discipline (implement vs. plan, clarification protocol,
   no fluff, review format with confidence filtering)
2. **Security** — dangerous pattern awareness for Python and React code
3. **Frontend** — UI discipline with full design direction for new components
4. **Git safety extensions** — rules that complement no-auto-commit

---

## Source Material

| Source | Location | Key takeaways |
|---|---|---|
| OpenAI GPT-5 Codex | `openai-chatgpt5-codex_20260325.md` (leaked-system-prompts) | Action bias, no fluff, review format, dirty worktree, linter loop limit, parallelize, frontend design direction |
| Cursor IDE Agent | `cursor-ide-agent-claude-sonnet-3.7_20250309.md` (leaked-system-prompts) | Read before edit, group edits per file, stop-and-ask on conflicts, linter loop limit |
| Anthropic Claude Code plugins | `anthropics/claude-code` (official repo) | Code review confidence scoring, security hook patterns, frontend SKILL.md, feature-dev clarification protocol |

**Note on the "leaked" Claude Code harness:** The `claude-code-output-style-default`
file in leaked-system-prompts has a `null` prompt — there is no hidden harness there.
The real structure is in Anthropic's official plugin repository, which is public.

---

## New Rules by Category

### Behavior

The key tension resolved in this spec: Codex says "implement, don't plan" while the
official Claude Code `feature-dev` plugin marks the clarification phase as
`CRITICAL: DO NOT SKIP`. Both are right in different contexts.

**Resolution:** simple/clear task → implement immediately. Ambiguous/large feature →
ask specific clarifying questions first, wait for answers, then implement.

Full behavior ruleset:

| Rule | Source | Rationale |
|---|---|---|
| Simple tasks: implement immediately. Ambiguous/large: clarify first, then implement | Codex + Claude Code feature-dev | Resolves the plan-vs-act tension correctly |
| No cheerleading, filler, or acknowledgement openers | Codex | Local LLMs are especially sycophantic |
| Code review: high-confidence issues only — cite exactly why it is wrong; false positives erode trust | Claude Code code-reviewer | Confidence ≥80 filter; prevents noise that buries real findings |
| Code review: bugs/risks first, severity-ordered with file:line refs; summaries follow | Codex + Claude Code | Structure that makes findings actionable |
| Read file before editing; group all edits per file into one pass | Cursor | Prevents partial edits and context-blind overwrites |
| Max 3 attempts on same linter error — then stop and ask | Cursor | Prevents runaway fix loops common with weaker local models |
| Working tree conflict with task → stop and ask; unrelated files → ignore | Codex + Cursor | Protects in-progress work |
| Parallelize independent reads and searches | Codex | Throughput improvement for Cline |
| Do not output code in chat unless explicitly asked (Cline only) | Cursor | Apply changes via edit tools, not chat |

### Security

Sourced from the official Anthropic Claude Code `security-guidance` plugin, which
ships as a pre-tool hook that blocks edits containing dangerous patterns. Adapted
as awareness rules for our harness (we don't run hooks in the local stack).

Patterns that must be flagged before proceeding:

| Pattern | Risk | Safer alternative |
|---|---|---|
| `eval()`, `new Function()` | Code injection | Redesign to avoid dynamic code evaluation |
| `os.system()` | Shell injection | `subprocess.run()` with argument list |
| `pickle` on untrusted data | Arbitrary code execution | JSON or another safe format |
| `.innerHTML =` or `dangerouslySetInnerHTML` with untrusted content | XSS | `textContent` or DOMPurify |
| `document.write()` | XSS + performance | DOM methods (createElement, appendChild) |

If any of these is genuinely required, the AI must flag it explicitly and wait for
the user to decide — not silently write the dangerous pattern.

### Frontend

Roamin has two React UIs:
- `ui/control-panel` — React/Vite monitoring and control dashboard
- `ui/roamin-chat` — Tauri-based chat app (Chat, ArtifactsPanel, ThinkingBlock,
  TokenBar, ToolStatus, VolumeControl, SessionSidebar, ModelSidebar, SearchBar,
  SettingsPanel, AgentPicker, ContextPicker, PermissionToggle, ProjectPicker,
  ToolPicker)

**Two-mode frontend rule:**

*Mode 1 — Working within existing UI:* Preserve the established visual patterns,
structure, and style. Do not redesign what is already there.

*Mode 2 — New components with no existing reference:* Apply the full design direction
sourced from Anthropic's official `frontend-design` SKILL.md:

| Dimension | Rule |
|---|---|
| Direction | Choose one clear aesthetic before writing code. Commit to it. Intentional minimalism and bold maximalism both work — the failure mode is neither. |
| Typography | Choose distinctive fonts. Never use Inter, Roboto, Arial, or system-ui. Pair a display font with a refined body font. |
| Color | CSS variables for all values. Dominant colors with sharp accents outperform even palettes. Avoid purple gradients on white. |
| Motion | One well-orchestrated page-load with staggered reveals beats scattered micro-interactions. Use the Motion library for React. |
| Layout | Asymmetry, overlap, diagonal flow, grid-breaking elements over centered boxes. |
| React patterns | Use startTransition, useDeferredValue where appropriate. Never add useMemo/useCallback by default. |

**Why the full design direction now (vs. just CSS variables before):**
The Anthropic SKILL.md is the more authoritative and detailed source. The Codex
guidelines were directionally correct but thin. The SKILL.md makes the "avoid AI slop"
rule actionable with specific, concrete choices to make (typography pairing, motion
approach, layout philosophy).

### Git Safety Extensions

| Rule | Why |
|---|---|
| Never amend a commit unless explicitly asked | Prevents silent history rewrite |
| Never use destructive git commands unless explicitly asked | Prevents accidental work loss |
| Never revert or discard changes you did not make | Protects dirty worktree state |
| Always prefer non-interactive git commands | Avoids terminal hang in Aider |

---

## File Changes

### `.clinerules`
- `## Behavior` — implement-vs-clarify protocol, no-fluff, confidence-filtered review,
  edit discipline, linter loop limit, worktree conflict handling, parallelization,
  no code-in-chat
- `## Security` — 5 dangerous pattern rules with safer alternatives
- `## Frontend` — two-mode rule: preserve existing / full design direction for new
- `## Git` extended — amend, destructive command, dirty worktree rules

### `.aider.rules.md`
- Same as `.clinerules` minus the no-code-in-chat rule (not applicable to Aider's
  file-edit workflow)

### `.continuerc.json`
- `systemMessage` rewritten as structured multi-paragraph string covering all four
  categories in condensed form
- `mergeBehavior: merge` unchanged

---

## What This Does NOT Do

- Does not change how any tool connects to LM Studio
- Does not affect model selection, context window, or temperature
- Does not affect Roamin's runtime — these are developer tooling files only
- Does not implement the security hook as actual tooling — that is a future Claude
  Code hooks integration, not a harness rule file

---

## Installation Checklist

- [x] Update `.clinerules` with all four new sections
- [x] Update `.aider.rules.md` with all four new sections
- [x] Update `.continuerc.json` systemMessage with all categories

### Verification

| Tool | Test |
|---|---|
| Cline | Ask: "Add a login button to the chat UI" (clear task) → should implement, not plan |
| Cline | Ask: "Build a new notification system" (ambiguous) → should ask clarifying questions first |
| Cline | Ask: "Review this file" → should list only high-confidence bugs with file:line refs before any summary |
| Cline | Write `eval(user_input)` in a file → should flag it and refuse to proceed silently |
| Aider | Same review and security tests — same behavior expected |
| Continue | Ask: "What do I do with a linter error that keeps failing?" → should say stop after 3 attempts and ask |
