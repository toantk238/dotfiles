# Stop Router Design

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Replace `stop_reviewer.py` with a unified `stop_router.py` that handles both "proceed?" detection and AI-assisted question answering.

---

## Problem

The current `stop_reviewer.py` only handles a narrow case: detecting "ready to proceed?" patterns and auto-replying "Proceed". It misses the broader case where Claude asks a clarifying question that the AI could answer automatically using the original user request as context.

---

## Goal

When Claude stops and its last message is a question, use an AI model to:
1. Extract the original user request from the session transcript
2. Determine if the question can be answered confidently (≥80% confidence) from that context
3. If yes → auto-answer and rewake Claude
4. If no → pass to human

---

## Architecture

Replace `stop_reviewer.py` with `stop_router.py`. Update `settings.json` hook command to point at the new file.

```
Stop event
  └─ stop_router.py
       ├─ guard: stop_hook_active? → exit 0
       ├─ read transcript → last assistant message + original user request
       ├─ danger_check(last_message) → if DANGER → exit 0
       ├─ classify_stop(message) → PROCEED | QUESTION | OTHER
       ├─ PROCEED  → proceed_handler(text)
       ├─ QUESTION → question_handler(text, original_request) [only if original_request is not None]
       └─ OTHER    → exit 0
```

DANGER_SIGNALS are checked **before** classification — if any danger signal is present, exit 0 unconditionally.

If classification returns QUESTION but `original_request` is None, exit 0 (no context to auto-answer with).

---

## Hook Input Format

The hook receives JSON on stdin:
```json
{
  "session_id": "<uuid>",
  "stop_hook_active": true
}
```

`stop_hook_active` is a field set to `true` by Claude Code when the current stop was triggered by a hook rewake (exit 2). Used for loop prevention.

---

## Loop Prevention Guard

At entry: `if hook_input.get("stop_hook_active"): sys.exit(0)`

---

## Transcript Location & Format

Session transcripts are stored as JSONL files at:
```
~/.claude/projects/*/{session_id}.jsonl
```

Use `glob.glob(pattern)` to find the file. If multiple files match, use `files[0]` (same behaviour as existing `stop_reviewer.py`).

Each line is a JSON object. The `message` key contains role and content:
```json
{
  "message": {
    "role": "assistant",
    "content": [{"type": "text", "text": "..."}]
  }
}
```

The `content` field may be either:
- A **list** of block dicts: `[{"type": "text", "text": "..."}, ...]` — extract text from blocks where `type == "text"`
- A **plain string**: treat the entire value as the text

Both forms must be handled. Join all text parts with a space and strip.

**`get_last_assistant_text(session_id)`**: walk lines in reverse, return text of the first assistant message with non-empty text content.

**`get_original_user_request(session_id)`**: walk lines from the beginning, return text of the first user message with non-empty text content.

---

## Signal Lists

### PROCEED_SIGNALS
Copied verbatim from `stop_reviewer.py`:
```python
PROCEED_SIGNALS = [
    "before i write the implementation plan",
    "before we move to the implementation plan",
    "let me know if you'd like any changes",
    "ready to proceed",
    "shall i proceed",
    "let me know if you want",
    "please review it before",
    "spec approved",
    "plan approved",
    "review complete",
    "would you like me to proceed",
    "let me know when you're ready",
    "if you'd like to proceed",
    "let me know if you want to make any changes",
    "let me know if you'd like to adjust",
    "any changes before i",
    "any adjustments before i",
]
```

### DANGER_SIGNALS
Copied verbatim from `stop_reviewer.py`:
```python
DANGER_SIGNALS = [
    "delete",
    "remove",
    "drop table",
    "production",
    "deploy to",
    "are you sure",
    "irreversible",
    "cannot be undone",
    "permanently",
    "force push",
    "reset --hard",
]
```

### QUESTION_SIGNALS
This is the final, complete list (no external source):
```python
QUESTION_SIGNALS = [
    "which option",
    "would you like",
    "do you want",
    "what would",
    "how would you",
    "which approach",
    "can you clarify",
]
```

---

## Classification Logic (`classify_stop`)

After danger check passes, check in order:

1. **PROCEED** — `any(sig in text.lower() for sig in PROCEED_SIGNALS)` → return `"PROCEED"`
2. **QUESTION** — `text.rstrip().endswith("?")` OR `any(sig in text.lower() for sig in QUESTION_SIGNALS)` → return `"QUESTION"`
3. **OTHER** — return `"OTHER"`

PROCEED is checked first: if a message matches both PROCEED and QUESTION, PROCEED takes priority.

---

## Proceed Handler (`proceed_handler`)

Behaviour copied from `stop_reviewer.py`'s `reviewer_decide` + response logic:

