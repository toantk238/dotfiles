# Stop Hook: Transcript-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix stop hook auto-answering by reading the full last assistant message from the transcript file and using `transcript_path` from the hook payload to detect and silently skip nested sub-sessions.

**Architecture:** `common.py` gets a path-based `read_transcript`, an updated `get_original_user_request`, and a new `get_last_assistant_message`. `stop_router.py` uses `transcript_path` from the hook payload as a session guard and message source. The `stop_hook_active` special-case gate is removed — re-woken stops go through the full decision path.

**Tech Stack:** Python 3.14, pytest, Claude Code hook API (JSONL transcript format)

---

## File Map

| File | Change |
|------|--------|
| `.claude/hooks/common.py` | Update `read_transcript` signature; update `get_original_user_request` to take path; add `get_last_assistant_message`; remove `glob` import |
| `.claude/hooks/stop_router.py` | Add `transcript_path` guard; replace `last_assistant_message` with transcript read + fallback; remove `stop_hook_active` gate; add `import os` |
| `.claude/hooks/tests/test_stop_router.py` | Update `_write_transcript` / `_run_main` helpers; update existing tests; add 4 new tests |

---

### Task 1: Update `common.py` — path-based transcript reading

**Files:**
- Modify: `.claude/hooks/common.py`
- Test: `.claude/hooks/tests/test_stop_router.py`

- [ ] **Step 1: Write failing tests for the updated `get_original_user_request` signature**

Add to `test_stop_router.py` (replace the existing `test_get_original_user_request_basic`):

```python
def test_get_original_user_request_basic(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(e) for e in [
            {"message": {"role": "user", "content": [{"type": "text", "text": "original request"}]}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "sure"}]}},
            {"message": {"role": "user", "content": [{"type": "text", "text": "second user message"}]}},
        ]),
        encoding="utf-8",
    )
    assert common.get_original_user_request(str(transcript)) == "original request"


def test_get_original_user_request_no_file():
    assert common.get_original_user_request("/nonexistent/path.jsonl") is None


def test_get_original_user_request_no_user_messages(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}}),
        encoding="utf-8",
    )
    assert common.get_original_user_request(str(transcript)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude/hooks
.venv/bin/pytest tests/test_stop_router.py::test_get_original_user_request_basic tests/test_stop_router.py::test_get_original_user_request_no_file tests/test_stop_router.py::test_get_original_user_request_no_user_messages -v
```

Expected: FAIL — `get_original_user_request` currently takes `session_id`, not a path.

- [ ] **Step 3: Update `common.py` — rewrite `read_transcript` and `get_original_user_request`**

Replace the `read_transcript` and `get_original_user_request` functions entirely. Also remove the `glob` import (no longer needed). The file top imports become:

```python
"""Common utilities for hooks."""
from dataclasses import dataclass
import json
import os
import subprocess
import sys
from typing import Any, Iterator
from typing import Any

from logger import get_logger
```

Replace `read_transcript`:

```python
def read_transcript(transcript_path: str) -> Iterator[dict[str, Any]]:
    """Read transcript from a given file path, yielding parsed JSONL entries."""
    if not transcript_path or not os.path.exists(transcript_path):
        return
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Could not read transcript: {e}")
        return
```

Replace `get_original_user_request`:

```python
def get_original_user_request(transcript_path: str) -> str | None:
    """Find the first user message in the transcript at the given path."""
    for entry in read_transcript(transcript_path):
        msg = entry.get("message", {})
        if msg.get("role") == "user":
            text = extract_text(msg.get("content", ""))
            if text:
                return text
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_stop_router.py::test_get_original_user_request_basic tests/test_stop_router.py::test_get_original_user_request_no_file tests/test_stop_router.py::test_get_original_user_request_no_user_messages -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add .claude/hooks/common.py .claude/hooks/tests/test_stop_router.py
git commit -m "refactor(hooks): make read_transcript/get_original_user_request path-based"
```

---

### Task 2: Add `get_last_assistant_message` to `common.py`

**Files:**
- Modify: `.claude/hooks/common.py`
- Test: `.claude/hooks/tests/test_stop_router.py`

