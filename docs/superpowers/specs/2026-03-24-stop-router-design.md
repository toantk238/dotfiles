# Stop Router Design

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Replace `stop_reviewer.py` with a unified `stop_router.py` that handles both "proceed?" detection and AI-assisted question answering.

---

## Problem

The current `stop_reviewer.py` only handles a narrow case: detecting "ready to proceed?" patterns and auto-replying "Proceed". It misses the broader case where Claude (e.g. during a superpowers brainstorming session) asks a clarifying question that the AI could answer automatically using the original user request as context.

---

## Goal

When Claude stops and its last message is a question, use an AI model to:
1. Extract the original user request from the session transcript
2. Determine if the question can be answered confidently (≥80% confidence) from that context
3. If yes → auto-answer and rewake Claude
4. If no → pass to human

---

## Architecture

Replace `stop_reviewer.py` with `stop_router.py`. Update `settings.json` to point at the new file.

```
Stop event
  └─ stop_router.py
       ├─ guard: stop_hook_active? → exit 0
       ├─ read transcript → last assistant message + original user request
       ├─ classify_stop(message) → PROCEED | QUESTION | OTHER
       ├─ PROCEED  → proceed_handler (existing PROCEED_SIGNALS + DANGER_SIGNALS logic)
       ├─ QUESTION → question_handler (AI confidence check → auto-answer or exit 0)
       └─ OTHER    → exit 0
```

---

## Components

### `stop_router.py`

Single entry point replacing `stop_reviewer.py`. Contains:

- `classify_stop(text) -> Literal["PROCEED", "QUESTION", "OTHER"]`
- `get_last_assistant_text(session_id) -> str | None` (unchanged from current)
- `get_original_user_request(session_id) -> str | None` (new — reads first meaningful user message)
- `proceed_handler(text) -> None` (extracted from current `stop_reviewer.py`)
- `question_handler(question_text, original_request) -> None` (new)
- `main()` — router entry point

### Classification Logic (`classify_stop`)

Two-pass, no AI call:

1. **PROCEED** — any `PROCEED_SIGNALS` keyword matches (existing list preserved)
2. **QUESTION** — message ends with `?` OR contains any of: `which option`, `would you like`, `do you want`, `what would`, `how would you`, `which approach`, `can you clarify`
3. **OTHER** — neither → exit 0

DANGER_SIGNALS gate applied inside both handlers — if triggered, always exit 0 (human decides).

### Original User Request Extraction

Walk transcript from the beginning. Find the first `user` role message with non-empty text. Used as context for the question handler.

### Question Handler AI Prompt

Calls `claude -p` with `claude-haiku-4-5-20251001`:

```
You are an autonomous assistant helping a developer.

Original user request:
{original_request[:1000]}

Claude is now asking:
{question_text[:2000]}

Based ONLY on the original request, can you answer this question confidently?

Reply in this exact format:
CONFIDENCE: <0-100>
ANSWER: <your answer, or blank if low confidence>

Rules:
- CONFIDENCE >= 80: provide a clear, direct answer
- CONFIDENCE < 80: leave ANSWER blank
- Never invent details not implied by the original request
- Keep answers concise (1-3 sentences max)
```

### Response Injection

If confidence ≥ 80 and answer is non-empty:

```python
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "Stop",
        "additionalContext": f'[stop_router] Auto-answered: "{answer}"'
    }
}))
sys.exit(2)  # asyncRewake
```

Otherwise: `sys.exit(0)` — human answers.

---

## Error Handling

| Failure Mode | Behavior |
|---|---|
| `stop_hook_active=True` | exit 0 (loop guard) |
| No transcript found | exit 0 |
| AI call fails / timeout | exit 0 (safe fallback) |
| Unparseable AI output | exit 0 |
| Danger signal present | exit 0 (human decides) |

All decisions logged to `hooks.log` with: stop type, confidence score, outcome.

---

## File Changes

| File | Action |
|---|---|
| `.claude/hooks/stop_reviewer.py` | Renamed/replaced by `stop_router.py` |
| `.claude/hooks/stop_router.py` | New unified router |
| `.claude/settings.json` | Hook command updated to `stop_router.py` |

---

## Non-Goals

- Does not change `pre_tool_reviewer.py`
- Does not add memory or cross-session context
- Does not use a model larger than Haiku (keep latency low)
