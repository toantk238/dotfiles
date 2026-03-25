# pre_tool_reviewer: fix BLOCKED reason extraction and message format

**Date:** 2026-03-25
**Status:** Approved

## Summary

Fix two bugs in `pre_tool_reviewer.py`: (1) reason extraction that produces empty or incorrect strings when Haiku's verdict lacks a colon, and (2) a raw JSON error message that is unreadable when shown to Claude.

## Motivation

When the hook blocks a tool call, Claude receives `{"reason": ""}` — raw JSON with an empty reason. This is both machine-formatted (not natural language) and uninformative. The root cause is a fragile string replace that silently fails when Haiku returns `BLOCK` without a `: <reason>` suffix.

## Bugs

### Bug 1 — Fragile reason extraction (line 42)

```python
# Current
reason = verdict.replace("BLOCK:", "").strip() if not approved else ""
```

Failure modes:
- Haiku returns `BLOCK` (no colon) → `reason = "BLOCK"` (the replace has no effect)
- Haiku returns `BLOCK: ` (colon, empty after) → `reason = ""`

### Bug 2 — Raw JSON message (line 58)

```python
# Current
print(json.dumps({"reason": reason}), file=sys.stderr)
```

Claude sees: `{"reason": ""}` — a JSON object, not a sentence. When reason is also empty, the message is entirely uninformative.

## Changes

### `pre_tool_reviewer.py`

**Fix 1 — reason extraction** in `review()`:

```python
if not approved:
    reason = verdict.split(":", 1)[1].strip() if ":" in verdict else ""
    if not reason:
        reason = "no reason provided"
else:
    reason = ""
```

- `split(":", 1)` correctly handles `BLOCK: rm -rf on system paths` → `"rm -rf on system paths"`
- When no colon is present, reason defaults to `""` then falls through to the `"no reason provided"` fallback
- The fallback ensures reason is never empty when blocked

**Fix 2 — message format** in `main()`:

```python
print(f"Tool '{tool_name}' blocked by pre_tool_reviewer.\nReason: {reason}", file=sys.stderr)
```

Claude sees:
```
Tool 'Bash' blocked by pre_tool_reviewer.
Reason: rm -rf on system paths
```

`tool_name` is already in scope in `main()`. No signature changes needed.

## What is unchanged

- `review()` return type: `tuple[bool, str]`
- `logger.warning(...)` call — still logs `tool_name` and `reason`
- Exit codes: 0 for approved, 2 for blocked
- The Haiku model, prompt, timeout, and subprocess invocation

## Testing

No automated tests exist for this file. Manual verification:

1. Trigger a block by asking Claude to run a destructive command (e.g. `rm -rf /tmp/testdir`)
2. Confirm Claude receives: `Tool 'Bash' blocked by pre_tool_reviewer.\nReason: <non-empty reason>`
3. Confirm no `{"reason": ...}` JSON appears in the block message

## Out of scope

- Adding automated tests for `pre_tool_reviewer.py`
- Changing the Haiku prompt or verdict format
- Changing approval/denial logic
