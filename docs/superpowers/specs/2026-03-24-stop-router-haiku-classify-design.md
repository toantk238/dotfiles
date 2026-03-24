# stop_router: AI-based stop_type classification via Haiku

**Date:** 2026-03-24
**Status:** Approved

## Summary

Replace the keyword-based `classify_stop(text)` function in `stop_router.py` with `classify_stop_ai(text)`, which calls Haiku to classify each stop event as `PROCEED`, `QUESTION`, or `OTHER`. The routing logic in `main()` is unchanged.

## Motivation

The current `classify_stop` relies on hard-coded keyword lists (`PROCEED_SIGNALS`, `QUESTION_SIGNALS`). These miss cases where phrasing is unexpected or doesn't match any listed signal. Haiku can reason about the intent of any message without brittle string matching.

## Changes

### `stop_router.py`

**Delete:**
- `PROCEED_SIGNALS` list
- `QUESTION_SIGNALS` list
- `classify_stop(text: str) -> str`

**Add:**
- `classify_stop_ai(text: str) -> str`
  - Calls `claude -p <prompt> --model claude-haiku-4-5-20251001` via `subprocess.run`
  - Timeout: 20s (matches existing Haiku calls)
  - Prompt instructs Haiku to reply with exactly one word: `PROCEED`, `QUESTION`, or `OTHER`
  - Strips and upper-cases the response
  - Returns `"OTHER"` on: non-zero exit, subprocess exception, timeout, or unrecognised response

**Unchanged:**
- `DANGER_SIGNALS` and `has_danger_signal` — cheap keyword check, runs before classification
- `proceed_handler`, `question_handler`, `_reviewer_decide` — no changes
- `main()` — calls `classify_stop_ai` in place of `classify_stop`, otherwise identical

### Haiku prompt

```
You are a routing agent for a developer's coding assistant stop hook.
Read the assistant's last message below and classify it as one of:
  PROCEED  — the assistant is ready to move forward and waiting for approval or a "proceed" signal
  QUESTION — the assistant is asking the developer a question that needs an answer
  OTHER    — anything else (summary, status update, error, etc.)

Reply with exactly one word: PROCEED, QUESTION, or OTHER.

Message:
{text[:3000]}
```

## Testing

### Deleted tests (keyword-based, no longer valid)
- `test_classify_proceed_signal`
- `test_classify_proceed_priority_over_question`
- `test_classify_question_ends_with_question_mark`
- `test_classify_question_signal`
- `test_classify_other`
- `test_classify_danger_check_not_in_classify`

### New tests for `classify_stop_ai`
| Test | Mock | Expected |
|---|---|---|
| `test_classify_stop_ai_returns_proceed` | stdout=`"PROCEED"`, rc=0 | `"PROCEED"` |
| `test_classify_stop_ai_returns_question` | stdout=`"QUESTION"`, rc=0 | `"QUESTION"` |
| `test_classify_stop_ai_returns_other` | stdout=`"OTHER"`, rc=0 | `"OTHER"` |
| `test_classify_stop_ai_unknown_response_returns_other` | stdout=`"BANANA"`, rc=0 | `"OTHER"` |
| `test_classify_stop_ai_subprocess_exception_returns_other` | raises `Exception` | `"OTHER"` |
| `test_classify_stop_ai_nonzero_exit_returns_other` | rc=1 | `"OTHER"` |

### Unchanged integration tests
`test_main_*` tests in `test_stop_router.py` mock `subprocess.run` and drive routing via transcript content — they continue to work without modification.

## Error handling

All failure modes for `classify_stop_ai` return `"OTHER"`, which causes `main()` to `sys.exit(0)` — passing control to the human. This is the safe default.

## Out of scope

- Keeping keyword lists as a fallback
- Logging the Haiku classification reason
- Changes to `proceed_handler` or `question_handler`
