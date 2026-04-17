# stop_router: Multi-line ANSWER Parsing + Debug Logging

**Date:** 2026-04-17
**File:** `.claude_custom/hooks/stop_router.py`

## Problem

`parse_llm_output()` only reads the answer value from the **same line** as `ANSWER:`. When the LLM puts its answer on the next line (which happens with longer responses), `answer` is parsed as `""`. The `handle_stop()` condition `decision.action == "ANSWER" and decision.answer` then evaluates as False, silently falling through to `sys.exit(0)` with no visible feedback — even though the LLM intended to auto-answer.

Additionally, there is no debug logging of the raw LLM response, making these parsing failures invisible until the user notices missing hook feedback.

## Solution

### 1. Multi-line ANSWER parsing in `parse_llm_output()`

Use a simple state machine. Once a line starting with `ANSWER:` is seen, collect the inline value (if any) and all subsequent non-empty lines until EOF. Join with a single space.

```python
def parse_llm_output(output: str) -> StopDecision:
    logger.debug(f"LLM raw output:\n{output}")
    action = "HUMAN_NEEDED"
    answer_lines = []
    in_answer = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ACTION:"):
            action = stripped[len("ACTION:"):].strip().upper()
            in_answer = False
        elif stripped.startswith("ANSWER:"):
            answer_lines = [stripped[len("ANSWER:"):].strip()]
            in_answer = True
        elif in_answer and stripped:
            answer_lines.append(stripped)
    answer = " ".join(answer_lines).strip()
    logger.debug(f"Parsed → action={action} answer={answer!r}")
    return StopDecision(action=action, answer=answer)
```

**Behavior table:**

| LLM output | Before | After |
|---|---|---|
| `ANSWER: Option A` | `"Option A"` ✅ | `"Option A"` ✅ |
| `ANSWER:\nOption A` | `""` ❌ | `"Option A"` ✅ |
| `ANSWER:\nLine 1\nLine 2` | `""` ❌ | `"Line 1 Line 2"` ✅ |
| `ANSWER:` (empty, no following content) | `""` ✅ | `""` ✅ |

### 2. Debug logging

Two `logger.debug()` calls added inside `parse_llm_output()`:

- **Before parsing:** raw LLM output — shows exactly what the model returned
- **After parsing:** `action` and `answer` with `repr()` — makes `""` vs `"text"` unambiguous in logs

## Tests

In `tests/test_stop_router.py`, add alongside existing parse tests:

- `test_parse_llm_output_answer_next_line` — `ANSWER:` on one line, value on next → captured correctly
- `test_parse_llm_output_answer_multiline` — value spans 2 lines → joined with a single space
- Existing `test_parse_llm_output_answer` (inline value) — must still pass unchanged
- Existing `test_parse_llm_output_garbage` — must still return `HUMAN_NEEDED` with `answer=""`
