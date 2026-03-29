# stop_router: AI-based stop_type classification via Haiku

**Date:** 2026-03-24
**Status:** Approved

## Summary

Replace the keyword-based `classify_stop(text)` function in `stop_router.py` with `classify_stop_ai(text)`, which calls Haiku to classify each stop event as `PROCEED`, `QUESTION`, or `OTHER`. The routing logic in `main()` is unchanged.

## Motivation

The current `classify_stop` relies on hard-coded keyword lists (`PROCEED_SIGNALS`, `QUESTION_SIGNALS`). These miss cases where phrasing is unexpected or doesn't match any listed signal. Haiku can reason about the intent of any message without brittle string matching.

## Changes

### `stop_router.py`

**Delete** `PROCEED_SIGNALS` and `QUESTION_SIGNALS`; `DANGER_SIGNALS` is kept because `has_danger_signal` still depends on it.

**Delete** `classify_stop(text: str) -> str`.

**Add** `classify_stop_ai(text: str) -> str`:
- Calls `claude -p <prompt> --model claude-haiku-4-5-20251001` via `subprocess.run`, timeout=20s (matches existing Haiku calls)
- Strips and upper-cases the response; if not one of `PROCEED`, `QUESTION`, `OTHER` → returns `"OTHER"`
- A single `except Exception` handler is sufficient for all failure modes including `subprocess.TimeoutExpired` (which is a subclass of `Exception`) — on any exception, returns `"OTHER"`
- Non-zero `returncode` → returns `"OTHER"`

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
{last_text truncated to 3000 characters}  ← f-string: text[:3000]
```

## Testing

### Deleted tests (keyword-based, no longer valid)
- `test_classify_proceed_signal`
- `test_classify_proceed_priority_over_question`
- `test_classify_question_ends_with_question_mark`
- `test_classify_question_signal`
- `test_classify_other`

### Carried-forward test (renamed)
`test_classify_danger_check_not_in_classify` → `test_classify_stop_ai_danger_check_not_in_classify`

This test encodes an architectural invariant — that `classify_stop_ai` does not check danger signals; the caller (`main()`) is responsible for that. The invariant still holds; only the function name changes.

### New tests for `classify_stop_ai`

All subprocess mocks use the existing `_make_proc(stdout, returncode)` helper.
Exception tests use `side_effect=Exception("boom")` (or `side_effect=subprocess.TimeoutExpired(cmd=[], timeout=20)` for the timeout case).

| Test | Mock | Expected |
|---|---|---|
| `test_classify_stop_ai_returns_proceed` | `_make_proc("PROCEED")`, rc=0 | `"PROCEED"` |
| `test_classify_stop_ai_returns_question` | `_make_proc("QUESTION")`, rc=0 | `"QUESTION"` |
| `test_classify_stop_ai_returns_other` | `_make_proc("OTHER")`, rc=0 | `"OTHER"` |
| `test_classify_stop_ai_unknown_response_returns_other` | `_make_proc("BANANA")`, rc=0 | `"OTHER"` |
| `test_classify_stop_ai_subprocess_exception_returns_other` | `side_effect=Exception("boom")` | `"OTHER"` |
| `test_classify_stop_ai_timeout_returns_other` | `side_effect=subprocess.TimeoutExpired(cmd=[], timeout=20)` | `"OTHER"` |
| `test_classify_stop_ai_nonzero_exit_returns_other` | `_make_proc("", returncode=1)` | `"OTHER"` |
| `test_classify_stop_ai_danger_check_not_in_classify` | `_make_proc("PROCEED")`, rc=0 | `"PROCEED"` (dangerous text still classifies as PROCEED — caller checks danger separately) |

### Updated integration tests

`test_main_proceed_calls_proceed_handler` and `test_main_question_with_context_calls_question_handler` **must be updated**. After this change, `main()` calls `classify_stop_ai` (which uses `subprocess.run`) before the handler, meaning a single `subprocess.run` mock is consumed by the classifier before the handler call.

Fix: patch `classify_stop_ai` directly in these tests:
```python
with patch("stop_router.classify_stop_ai", return_value="PROCEED"):
    with patch("stop_router.subprocess.run", return_value=_make_proc("Proceed")):
        ...
```

`test_main_other_classification_exits_0` also needs updating for the same reason — patch `classify_stop_ai` to return `"OTHER"` directly rather than relying on transcript text to drive keyword matching.

`test_main_danger_signal_exits_0` and `test_main_stop_hook_active_exits_0` are unaffected (they exit before classification).

## Error handling

All failure modes for `classify_stop_ai` return `"OTHER"`, causing `main()` to `sys.exit(0)` — passing control to the human. This is the safe default.

## Out of scope

- Keeping keyword lists as a fallback
- Logging the Haiku classification reason
- Changes to `proceed_handler` or `question_handler`
