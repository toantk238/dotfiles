# stop_router: Skip Stop Hook While Background Tasks/Agents Are Running

## Overview
Prevent the Stop hook (`stop_router.py`) from calling the LLM or injecting auto-approvals/answers while native background tasks (such as subagents or background commands) are active.

## Background & Problem Statement
When Claude spawns a background agent/subagent, it registers that task with the parent session. The Stop hook (`stop_router.py`) executes at every turn boundary. 

Currently, `stop_router.py` only gates on `has_incomplete_tasks(transcript_path)` (which checks the custom task-tracking plugin). It does not check for native background tasks passed via the hook's input payload under `background_tasks`. 

As a result, the Stop hook falls through, queries the classification LLM, and injects auto-approvals (e.g. `[stop_router] Auto-approved: ...`). This wakes up the parent agent, leading to confusion and infinite loops while waiting for the background agent.

## Goals & Requirements
1. **Detect active background tasks**: Inspect the `background_tasks` payload list in the hook input.
2. **Early exit**: If any task in `background_tasks` has a status of `"running"`, the Stop hook must immediately exit with code `0` (do nothing, pass back to human).
3. **No LLM calls**: The LLM must not be called when background tasks are running.
4. **Test coverage**: Provide unit/integration tests for both early-exit and normal fall-through paths under different background task statuses.

## Detailed Design

### 1. Stop Router Modification (`.claude_custom/hooks/stop_router.py`)
We will read `background_tasks` from `hook_input` and check for `"status": "running"`.

```python
    # Check if there are any running background tasks (like subagents) in hook input
    background_tasks = hook_input.get("background_tasks", [])
    if any(task.get("status") == "running" for task in background_tasks if isinstance(task, dict)):
        logger.info("Early exit: running background tasks/agents present in hook input")
        sys.exit(0)
```

This check will be placed in `main()` immediately after the `has_incomplete_tasks` check.

### 2. Test Updates (`.claude_custom/hooks/tests/test_stop_router.py`)
Add test cases verifying:
- `test_main_skips_when_background_tasks_running`: Hook input has a task with `"status": "running"`. The hook should exit 0 and mock LLM is not called.
- `test_main_proceeds_when_background_tasks_completed_or_failed`: Hook input has background tasks but none are `"running"` (e.g., `"completed"`, `"failed"`). The hook should proceed normally to call the LLM.

## Rollout Plan
1. Write tests reproducing the problem.
2. Modify `stop_router.py` to add the gate.
3. Verify that tests pass.
4. Commit changes to git.
