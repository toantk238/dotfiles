# Stop Hook: Transcript-First Design

**Date:** 2026-04-16  
**Status:** Approved

## Problem Statement

Two bugs cause the stop hook to fail at auto-answering:

1. **Truncated last message.** Claude Code truncates the `last_assistant_message` field in the Stop hook payload when the assistant's response is long. Key phrases like "Shall I proceed?" or "Subagent-Driven" appear at the *end* of long messages, so they are lost in truncation, causing the hook to fall back to `HUMAN_NEEDED`.

2. **Original request not found for nested sessions.** Every tool use fires `pre_tool_reviewer`, which calls `call_claude()`, which spawns a `claude --print --no-session-persistence` sub-session. That sub-session also fires the Stop hook. Since `--no-session-persistence` produces no transcript, `get_original_user_request` always returns `None` for these sessions, flooding the log with "Early exit: original_request not found" and occasionally preventing the main session from auto-answering.

Additionally, re-woken stops (`stop_hook_active=True`) were only handling the specific "Subagent-Driven / Inline Execution" check — they should go through the full PROCEED/ANSWER/HUMAN_NEEDED decision path like any other stop.

## Chosen Approach: Transcript-First

Use `transcript_path` from the hook payload as the single source of truth for both message retrieval and session identity. All hook event types (PostToolUse, UserPromptSubmit, Stop) include this field. Nested `--no-session-persistence` sessions have no transcript file, so a simple existence check distinguishes them from real sessions.

## Architecture

### `common.py` changes

**`read_transcript(transcript_path: str)`**  
Signature changes from `(session_id, glob_template)` to `(transcript_path: str)`. Reads the JSONL file at the given path, yields parsed dicts. Returns immediately if the file doesn't exist.

**`get_original_user_request(transcript_path: str) -> str | None`**  
Same logic as today — find the first `role == "user"` entry and extract its text — but takes `transcript_path` directly instead of `session_id` + glob. No more `os.path.expanduser` or `glob.glob`.

**`get_last_assistant_message(transcript_path: str) -> str | None`**  
New function. Scans all JSONL entries, returns the text content of the last `role == "assistant"` entry using the existing `extract_text` helper. Returns `None` if no assistant entry exists yet.

### `stop_router.py` changes

**Early exit for nested sessions (top of `main()`):**
```python
transcript_path = hook_input.get("transcript_path", "")
if not transcript_path or not os.path.exists(transcript_path):
    logger.debug("Early exit: no transcript (nested session)")
    sys.exit(0)
```
This replaces the noisy "original_request not found" path. No log noise for pre_tool_reviewer sub-sessions.

**Full last message from transcript:**
```python
last_text = get_last_assistant_message(transcript_path)
if not last_text:
    last_text = hook_input.get("last_assistant_message", "")
if not last_text:
    logger.info("Early exit: no last_text found")
    sys.exit(0)
```
Fallback chain: transcript (full) → hook payload field (truncated) → exit.

**Remove `stop_hook_active` special-case gate:**  
Delete the block that only handles "subagent-driven/inline execution" keywords when `stop_hook_active=True`. Re-woken stops go through the same full `handle_stop()` path. The session still needs a valid transcript and original request.

**`original_request` lookup:**
```python
original_request = get_original_user_request(transcript_path)
if not original_request:
    logger.info("Early exit: no original_request in transcript")
    sys.exit(0)
```

### Data flow

```
Stop hook fires
  └── transcript_path present and file exists?
        NO  → exit 0 (nested session, no noise)
        YES → get_last_assistant_message(transcript_path)
                └── fallback: hook_input["last_assistant_message"]
                └── empty? → exit 0
              get_original_user_request(transcript_path)
                └── None? → exit 0
              handle_stop(last_text, original_request)
                └── call_claude(prompt)
                      PROCEED  → exit 2 with additionalContext
                      ANSWER   → exit 2 with additionalContext
                      HUMAN_NEEDED → exit 0
```

## Test Updates (`test_stop_router.py`)

- `_write_transcript` returns a `transcript_path` string; mock the path directly instead of patching `glob`/`expanduser`
- `_run_main` passes `transcript_path` in `hook_input` instead of `session_id`
- **New test:** `stop_hook_active=True` + "Shall I proceed?" message → should PROCEED (was previously gated out)
- **New test:** `transcript_path` absent in hook_input → exits 0 (nested session guard)
- **New test:** `transcript_path` present but file doesn't exist → exits 0 (nested session guard)
- **New test:** transcript has a long assistant message; `last_assistant_message` in payload is a truncated version → full transcript text is used

## Out of Scope

- Changes to `pre_tool_reviewer.py` — its behavior is unchanged; nested sessions are now filtered silently
- Changes to the LLM prompt in `STOP_PROMPT_TEMPLATE`
- Changes to `handle_stop` or `parse_llm_output`
