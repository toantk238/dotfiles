# pre_tool_reviewer: fix BLOCKED reason extraction and message format

**Date:** 2026-03-25
**Status:** Draft

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
- When no colon is present, `reason` is set to `""`, which is then caught by `if not reason:` and replaced with the fallback. (This is not Python fall-through; the `if not reason:` guard is an explicit check on the empty string.)
- The fallback ensures reason is never empty when blocked

**Note on fallback wording:** A bare `BLOCK` with no colon means Haiku did not follow the `BLOCK: <reason>` prompt format — it is a prompt non-compliance case. The fallback `"no reason provided"` is an intentional choice that favours human-readable output over diagnostic transparency. An implementer who prefers diagnosability may use `"(model returned BLOCK without explanation)"` instead, but this spec uses the simpler form.

**Fix 2 — message format** in `main()`:

```python
print(f"Tool '{tool_name}' blocked by pre_tool_reviewer.\nReason: {reason}", file=sys.stderr)
```

Claude sees:
```
Tool 'Bash' blocked by pre_tool_reviewer.
Reason: rm -rf on system paths
```

`tool_name` is in scope in `main()` — assigned at line 48, used at line 58.

**Fix 3 — log the raw verdict** in `main()`:

Update `logger.warning` to include the raw `verdict` alongside `reason`, so that when the fallback fires, the original Haiku output is not silently discarded:

```python
logger.warning("BLOCKED   tool=%s reason=%s verdict=%s", tool_name, reason, verdict)
```

`verdict` must be returned from `review()` alongside `approved` and `reason`, or stored as a module-level variable. The cleanest approach is to change `review()` to return `tuple[bool, str, str]` — `(approved, reason, verdict)` — so `main()` can log all three.

## What is unchanged

- `review()` prompt, Haiku model, subprocess invocation, and timeout
- Exit codes: 0 for approved, 2 for blocked
- The `json` import remains necessary: `review()` uses `json.dumps` (to serialise `tool_input`) and `main()` uses `json.load` (to read stdin). Do not remove it when removing `json.dumps` from the block path.

## What changes in the function signature

`review()` changes from `tuple[bool, str]` to `tuple[bool, str, str]`:

```python
def review(tool_name: str, tool_input: dict) -> tuple[bool, str, str]:
    ...
    return approved, reason, verdict
```

`main()` unpacks accordingly:

```python
approved, reason, verdict = review(tool_name, tool_input)
```

## Testing

No automated tests exist for this file. Manual verification:

1. Trigger a block by asking Claude to run a destructive command (e.g. `rm -rf /tmp/testdir`)
2. Confirm Claude receives: `Tool 'Bash' blocked by pre_tool_reviewer.\nReason: <non-empty reason>`
3. Confirm no `{"reason": ...}` JSON appears in the block message
4. Confirm the log line contains both `reason` and `verdict`

## Out of scope

- Adding automated tests for `pre_tool_reviewer.py`
- Changing the Haiku prompt or verdict format
- Changing approval/denial logic
