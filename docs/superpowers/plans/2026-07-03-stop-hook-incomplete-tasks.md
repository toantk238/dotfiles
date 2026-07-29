# stop_router: Skip Hook While Tasks Are Incomplete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Stop hook skip its entire classification pipeline (static rules + LLM call) whenever the session's transcript shows a task that hasn't reached a terminal status, so it stops injecting confusing auto-approvals mid-checklist.

**Architecture:** Add a pure function `has_incomplete_tasks(transcript_path)` to `common.py` that replays `TaskCreate`/`TaskUpdate` tool calls from the transcript to reconstruct each task's last-known status. Wire it into `stop_router.py::main()` as an early-exit guard, placed before the existing static-rule check and LLM call.

**Tech Stack:** Python 3.11+, pytest (existing suite in `.claude_custom/hooks/tests/`)

## Global Constraints

- Valid `TaskUpdate` statuses are exactly `pending`, `in_progress`, `completed`, `deleted` — no other values exist. Terminal (= "done") statuses are `completed` and `deleted`; `pending` and `in_progress` are incomplete.
- Task IDs are assigned monotonically for the life of a session and are never reused — a single forward pass over the transcript is sufficient.
- Parsing failures must fail open (treated as "no incomplete tasks found"), matching how `read_transcript()` already tolerates malformed lines — never raise out of `has_incomplete_tasks()`.
- Follow the existing test fixture style in `tests/test_stop_router.py` (`_write_transcript`, `_msg`) rather than introducing a new fixture pattern.

---

### Task 1: Add `has_incomplete_tasks()` to `common.py`

**Files:**
- Modify: `.claude_custom/hooks/common.py`
- Test: `.claude_custom/hooks/tests/test_stop_router.py`

**Interfaces:**
- Produces: `has_incomplete_tasks(transcript_path: str) -> bool` in `common.py`, used by Task 2.

- [ ] **Step 1: Add transcript fixture helpers for Task tool calls**

In `.claude_custom/hooks/tests/test_stop_router.py`, add these three helpers directly after the existing `_msg()` function (after line 33):

```python
def _task_create(tool_use_id: str, subject: str) -> dict:
    """Assistant turn: a single TaskCreate tool_use block."""
    return {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_use_id, "name": "TaskCreate",
         "input": {"subject": subject, "description": subject}},
    ]}}


def _task_create_result(tool_use_id: str, task_id: str, subject: str) -> dict:
    """User turn: the tool_result for a TaskCreate call."""
    return {"message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id,
         "content": f"Task #{task_id} created successfully: {subject}"},
    ]}}


def _task_update(task_id: str, status: str) -> dict:
    """Assistant turn: a single TaskUpdate tool_use block."""
    return {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": f"toolu_update_{task_id}_{status}", "name": "TaskUpdate",
         "input": {"taskId": task_id, "status": status}},
    ]}}
```

- [ ] **Step 2: Write failing tests for `has_incomplete_tasks()`**

Add this new section at the end of `tests/test_stop_router.py`:

```python
# ── has_incomplete_tasks ─────────────────────────────────────────────────────

def test_has_incomplete_tasks_pending(tmp_path):
    """A created task with no update at all is still pending -> incomplete."""
    path = _write_transcript(tmp_path, [
        _task_create("toolu_1", "Do the thing"),
        _task_create_result("toolu_1", "1", "Do the thing"),
    ])
    assert common.has_incomplete_tasks(path) is True


def test_has_incomplete_tasks_in_progress(tmp_path):
    path = _write_transcript(tmp_path, [
        _task_create("toolu_1", "Do the thing"),
        _task_create_result("toolu_1", "1", "Do the thing"),
        _task_update("1", "in_progress"),
    ])
    assert common.has_incomplete_tasks(path) is True


def test_has_incomplete_tasks_all_completed(tmp_path):
    path = _write_transcript(tmp_path, [
        _task_create("toolu_1", "Task one"),
        _task_create_result("toolu_1", "1", "Task one"),
        _task_create("toolu_2", "Task two"),
        _task_create_result("toolu_2", "2", "Task two"),
        _task_update("1", "in_progress"),
        _task_update("1", "completed"),
        _task_update("2", "in_progress"),
        _task_update("2", "completed"),
    ])
    assert common.has_incomplete_tasks(path) is False


def test_has_incomplete_tasks_deleted_counts_as_done(tmp_path):
    path = _write_transcript(tmp_path, [
        _task_create("toolu_1", "Task one"),
        _task_create_result("toolu_1", "1", "Task one"),
        _task_create("toolu_2", "Task two"),
        _task_create_result("toolu_2", "2", "Task two"),
        _task_update("1", "completed"),
        _task_update("2", "deleted"),
    ])
    assert common.has_incomplete_tasks(path) is False


def test_has_incomplete_tasks_no_tasks(tmp_path):
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", "sure, done"),
    ])
    assert common.has_incomplete_tasks(path) is False
```

- [ ] **Step 3: Run new tests to verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -k has_incomplete_tasks -v
```

Expected: 5 FAILs with `AttributeError: module 'common' has no attribute 'has_incomplete_tasks'`.

- [ ] **Step 4: Implement `has_incomplete_tasks()` in `common.py`**

Add `import re` to the stdlib import block at the top of `common.py` (between `import os` and `import subprocess`, keeping the block alphabetical):

```python
from dataclasses import dataclass
import json
import os
import re
import subprocess
import sys
from typing import Any, Iterator

