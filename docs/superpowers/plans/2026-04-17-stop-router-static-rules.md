# stop_router Static Rules Short-Circuit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `check_static_rules()` function to `stop_router.py` that detects the writing-plans "which approach?" prompt by keyword and auto-selects Subagent-Driven without calling the LLM.

**Architecture:** A pure-Python keyword check runs at the top of `handle_stop()` before the LLM call. If all 4 sentinel terms are present in the last assistant message, the function returns the inject-context string and `handle_stop()` exits with code 2 immediately. No LLM call, no network latency.

**Tech Stack:** Python 3.11+, pytest (existing test suite in `tests/`)

---

### Task 1: Add `check_static_rules()` and wire it into `handle_stop()`

**Files:**
- Modify: `.claude_custom/hooks/stop_router.py`

- [ ] **Step 1: Open `stop_router.py` and locate the module-level constants block**

The file currently has `STOP_PROMPT_TEMPLATE` as the only module-level constant. You will add the terms list just above it (after the imports and `StopDecision` dataclass, before `STOP_PROMPT_TEMPLATE`).

- [ ] **Step 2: Add the terms constant and `check_static_rules()` function**

Insert this block immediately before the `STOP_PROMPT_TEMPLATE = """...` line:

```python
_PLAN_SELECTION_TERMS = [
    "Plan complete and saved",
    "Subagent-Driven",
    "Inline Execution",
    "Which approach?",
]


def check_static_rules(last_text: str) -> str | None:
    """Return an inject-context string if a known deterministic pattern matches, else None."""
    if all(term in last_text for term in _PLAN_SELECTION_TERMS):
        return '[stop_router] Auto-answered: "Option 1: Subagent-Driven". Please continue accordingly.'
    return None
```

- [ ] **Step 3: Wire into `handle_stop()` — add static check before LLM call**

Replace the opening of `handle_stop()` (currently just the `prompt = ...` line) with:

```python
def handle_stop(last_text: str, original_request: str) -> None:
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

    prompt = STOP_PROMPT_TEMPLATE.format(
        original_request=original_request[:1000],
        last_text=last_text[:2000]
    )
    # ... rest of function unchanged
```

The full `handle_stop()` after the edit should look like:

```python
def handle_stop(last_text: str, original_request: str) -> None:
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

    prompt = STOP_PROMPT_TEMPLATE.format(
        original_request=original_request[:1000],
        last_text=last_text[:2000]
    )

    try:
        output = call_claude(prompt, timeout=30)
    except Exception as e:
        logger.warning(f"LLM call failed, falling back to human: {e}")
        sys.exit(0)

    decision = parse_llm_output(output)
    logger.info(f"Decision: action={decision.action} answer={decision.answer[:80] if decision.answer else ''}")

    context = ""
    if decision.action == "PROCEED":
        context = '[stop_router] Auto-approved: "Proceed". Please continue accordingly.'
    elif decision.action == "ANSWER" and decision.answer:
        context = f'[stop_router] Auto-answered: "{decision.answer}". Please continue accordingly.'
    else:
        logger.info(f"Passing to human (action={decision.action})")
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }))
    sys.exit(2)
```

---

### Task 2: Write and run tests for `check_static_rules()` and the wired `handle_stop()`

**Files:**
- Modify: `.claude_custom/hooks/tests/test_stop_router.py`

- [ ] **Step 1: Write the three failing tests**

Add this section at the end of `tests/test_stop_router.py`:

```python
# ── check_static_rules ───────────────────────────────────────────────────────

_PLAN_MSG = (
    "Plan complete and saved to docs/superpowers/plans/2026-04-17-foo.md. "
    "7 tasks, ~25 steps total.\n\n"
    "Two execution options:\n\n"
    "1. Subagent-Driven (recommended) — I dispatch a fresh subagent per task\n\n"
    "2. Inline Execution — Execute tasks in this session\n\n"
    "Which approach?"
)


def test_static_rule_plan_selection_matches():
    result = stop_router.check_static_rules(_PLAN_MSG)
    assert result is not None
    assert "Subagent-Driven" in result


def test_static_rule_missing_term_returns_none():
    msg = _PLAN_MSG.replace("Which approach?", "What do you want to do?")
    assert stop_router.check_static_rules(msg) is None


def test_handle_stop_static_rule_exits_2_without_llm(capsys):
    with patch("stop_router.call_claude") as mock_llm:
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop(_PLAN_MSG, "build something")
    assert exc.value.code == 2
    mock_llm.assert_not_called()
    out = json.loads(capsys.readouterr().out)
    assert "Subagent-Driven" in out["hookSpecificOutput"]["additionalContext"]
```

- [ ] **Step 2: Run tests to verify they FAIL (function not yet added)**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py::test_static_rule_plan_selection_matches \
    tests/test_stop_router.py::test_static_rule_missing_term_returns_none \
    tests/test_stop_router.py::test_handle_stop_static_rule_exits_2_without_llm -v
```

Expected: 3 FAILs with `AttributeError: module 'stop_router' has no attribute 'check_static_rules'`

- [ ] **Step 3: Apply the code changes from Task 1** (if not already done)

- [ ] **Step 4: Run all three new tests — expect PASS**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py::test_static_rule_plan_selection_matches \
    tests/test_stop_router.py::test_static_rule_missing_term_returns_none \
    tests/test_stop_router.py::test_handle_stop_static_rule_exits_2_without_llm -v
```

Expected: 3 PASSes.

- [ ] **Step 5: Run the full test suite — expect no regressions**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add .claude_custom/hooks/stop_router.py .claude_custom/hooks/tests/test_stop_router.py
git commit -m "feat(hooks): short-circuit stop_router for plan-selection prompt via keyword match"
```