1. Call `reviewer_decide(text)` — a `claude -p` call that returns either a reply string or `"HUMAN_NEEDED"` (see subprocess details below)
2. If result is empty or `"HUMAN_NEEDED"` → `sys.exit(0)`
3. Otherwise → inject via `additionalContext` and `sys.exit(2)`

The injected context string:
```python
f'[stop_router] The developer\'s AI reviewer read your last message and responds: "{decision}". Please continue accordingly.'
```

The `reviewer_decide` prompt (copied from `stop_reviewer.py`):
```
You are an autonomous decision agent for a developer's coding assistant.
Claude has stopped and is waiting for a response. Decide the best action.

Claude's last message:
{text[:3000]}

Is this a simple "proceed to next step" situation (e.g. spec review done, plan ready, asking to continue)?
If yes, reply with the exact text the developer would type (usually just: Proceed).
If this requires human judgment (destructive action, unclear, important decision), reply with exactly: HUMAN_NEEDED

Reply with ONLY the response text or HUMAN_NEEDED.
```

---

## Question Handler (`question_handler`)

### AI Prompt

Full prompt sent to the model (caller has already confirmed `original_request` is not None):

```
You are an autonomous assistant helping a developer.

Original user request:
{original_request[:1000]}

Claude is now asking:
{question_text[:2000]}

Based ONLY on the original request, can you answer this question confidently?

Reply in this exact format:
CONFIDENCE: <integer 0-100>
ANSWER: <your answer text, or leave blank if confidence is below 80>

Rules:
- If CONFIDENCE >= 80, write a clear direct answer on the ANSWER line
- If CONFIDENCE < 80, leave the ANSWER line blank
- Never invent details not implied by the original request
- Keep answers concise (1-3 sentences max)
```

### Subprocess Invocation

```python
result = subprocess.run(
    ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001"],
    capture_output=True, text=True, timeout=20,
)
output = result.stdout.strip()
```

Stderr is not used for routing. If `subprocess.run` raises (e.g. `TimeoutExpired`, `FileNotFoundError`) → catch all exceptions → `sys.exit(0)`.

### Response Parsing

Parse `output` line by line:
- Find line starting with `"CONFIDENCE:"` → strip prefix, strip whitespace → parse as int
- Find line starting with `"ANSWER:"` → strip prefix, strip whitespace → answer text

**Parse failure cases** (all → `sys.exit(0)`):
- No line starting with `"CONFIDENCE:"` found
- Value after `"CONFIDENCE:"` is not a valid integer
- Parsed integer is outside range 0–100 (inclusive)
- Confidence ≥ 80 but no `"ANSWER:"` line found
- Confidence ≥ 80 but answer text after stripping whitespace is empty

### Response Injection

If confidence ≥ 80 and `answer.strip()` is non-empty:
```python
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "Stop",
        "additionalContext": (
            f'[stop_router] Auto-answered: "{answer}". Please continue accordingly.'
        )
    }
}))
sys.exit(2)  # asyncRewake
```

Otherwise: `sys.exit(0)`.

---

## Error Handling

| Failure Mode | Behavior |
|---|---|
| `stop_hook_active=True` | exit 0 (loop guard) |
| No transcript file found | exit 0 |
| No assistant text in transcript | exit 0 |
| Danger signal in last message | exit 0 |
| Classification returns OTHER | exit 0 |
| QUESTION but `original_request` is None | exit 0 |
| `subprocess.run` raises any exception | exit 0 |
| AI subprocess exits non-zero | exit 0 |
| No `CONFIDENCE:` line in output | exit 0 |
| `CONFIDENCE:` value not a valid integer | exit 0 |
| `CONFIDENCE:` value outside 0–100 | exit 0 |
| Confidence ≥ 80 but no `ANSWER:` line | exit 0 |
| Confidence ≥ 80 but answer is whitespace-only | exit 0 |

All decisions logged to `hooks.log` (via `logger.py`) with: stop type, confidence score, and outcome.

---

## File Changes

| File | Action |
|---|---|
| `.claude/hooks/stop_reviewer.py` | **Deleted** |
| `.claude/hooks/stop_router.py` | **New** — unified router |
| `.claude/settings.json` | Hook command updated (see below) |

### `settings.json` Hook Command Change

**Before:**
```json
"command": "zsh -c \"source ~/.env.zsh; ~/.claude/hooks/.venv/bin/python ~/.claude/hooks/stop_reviewer.py\""
```

**After:**
```json
"command": "zsh -c \"source ~/.env.zsh; ~/.claude/hooks/.venv/bin/python ~/.claude/hooks/stop_router.py\""
```

---

## Non-Goals

- Does not change `pre_tool_reviewer.py`
- Does not add cross-session memory or persistent context
- Uses Haiku only (keep latency low, ≤20s timeout)
