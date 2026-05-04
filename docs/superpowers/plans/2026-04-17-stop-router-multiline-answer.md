# stop_router Multi-line ANSWER Parsing + Debug Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `parse_llm_output()` to capture ANSWER values that span multiple lines, and add debug logging of the raw LLM response and parsed result.

**Architecture:** Replace the single-line `ANSWER:` capture with a state-machine loop that collects all subsequent non-empty lines after seeing `ANSWER:`. Add two `logger.debug()` calls — one before parsing (raw output) and one after (parsed result with `repr()`).

**Tech Stack:** Python 3.11+, pytest (existing suite in `.claude_custom/hooks/tests/`)

---

### Task 1: Fix `parse_llm_output()` and add debug logging

**Files:**
- Modify: `.claude_custom/hooks/stop_router.py:87-97`
- Test: `.claude_custom/hooks/tests/test_stop_router.py`

- [ ] **Step 1: Write two new failing tests**

Add these two tests directly after `test_parse_llm_output_answer` (after line 118) in `tests/test_stop_router.py`:

```python
def test_parse_llm_output_answer_next_line():
    decision = stop_router.parse_llm_output("ACTION: ANSWER\nANSWER:\nUse option B.")
    assert decision.action == "ANSWER"
    assert decision.answer == "Use option B."


def test_parse_llm_output_answer_multiline():
    decision = stop_router.parse_llm_output("ACTION: ANSWER\nANSWER:\nOption A for Issue 1.\nOption A for Issue 2.")
    assert decision.action == "ANSWER"
    assert decision.answer == "Option A for Issue 1. Option A for Issue 2."
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py::test_parse_llm_output_answer_next_line tests/test_stop_router.py::test_parse_llm_output_answer_multiline -v
```

Expected: 2 FAILs — `assert "" == "Use option B."` and similar.

- [ ] **Step 3: Replace `parse_llm_output()` in `stop_router.py`**

Replace lines 87–97 (the entire function) with:

```python
def parse_llm_output(output: str) -> StopDecision:
    """Parse AI output for ACTION and ANSWER lines. ANSWER may span multiple lines."""
    logger.debug(f"LLM raw output:\n{output}")
    action = "HUMAN_NEEDED"
    answer_lines: list[str] = []
    in_answer = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ACTION:"):
            action = stripped[len("ACTION:"):].strip().upper()
            in_answer = False
        elif stripped.startswith("ANSWER:"):
            answer_lines = [stripped[len("ANSWER:"):].strip()]
            in_answer = True
        elif in_answer and stripped:
            answer_lines.append(stripped)
    answer = " ".join(part for part in answer_lines if part).strip()
    logger.debug(f"Parsed → action={action} answer={answer!r}")
    return StopDecision(action=action, answer=answer)
```

- [ ] **Step 4: Run new tests — expect PASS**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py::test_parse_llm_output_answer_next_line tests/test_stop_router.py::test_parse_llm_output_answer_multiline -v
```

Expected: 2 PASSes.

- [ ] **Step 5: Run full test suite — expect no regressions**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/.claude_custom/hooks
.venv/bin/pytest tests/test_stop_router.py -v
```

Expected: all tests PASS (33 total).

- [ ] **Step 6: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add .claude_custom/hooks/stop_router.py .claude_custom/hooks/tests/test_stop_router.py
git commit -m "fix(hooks): parse multi-line ANSWER in stop_router, add debug logging"
```
