# stop_router: Skip Stop Hook While Background Tasks/Agents Are Running Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip the Stop hook (`stop_router.py`) entirely and exit `0` whenever any background task (such as subagents or background commands) is in the `"running"` state.

**Architecture:** Read the `"background_tasks"` list from the stdin hook input inside `stop_router.py::main()`. If any background task contains `"status": "running"`, exit immediately with code `0`.

**Tech Stack:** Python 3.14+, pytest

## Global Constraints
- Inspect all elements of `background_tasks` where `"status"` matches `"running"`.
- Never call the classification LLM (`call_claude`) if any background task is running.
- Exit code `0` is used to yield control back to the environment/user.
- Parsing failures or absent fields should fail open (proceed to normal classification).

---

### Task 1: Add Unit/Integration Tests for Background Task Gating

**Files:**
- Modify: `.claude_custom/hooks/tests/test_stop_router.py`

**Interfaces:**
- Produces: `test_main_skips_when_background_tasks_running` and `test_main_proceeds_when_background_tasks_completed_or_failed` in `tests/test_stop_router.py`.

- [ ] **Step 1: Write integration tests at the end of the file**

Add the following tests to the bottom of `.claude_custom/hooks/tests/test_stop_router.py`:

```python
# ── main() background-tasks gate ─────────────────────────────────────────────

def test_main_skips_when_background_tasks_running(tmp_path):
    """Stop fires while a background task is running -> exit 0, LLM never called."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", "Starting exploration agent."),
    ])
    payload = {
        "background_tasks": [
            {"id": "task_1", "status": "running", "type": "subagent"}
        ]
    }
    with patch("stop_router.call_claude") as mock_llm:
        with pytest.raises(SystemExit) as exc:
            _run_main(path, payload)
    assert exc.value.code == 0
    mock_llm.assert_not_called()


def test_main_proceeds_when_background_tasks_completed_or_failed(tmp_path):
    """Stop fires but no background tasks are running -> proceeds to LLM."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", "Ready to start?"),
    ])
    payload = {
        "background_tasks": [
            {"id": "task_1", "status": "completed", "type": "subagent"},
            {"id": "task_2", "status": "failed", "type": "subagent"}
        ]
    }
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output) as mock_llm:
        with pytest.raises(SystemExit) as exc:
            _run_main(path, payload)
    assert exc.value.code == 2
    mock_llm.assert_called_once()
```

- [ ] **Step 2: Run new tests to verify they fail**

Run:
```bash
.claude_custom/hooks/.venv/bin/pytest .claude_custom/hooks/tests/test_stop_router.py -k "background_tasks" -v
```
Expected output: `test_main_skips_when_background_tasks_running` FAILS because the gate does not exist yet (so `call_claude` is mocked but gets called, causing assertion failure). `test_main_proceeds_when_background_tasks_completed_or_failed` PASSES.

- [ ] **Step 3: Commit**

Run:
```bash
git add .claude_custom/hooks/tests/test_stop_router.py
git commit -m "test(hooks): add failing test for background_tasks stop_router gate"
```

---

### Task 2: Implement Background Task Gating in `stop_router.py`

**Files:**
- Modify: `.claude_custom/hooks/stop_router.py:204-210`

**Interfaces:**
- Consumes: `"background_tasks"` list from `HookInput` in `stop_router.py`.

- [ ] **Step 1: Implement the early exit check in `main()`**

Modify `.claude_custom/hooks/stop_router.py` around line 204 to include the check for running background tasks:

```python
    if has_incomplete_tasks(transcript_path):
        logger.info("Early exit: incomplete tasks present in task list")
        sys.exit(0)

    # Check if there are any running background tasks (like subagents) in hook input
    background_tasks = hook_input.get("background_tasks", [])
    if any(task.get("status") == "running" for task in background_tasks if isinstance(task, dict)):
        logger.info("Early exit: running background tasks/agents present in hook input")
        sys.exit(0)
```

- [ ] **Step 2: Run the test suite to verify tests pass**

Run:
```bash
.claude_custom/hooks/.venv/bin/pytest .claude_custom/hooks/tests/test_stop_router.py -k "background_tasks" -v
```
Expected output: 2 passed.

- [ ] **Step 3: Run the full test suite to check for regressions**

Run:
```bash
.claude_custom/hooks/.venv/bin/pytest .claude_custom/hooks/tests/test_stop_router.py -v
```
Expected output: 46 passed, 3 failed (the 3 pre-existing failures on master).

- [ ] **Step 4: Commit**

Run:
```bash
git add .claude_custom/hooks/stop_router.py
git commit -m "fix(hooks): skip stop_router entirely when background tasks are running"
```