from logger import get_logger
```

Then append this to the end of `common.py` (after `get_last_assistant_message`):

```python
_TASK_CREATED_RE = re.compile(r"Task #(\d+) created successfully")
_INCOMPLETE_TASK_STATUSES = {"pending", "in_progress"}


def has_incomplete_tasks(transcript_path: str) -> bool:
    """True if any task created in this transcript hasn't reached completed/deleted.

    Replays TaskCreate/TaskUpdate tool calls in order. Task ids are assigned
    monotonically and never reused within a session, so a single forward pass
    is sufficient. Any parsing failure is treated as "no incomplete tasks"
    (fail open) rather than raising.
    """
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

    return any(status in _INCOMPLETE_TASK_STATUSES for status in states.values())
```

- [ ] **Step 5: Run new tests — expect PASS**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -k has_incomplete_tasks -v
```

Expected: 5 PASSes.

- [ ] **Step 6: Run full test suite — check for regressions**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -v
```

Expected: 36 passed, 3 failed. The 3 failures (`test_main_uses_transcript_message_not_payload_field`, `test_static_rule_missing_term_returns_none[Plan complete and saved]`, `test_static_rule_missing_term_returns_none[Which approach?]`) are pre-existing and unrelated to this change — confirmed by running the suite before starting this task. Do not attempt to fix them here.

- [ ] **Step 7: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add .claude_custom/hooks/common.py .claude_custom/hooks/tests/test_stop_router.py
git commit -m "feat(hooks): add has_incomplete_tasks() to detect open Task tracker items"
```

---

### Task 2: Gate `stop_router.py::main()` on incomplete tasks

**Files:**
- Modify: `.claude_custom/hooks/stop_router.py`
- Test: `.claude_custom/hooks/tests/test_stop_router.py`

**Interfaces:**
- Consumes: `common.has_incomplete_tasks(transcript_path: str) -> bool` from Task 1.

- [ ] **Step 1: Write failing integration tests**

Add this new section at the end of `tests/test_stop_router.py`:

```python
# ── main() incomplete-tasks gate ─────────────────────────────────────────────

def test_main_skips_when_tasks_incomplete(tmp_path):
    """Stop fires while a task is still pending/in_progress -> exit 0, LLM never called."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _task_create("toolu_1", "Step one"),
        _task_create_result("toolu_1", "1", "Step one"),
        _task_update("1", "in_progress"),
        _msg("assistant", "Shall I proceed?"),
    ])
    with patch("stop_router.call_claude") as mock_llm:
        with pytest.raises(SystemExit) as exc:
            _run_main(path)
    assert exc.value.code == 0
    mock_llm.assert_not_called()


def test_main_proceeds_when_tasks_all_completed(tmp_path):
    """All tasks completed -> falls through to existing LLM-driven behavior."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _task_create("toolu_1", "Step one"),
        _task_create_result("toolu_1", "1", "Step one"),
        _task_update("1", "completed"),
        _msg("assistant", "Shall I proceed?"),
    ])
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            _run_main(path)
    assert exc.value.code == 2
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -k "skips_when_tasks_incomplete or proceeds_when_tasks_all_completed" -v
```

Expected: `test_main_skips_when_tasks_incomplete` FAILs (`mock_llm.assert_not_called()` fails — the LLM is still called because the gate doesn't exist yet). `test_main_proceeds_when_tasks_all_completed` PASSes already (no regression risk, just confirms baseline).

- [ ] **Step 3: Import `has_incomplete_tasks` in `stop_router.py`**

Replace the `common` import block near the top of `stop_router.py`:

```python
from common import (
    HookInput,
    call_claude,
    get_last_assistant_message,
    get_original_user_request,
)
```

with:

```python
from common import (
    HookInput,
    call_claude,
    get_last_assistant_message,
    get_original_user_request,
    has_incomplete_tasks,
)
```

- [ ] **Step 4: Add the early-exit gate in `main()`**

In `stop_router.py::main()`, insert the gate right after the transcript-existence check and before `last_text = hook_input.get(...)`:

```python
    transcript_path = hook_input.get("transcript_path", "")
    # Check existence here (not just inside read_transcript) so we can exit early
    # with a specific "nested session" log before making two file-open attempts.
    if not transcript_path or not os.path.exists(transcript_path):
        logger.debug("Early exit: no transcript (nested session)")
        sys.exit(0)

    if has_incomplete_tasks(transcript_path):
        logger.info("Early exit: incomplete tasks present in task list")
        sys.exit(0)

    last_text = hook_input.get("last_assistant_message", "")
```

- [ ] **Step 5: Run new tests — expect PASS**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -k "skips_when_tasks_incomplete or proceeds_when_tasks_all_completed" -v
```

Expected: 2 PASSes.

- [ ] **Step 6: Run full test suite — check for regressions**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -v
```

Expected: 38 passed, 3 failed (the same pre-existing failures noted in Task 1, Step 6 — unchanged).

- [ ] **Step 7: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add .claude_custom/hooks/stop_router.py .claude_custom/hooks/tests/test_stop_router.py
git commit -m "fix(hooks): skip stop_router entirely while task tracker has open items"
```
