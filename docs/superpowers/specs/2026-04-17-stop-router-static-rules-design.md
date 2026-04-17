# stop_router: Static Rules Short-Circuit

**Date:** 2026-04-17
**File:** `.claude_custom/hooks/stop_router.py`

## Problem

`handle_stop()` always invokes the LLM, even for deterministic patterns like the writing-plans "which approach?" prompt. This wastes ~1-2s and a Haiku API call on a decision that can be made by code.

## Solution

Add a `check_static_rules(last_text: str) -> str | None` function that runs before the LLM call. If a known pattern matches, it returns the inject-context string directly. `handle_stop()` exits with code 2 immediately, skipping the LLM entirely.

## Pattern: Plan Selection Prompt

**Trigger:** All 4 terms present in `last_text` (case-sensitive substring):

1. `"Plan complete and saved"`
2. `"Subagent-Driven"`
3. `"Inline Execution"`
4. `"Which approach?"`

**Action:** Auto-select Option 1 (Subagent-Driven).

**Injected context:**
```
[stop_router] Auto-answered: "Option 1: Subagent-Driven". Please continue accordingly.
```

## Architecture

### `check_static_rules(last_text: str) -> str | None`

```python
_PLAN_SELECTION_TERMS = [
    "Plan complete and saved",
    "Subagent-Driven",
    "Inline Execution",
    "Which approach?",
]

def check_static_rules(last_text: str) -> str | None:
    if all(term in last_text for term in _PLAN_SELECTION_TERMS):
        return '[stop_router] Auto-answered: "Option 1: Subagent-Driven". Please continue accordingly.'
    return None
```

### Modified `handle_stop()`

```python
def handle_stop(last_text, original_request):
    static_context = check_static_rules(last_text)
    if static_context:
        logger.info("Static rule matched: subagent-driven plan selection")
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": static_context,
            }
        }))
        sys.exit(2)

    # existing LLM path unchanged below
    ...
```

## Tests

In `tests/test_stop_router.py`:

- `test_static_rule_plan_selection_matches`: all 4 terms present → `check_static_rules` returns the context string
- `test_static_rule_missing_term`: one term absent → returns `None`
- `test_handle_stop_static_rule_exits_2`: full `handle_stop()` with matching text → exits 2, context contains "Subagent-Driven", LLM not called
