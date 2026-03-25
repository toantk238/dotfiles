# pre_tool_reviewer Block Message Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two bugs in `pre_tool_reviewer.py` so that blocked tool calls show a clear, human-readable reason to Claude instead of raw JSON with an empty string.

**Architecture:** All changes are in a single file (`pre_tool_reviewer.py`). The `review()` function gains a third return value (`verdict`), reason extraction is made robust, and the stderr output is changed from `json.dumps` to a plain-English f-string. No new files are created.

**Tech Stack:** Python 3, subprocess, Claude CLI (Haiku)

**Spec:** `docs/superpowers/specs/2026-03-25-pre-tool-reviewer-block-message-design.md`

---

## File Map

| Action | File |
|--------|------|
| Modify | `.claude/hooks/pre_tool_reviewer.py` |

---

### Task 1: Fix `review()` — return type, reason extraction, return `verdict`

**Files:**
- Modify: `.claude/hooks/pre_tool_reviewer.py:15,41-43`

The current `review()` function returns `tuple[bool, str]`. We need it to return `tuple[bool, str, str]` so that `main()` can log the raw Haiku verdict even when the fallback fires.

Current lines being replaced:
- Line 15 (signature): `def review(tool_name: str, tool_input: dict) -> tuple[bool, str]:`
- Lines 41–43 (approved check, reason extraction, return):
```python
    approved = verdict.startswith("APPROVE")
    reason = verdict.replace("BLOCK:", "").strip() if not approved else ""
    return approved, reason
```

Lines 39–40 (`verdict = result.stdout.strip()` and `logger.debug(...)`) are **not** changed.

- [ ] **Step 1: Update the function signature**

Replace line 15:
```python
def review(tool_name: str, tool_input: dict) -> tuple[bool, str, str]:
```

- [ ] **Step 2: Replace lines 41–43 (the approved check, reason extraction, and return)**

Replace the three-line block starting at `approved = verdict.startswith("APPROVE")` through `return approved, reason` with:

```python
    approved = verdict.startswith("APPROVE")
    if not approved:
        reason = verdict.split(":", 1)[1].strip() if ":" in verdict else ""
        if not reason:
            reason = "no reason provided"
    else:
        reason = ""
    return approved, reason, verdict
```

- [ ] **Step 3: Verify the file looks correct**

Read `.claude/hooks/pre_tool_reviewer.py` and confirm:
- Signature is `-> tuple[bool, str, str]`
- Reason extraction uses `split(":", 1)`
- Returns three values: `approved, reason, verdict`
- Lines 39–40 (`verdict = result.stdout.strip()` and `logger.debug(...)`) are unchanged

---

### Task 2: Fix `main()` — unpack three values, update warning log, fix stderr message

**Files:**
- Modify: `.claude/hooks/pre_tool_reviewer.py:51,57-58`

Current code (lines 51, 57–58):
```python
    approved, reason = review(tool_name, tool_input)
    ...
        logger.warning("BLOCKED   tool=%s reason=%s", tool_name, reason)
        print(json.dumps({"reason": reason}), file=sys.stderr)
```

- [ ] **Step 1: Update the unpack and block branch in `main()`**

Replace line 51:
```python
    approved, reason, verdict = review(tool_name, tool_input)
```

Replace lines 57–58:
```python
        logger.warning("BLOCKED   tool=%s reason=%s verdict=%s", tool_name, reason, verdict)
        print(f"Tool '{tool_name}' blocked by pre_tool_reviewer.\nReason: {reason}", file=sys.stderr)
```

- [ ] **Step 2: Verify the file looks correct**

Read `.claude/hooks/pre_tool_reviewer.py` and confirm:
- `main()` unpacks three values from `review()`
- `logger.warning` includes `verdict=%s`
- `print(...)` is a plain f-string with no `json.dumps`
- The `json` import is still present (needed for `json.dumps` in `review()` and `json.load` in `main()`)

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/pre_tool_reviewer.py
git commit -m "fix: pre_tool_reviewer — robust reason extraction and readable block message"
```

---

### Task 3: Manual verification

No automated tests exist for this file. Verify by triggering a real block.

- [ ] **Step 1: Re-enable the PreToolUse hook in settings**

Ensure `.claude/settings.json` (and `/home/freesky1102/.claude/settings.json` if it is a separate file) has the PreToolUse hook configured:

```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "zsh -c \"source ~/.env.zsh; ~/.claude/hooks/.venv/bin/python ~/.claude/hooks/pre_tool_reviewer.py\""
      }
    ]
  }
]
```

- [ ] **Step 2: Ask Claude to run a destructive command**

In a new Claude Code session, ask Claude to run:
```
rm -rf /etc/something
```

- [ ] **Step 3: Confirm the block message**

Claude should receive:
```
Tool 'Bash' blocked by pre_tool_reviewer.
Reason: <non-empty reason from Haiku>
```

Confirm:
- No `{"reason": ...}` JSON anywhere in the message
- Reason is not empty
- The log file (check `~/.claude/hooks/logs/` or wherever `get_logger` writes) contains a line with both `reason=` and `verdict=`