- [ ] **Step 1: Write the failing test**

Add to `test_stop_router.py`:

```python
def test_get_last_assistant_message_basic(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(e) for e in [
            {"message": {"role": "user", "content": [{"type": "text", "text": "do something"}]}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "first response"}]}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "final response — shall I proceed?"}]}},
        ]),
        encoding="utf-8",
    )
    assert common.get_last_assistant_message(str(transcript)) == "final response — shall I proceed?"


def test_get_last_assistant_message_skips_thinking_blocks(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "I am thinking..."},
            {"type": "text", "text": "Here is my answer"},
        ]}}),
        encoding="utf-8",
    )
    assert common.get_last_assistant_message(str(transcript)) == "Here is my answer"


def test_get_last_assistant_message_no_text_blocks(tmp_path):
    """Tool-use-only turns have no text block — should return None."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "x", "name": "Bash", "input": {}},
        ]}}),
        encoding="utf-8",
    )
    assert common.get_last_assistant_message(str(transcript)) is None


def test_get_last_assistant_message_no_file():
    assert common.get_last_assistant_message("/nonexistent.jsonl") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude/hooks
.venv/bin/pytest tests/test_stop_router.py::test_get_last_assistant_message_basic tests/test_stop_router.py::test_get_last_assistant_message_skips_thinking_blocks tests/test_stop_router.py::test_get_last_assistant_message_no_text_blocks tests/test_stop_router.py::test_get_last_assistant_message_no_file -v
```

Expected: FAIL — `get_last_assistant_message` does not exist yet.

- [ ] **Step 3: Implement `get_last_assistant_message` in `common.py`**

Add after `get_original_user_request`:

```python
def get_last_assistant_message(transcript_path: str) -> str | None:
    """Return the text content of the last assistant turn in the transcript."""
    last_text = None
    for entry in read_transcript(transcript_path):
        msg = entry.get("message", {})
        if msg.get("role") == "assistant":
            text = extract_text(msg.get("content", ""))
            if text:
                last_text = text
    return last_text
```

Also update the import in `stop_router.py` to include `get_last_assistant_message`:

```python
from common import HookInput, call_claude, get_original_user_request, get_last_assistant_message
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_stop_router.py::test_get_last_assistant_message_basic tests/test_stop_router.py::test_get_last_assistant_message_skips_thinking_blocks tests/test_stop_router.py::test_get_last_assistant_message_no_text_blocks tests/test_stop_router.py::test_get_last_assistant_message_no_file -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add .claude/hooks/common.py .claude/hooks/tests/test_stop_router.py
git commit -m "feat(hooks): add get_last_assistant_message to common"
```

---

### Task 3: Update `stop_router.py` — transcript-first main loop

**Files:**
- Modify: `.claude/hooks/stop_router.py`
- Test: `.claude/hooks/tests/test_stop_router.py`

- [ ] **Step 1: Write failing tests for the new `main()` behavior**

Replace the existing `_write_transcript`, `_run_main`, `test_main_stop_hook_active_exits_0`, and `test_main_calls_handle_stop` with:

```python
# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_transcript(tmp_path, lines: list[dict]) -> str:
    """Write a fake JSONL transcript, return the absolute path string."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(l) for l in lines),
        encoding="utf-8",
    )
    return str(transcript)


def _msg(role: str, text: str | list) -> dict:
    if isinstance(text, str):
        content = [{"type": "text", "text": text}]
    else:
        content = text
    return {"message": {"role": role, "content": content}}


def _run_main(transcript_path: str, extra_hook_input: dict | None = None):
    """Run stop_router.main() with the given transcript_path in hook input."""
    hook_input = {"transcript_path": transcript_path}
    if extra_hook_input:
        hook_input.update(extra_hook_input)
    with patch("sys.stdin", io.StringIO(json.dumps(hook_input))):
        stop_router.main()


# ── main() integration ────────────────────────────────────────────────────────

def test_main_no_transcript_path_exits_0():
    """Missing transcript_path → nested session guard → exit 0."""
    with pytest.raises(SystemExit) as exc:
        with patch("sys.stdin", io.StringIO(json.dumps({}))):
            stop_router.main()
    assert exc.value.code == 0


def test_main_nonexistent_transcript_exits_0():
    """transcript_path present but file missing → nested session guard → exit 0."""
    with pytest.raises(SystemExit) as exc:
        with patch("sys.stdin", io.StringIO(json.dumps({"transcript_path": "/no/such/file.jsonl"}))):
            stop_router.main()
    assert exc.value.code == 0


def test_main_stop_hook_active_still_processes(tmp_path):
    """Re-woken stop (stop_hook_active=True) goes through full PROCEED path."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", "Shall I proceed?"),
    ])
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            _run_main(path, {"stop_hook_active": True})
    assert exc.value.code == 2


def test_main_uses_transcript_message_not_payload_field(tmp_path):
    """Full message from transcript is used even when payload has a truncated version."""
    full_text = "This is the full message — Shall I proceed with the implementation?"
    truncated = "This is the full message — Shall I"
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", full_text),
    ])
    captured_prompt = []

    def fake_claude(prompt, **kwargs):
        captured_prompt.append(prompt)
        return "ACTION: PROCEED\nANSWER: "

    with patch("stop_router.call_claude", side_effect=fake_claude):
        with pytest.raises(SystemExit):
            _run_main(path, {"last_assistant_message": truncated})

    assert full_text in captured_prompt[0]
    assert truncated not in captured_prompt[0]


def test_main_calls_handle_stop(tmp_path):
    """Normal stop → finds original request and last message → PROCEED."""
    path = _write_transcript(tmp_path, [
        _msg("user", "original request"),
        _msg("assistant", "ready to go"),
    ])
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            _run_main(path)
    assert exc.value.code == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude/hooks
.venv/bin/pytest tests/test_stop_router.py::test_main_no_transcript_path_exits_0 tests/test_stop_router.py::test_main_nonexistent_transcript_exits_0 tests/test_stop_router.py::test_main_stop_hook_active_still_processes tests/test_stop_router.py::test_main_uses_transcript_message_not_payload_field tests/test_stop_router.py::test_main_calls_handle_stop -v
```

Expected: FAIL (old `main()` still uses session_id / stop_hook_active gate).

- [ ] **Step 3: Rewrite `main()` in `stop_router.py`**

Add `import os` at the top of `stop_router.py` (with the other stdlib imports):

```python
import os
```

Update the import from common:

```python
from common import HookInput, call_claude, get_original_user_request, get_last_assistant_message
```

Replace `main()` entirely:

```python
def main():
    hook_input = HookInput.from_stdin()
    if not hook_input.data:
        logger.info("Early exit: empty stdin")
        sys.exit(0)

    logger.debug(f"input = {json.dumps(hook_input.data, indent=2)}")

    transcript_path = hook_input.get("transcript_path", "")
    if not transcript_path or not os.path.exists(transcript_path):
        logger.debug("Early exit: no transcript (nested session)")
        sys.exit(0)

    last_text = get_last_assistant_message(transcript_path)
    if not last_text:
        last_text = hook_input.get("last_assistant_message", "")
    if not last_text:
        logger.info("Early exit: no last_text found")
        sys.exit(0)

    original_request = get_original_user_request(transcript_path)
    if not original_request:
        logger.info("Early exit: no original_request in transcript")
        sys.exit(0)

    handle_stop(last_text, original_request)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
.venv/bin/pytest tests/test_stop_router.py::test_main_no_transcript_path_exits_0 tests/test_stop_router.py::test_main_nonexistent_transcript_exits_0 tests/test_stop_router.py::test_main_stop_hook_active_still_processes tests/test_stop_router.py::test_main_uses_transcript_message_not_payload_field tests/test_stop_router.py::test_main_calls_handle_stop -v
```

Expected: PASS

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass. If `test_main_stop_hook_active_exits_0` (old test) exists and fails, delete it — it tested the removed behavior.

- [ ] **Step 6: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add .claude/hooks/stop_router.py .claude/hooks/tests/test_stop_router.py
git commit -m "feat(hooks): transcript-first stop hook — fix truncation and nested session noise"
```
