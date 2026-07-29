# stop_router: Skip Hook While Tasks Are Incomplete

**Date:** 2026-07-03
**File:** `.claude_custom/hooks/stop_router.py`, `.claude_custom/hooks/common.py`

## Problem

The Stop hook fires on every `Stop` event — whenever Claude's turn ends without a further tool call — and asks an LLM to classify the last message as `PROCEED`, `ANSWER`, or `HUMAN_NEEDED`. `PROCEED`/`ANSWER` force Claude to keep going (exit code 2, with injected context); `HUMAN_NEEDED` lets the stop happen normally (exit code 0).

The hook has no awareness of the session's Task tracker (`TaskCreate`/`TaskUpdate`/`TaskList`). When a Stop fires while a multi-step task list still has pending or in-progress items (e.g. mid-checklist during a skill like brainstorming), the hook still runs its full classification and can inject an auto-approval or auto-answer that doesn't actually correspond to a real decision point — producing confusing or wrong interjections partway through a known, in-progress plan.

## Solution

Skip the entire hook — no static-rule check, no LLM call — whenever the transcript shows any task that hasn't reached a terminal state. Let the Stop happen normally (exit 0), same as if the hook weren't installed.

### 1. `has_incomplete_tasks()` in `common.py`

Reconstructs task state by replaying `TaskCreate`/`TaskUpdate` tool calls from the transcript, in order:

- Assistant `TaskCreate` tool_use → remember its `tool_use_id`.
- Matching `tool_result` (delivered in a `user`-role message) → regex out the assigned id from `"Task #N created successfully..."` and record `states[N] = "pending"`.
- Assistant `TaskUpdate` tool_use → overwrite `states[taskId]` with `input["status"]` directly (no need to parse its result).
- A task is incomplete if its last known status is `pending` or `in_progress`. `completed` and `deleted` (the only other valid `TaskUpdate` statuses) both count as done.

Task IDs are assigned monotonically for the life of a session and never reused, so a single forward pass over the transcript is sufficient — no need to reset state between unrelated task batches.

```python
import re

_TASK_CREATED_RE = re.compile(r"Task #(\d+) created successfully")
_INCOMPLETE_STATUSES = {"pending", "in_progress"}


def has_incomplete_tasks(transcript_path: str) -> bool:
    """True if any task created in this transcript hasn't reached completed/deleted."""
    states: dict[str, str] = {}
    pending_create_ids: set[str] = set()

    for entry in read_transcript(transcript_path):
        msg = entry.get("message", {})
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        role = msg.get("role")
        if role == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                name = block.get("name")
                if name == "TaskCreate":
                    pending_create_ids.add(block.get("id"))
                elif name == "TaskUpdate":
                    task_id = str(block.get("input", {}).get("taskId", ""))
                    status = block.get("input", {}).get("status", "")
                    if task_id:
                        states[task_id] = status
        elif role == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                if block.get("tool_use_id") not in pending_create_ids:
                    continue
                text = extract_text(block.get("content", ""))
                m = _TASK_CREATED_RE.search(text)
                if m:
                    states.setdefault(m.group(1), "pending")

    return any(status in _INCOMPLETE_STATUSES for status in states.values())
```

### 2. Early exit in `stop_router.py::main()`

Placed immediately after the `transcript_path` existence check, before `check_static_rules`, before repeat-detection, before the LLM call — mirroring the other early-exit guards already in `main()`:

```python
if not transcript_path or not os.path.exists(transcript_path):
    logger.debug("Early exit: no transcript (nested session)")
    sys.exit(0)

if has_incomplete_tasks(transcript_path):
    logger.info("Early exit: incomplete tasks present in task list")
    sys.exit(0)

last_text = hook_input.get("last_assistant_message", "")
...
```

### 3. Error handling

Any parsing failure (malformed JSON line, unexpected result text, missing fields) is swallowed the same way `read_transcript()` already tolerates bad lines — a task simply isn't recorded, or `_TASK_CREATED_RE` doesn't match and that create is skipped. This fails open: worst case, a format change in the Task tool's result text means the check finds zero tasks and the hook behaves exactly as it does today, rather than getting silently wedged into always skipping.

## Tests

Added to `tests/test_stop_router.py` (existing convention — it already covers `common.*` functions), using the same `_write_transcript`/`_msg` fixtures, extended with a helper to embed `tool_use`/`tool_result` blocks for `TaskCreate`/`TaskUpdate`:

- `test_has_incomplete_tasks_pending` — one `TaskCreate`, no update → `True`.
- `test_has_incomplete_tasks_in_progress` — created + updated to `in_progress` → `True`.
- `test_has_incomplete_tasks_all_completed` — multiple tasks, all updated to `completed` → `False`.
- `test_has_incomplete_tasks_deleted_counts_as_done` — one `completed`, one `deleted` → `False`.
- `test_has_incomplete_tasks_no_tasks` — transcript with no Task tool calls at all → `False`.
- `test_main_skips_when_tasks_incomplete` — full `main()` integration: transcript with an incomplete task and a PROCEED-worthy last message → exits 0, `call_claude` never invoked.
- `test_main_proceeds_when_tasks_all_completed` — same shape but all tasks completed → falls through to existing LLM-driven behavior (regression guard for current tests).
