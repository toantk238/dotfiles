# Stop Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `stop_reviewer.py` with `stop_router.py`, a unified Stop hook that auto-answers both "proceed?" prompts and clarifying questions Claude asks the user.

**Architecture:** A single Python script fired on every Stop event. It reads the session transcript, runs a danger check, classifies the stop (PROCEED / QUESTION / OTHER), and dispatches to the appropriate handler. Both handlers call `claude -p` with Haiku for AI decisions; all failures fall through to human.

**Tech Stack:** Python 3.14, pytest 9, subprocess, json, glob — all in `.claude/hooks/.venv`. No new dependencies.

---

## File Map

| Path | Status | Responsibility |
|---|---|---|
| `.claude/hooks/stop_router.py` | CREATE | Unified Stop hook — routing, classification, both handlers |
| `.claude/hooks/tests/__init__.py` | CREATE | Makes tests a package |
| `.claude/hooks/tests/test_stop_router.py` | CREATE | All unit tests |
| `.claude/hooks/stop_reviewer.py` | DELETE | Replaced by stop_router.py |
| `.claude/settings.json` | MODIFY | Update hook command path |

**Test runner:** `.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/ -v`

---

## Task 1: Transcript Parsing

**Files:**
- Create: `.claude/hooks/tests/__init__.py`
- Create: `.claude/hooks/tests/test_stop_router.py`
- Create: `.claude/hooks/stop_router.py` (skeleton + parsing functions only)

- [ ] **Step 1: Write the failing tests**

Create `.claude/hooks/tests/__init__.py` (empty file).

Create `.claude/hooks/tests/test_stop_router.py`:

```python
import json
import sys
from pathlib import Path

# Put hooks dir on path so we can import stop_router
sys.path.insert(0, str(Path(__file__).parent.parent))

import stop_router


# ── Fixtures ────────────────────────────────────────────────────────────────

def _write_transcript(tmp_path, lines: list[dict]) -> str:
    """Write a fake JSONL transcript, return a session_id whose glob will match."""
    session_id = "test-session-abc123"
    project_dir = tmp_path / ".claude" / "projects" / "myproject"
    project_dir.mkdir(parents=True)
    transcript = project_dir / f"{session_id}.jsonl"
    transcript.write_text("\n".join(json.dumps(l) for l in lines))
    # Patch the glob pattern used by the module
    stop_router._TRANSCRIPT_GLOB_TEMPLATE = str(
        tmp_path / ".claude" / "projects" / "*" / "{session_id}.jsonl"
    )
    return session_id


def _msg(role: str, text: str | list) -> dict:
    if isinstance(text, str):
        content = [{"type": "text", "text": text}]
    else:
        content = text
    return {"message": {"role": role, "content": content}}


# ── get_last_assistant_text ──────────────────────────────────────────────────

def test_get_last_assistant_text_basic(tmp_path):
    sid = _write_transcript(tmp_path, [
        _msg("user", "hello"),
        _msg("assistant", "first"),
        _msg("assistant", "second"),
    ])
    assert stop_router.get_last_assistant_text(sid) == "second"


def test_get_last_assistant_text_string_content(tmp_path):
    """content may be a plain string instead of a list of blocks."""
    sid = _write_transcript(tmp_path, [
        {"message": {"role": "assistant", "content": "plain string content"}},
    ])
    assert stop_router.get_last_assistant_text(sid) == "plain string content"


def test_get_last_assistant_text_skips_empty(tmp_path):
    sid = _write_transcript(tmp_path, [
        _msg("assistant", ""),
        _msg("assistant", "real text"),
    ])
    assert stop_router.get_last_assistant_text(sid) == "real text"


def test_get_last_assistant_text_no_transcript(tmp_path):
    stop_router._TRANSCRIPT_GLOB_TEMPLATE = str(tmp_path / "*.jsonl")
    assert stop_router.get_last_assistant_text("missing") is None


def test_get_last_assistant_text_no_assistant_msg(tmp_path):
    sid = _write_transcript(tmp_path, [
        _msg("user", "just a user message"),
    ])
    assert stop_router.get_last_assistant_text(sid) is None


# ── get_original_user_request ────────────────────────────────────────────────

def test_get_original_user_request_basic(tmp_path):
    sid = _write_transcript(tmp_path, [
        _msg("user", "original request"),
        _msg("assistant", "sure"),
        _msg("user", "second user message"),
    ])
    assert stop_router.get_original_user_request(sid) == "original request"


def test_get_original_user_request_string_content(tmp_path):
    sid = _write_transcript(tmp_path, [
        {"message": {"role": "user", "content": "plain user request"}},
    ])
    assert stop_router.get_original_user_request(sid) == "plain user request"


def test_get_original_user_request_no_transcript(tmp_path):
    stop_router._TRANSCRIPT_GLOB_TEMPLATE = str(tmp_path / "*.jsonl")
    assert stop_router.get_original_user_request("missing") is None
```

- [ ] **Step 2: Run the tests — verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'stop_router'` or similar import error.

- [ ] **Step 3: Create `stop_router.py` skeleton with parsing functions**

Create `.claude/hooks/stop_router.py`:

```python
#!/usr/bin/env python3
"""
Stop hook — unified router for proceed-detection and AI-assisted question answering.
Replaces stop_reviewer.py.
"""
import glob as _glob
import json
import os
import subprocess
import sys

from logger import get_logger

logger = get_logger("stop_router")

# Allows tests to patch the glob pattern
_TRANSCRIPT_GLOB_TEMPLATE = os.path.expanduser(
    "~/.claude/projects/*/{session_id}.jsonl"
)

PROCEED_SIGNALS = [
    "before i write the implementation plan",
    "before we move to the implementation plan",
    "let me know if you'd like any changes",
    "ready to proceed",
    "shall i proceed",
    "let me know if you want",
    "please review it before",
    "spec approved",
    "plan approved",
    "review complete",
    "would you like me to proceed",
    "let me know when you're ready",
    "if you'd like to proceed",
    "let me know if you want to make any changes",
    "let me know if you'd like to adjust",
    "any changes before i",
    "any adjustments before i",
]

DANGER_SIGNALS = [
    "delete",
    "remove",
    "drop table",
    "production",
    "deploy to",
    "are you sure",
    "irreversible",
    "cannot be undone",
    "permanently",
    "force push",
    "reset --hard",
]

QUESTION_SIGNALS = [
    "which option",
    "would you like",
    "do you want",
    "what would",
    "how would you",
    "which approach",
    "can you clarify",
]


def _extract_text(content) -> str:
    """Extract text from a content field that may be a list of blocks or a plain string."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts).strip()
    return ""


def _read_transcript(session_id: str) -> list[dict] | None:
    pattern = _TRANSCRIPT_GLOB_TEMPLATE.format(session_id=session_id)
    files = _glob.glob(pattern)
    if not files:
        return None
    entries = []
    try:
        with open(files[0]) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        logger.debug("Could not read transcript: %s", e)
        return None
    return entries


def get_last_assistant_text(session_id: str) -> str | None:
    entries = _read_transcript(session_id)
    if entries is None:
        return None
    for entry in reversed(entries):
        msg = entry.get("message", {})
        if msg.get("role") == "assistant":
            text = _extract_text(msg.get("content", ""))
            if text:
                return text
    return None


def get_original_user_request(session_id: str) -> str | None:
    entries = _read_transcript(session_id)
    if entries is None:
        return None
    for entry in entries:
        msg = entry.get("message", {})
        if msg.get("role") == "user":
            text = _extract_text(msg.get("content", ""))
            if text:
                return text
    return None


def main():
    pass  # implemented in later tasks


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/stop_router.py .claude/hooks/tests/__init__.py .claude/hooks/tests/test_stop_router.py
git commit -m "feat: add stop_router skeleton with transcript parsing and tests"
```

---

## Task 2: Classification Logic

**Files:**
- Modify: `.claude/hooks/tests/test_stop_router.py` (add tests)
- Modify: `.claude/hooks/stop_router.py` (add `classify_stop`)

- [ ] **Step 1: Add failing tests for `classify_stop`**

Append to `test_stop_router.py`:

```python
# ── classify_stop ────────────────────────────────────────────────────────────

def test_classify_proceed_signal():
    assert stop_router.classify_stop("ready to proceed with the plan?") == "PROCEED"


def test_classify_proceed_priority_over_question():
    # Message matches both PROCEED and QUESTION — PROCEED wins
    assert stop_router.classify_stop("shall i proceed? would you like me to?") == "PROCEED"


def test_classify_question_ends_with_question_mark():
    assert stop_router.classify_stop("What is the primary goal of this feature?") == "QUESTION"


def test_classify_question_signal():
    assert stop_router.classify_stop("Which approach would work best for your use case") == "QUESTION"


def test_classify_other():
    assert stop_router.classify_stop("Here is a summary of what I just did.") == "OTHER"


def test_classify_danger_check_not_in_classify():
    # classify_stop itself does NOT check danger — caller does that before invoking
    # A dangerous "proceed" still classifies as PROCEED
    assert stop_router.classify_stop("delete all files. ready to proceed?") == "PROCEED"


def test_has_danger_signal_true():
    assert stop_router.has_danger_signal("This action is irreversible") is True


def test_has_danger_signal_false():
    assert stop_router.has_danger_signal("Here is the plan ready to proceed") is False
```

- [ ] **Step 2: Run — verify tests fail**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py::test_classify_proceed_signal -v
```

Expected: `AttributeError: module 'stop_router' has no attribute 'classify_stop'`

- [ ] **Step 3: Implement `classify_stop` and `has_danger_signal` in `stop_router.py`**

Add after the signal list constants:

```python
def has_danger_signal(text: str) -> bool:
    t = text.lower()
    return any(sig in t for sig in DANGER_SIGNALS)


def classify_stop(text: str) -> str:
    """Return 'PROCEED', 'QUESTION', or 'OTHER'. Does not check danger signals."""
    t = text.lower()
    if any(sig in t for sig in PROCEED_SIGNALS):
        return "PROCEED"
    if text.rstrip().endswith("?") or any(sig in t for sig in QUESTION_SIGNALS):
        return "QUESTION"
    return "OTHER"
```

- [ ] **Step 4: Run — verify all tests pass**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py -v
```

Expected: all 17 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/stop_router.py .claude/hooks/tests/test_stop_router.py
git commit -m "feat: add classify_stop and has_danger_signal with tests"
```

---

## Task 3: Proceed Handler

**Files:**
- Modify: `.claude/hooks/tests/test_stop_router.py` (add tests)
- Modify: `.claude/hooks/stop_router.py` (add `proceed_handler` + `_reviewer_decide`)

- [ ] **Step 1: Add failing tests for proceed handler**

Append to `test_stop_router.py`:

```python
from unittest.mock import patch, MagicMock
import io

# ── proceed_handler ──────────────────────────────────────────────────────────

def _make_proc(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def test_reviewer_decide_returns_proceed(monkeypatch):
    with patch("stop_router.subprocess.run", return_value=_make_proc("Proceed")) as mock_run:
        result = stop_router._reviewer_decide("some text")
    assert result == "Proceed"
    mock_run.assert_called_once()


def test_reviewer_decide_returns_human_needed(monkeypatch):
    with patch("stop_router.subprocess.run", return_value=_make_proc("HUMAN_NEEDED")):
        result = stop_router._reviewer_decide("some text")
    assert result == "HUMAN_NEEDED"


def test_reviewer_decide_subprocess_exception():
    with patch("stop_router.subprocess.run", side_effect=Exception("boom")):
        result = stop_router._reviewer_decide("some text")
    assert result == "HUMAN_NEEDED"


def test_proceed_handler_injects_and_exits_2(capsys):
    with patch("stop_router.subprocess.run", return_value=_make_proc("Proceed")):
        with pytest.raises(SystemExit) as exc:
            stop_router.proceed_handler("ready to proceed?")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "additionalContext" in out["hookSpecificOutput"]
    assert "Proceed" in out["hookSpecificOutput"]["additionalContext"]


def test_proceed_handler_human_needed_exits_0():
    with patch("stop_router.subprocess.run", return_value=_make_proc("HUMAN_NEEDED")):
        with pytest.raises(SystemExit) as exc:
            stop_router.proceed_handler("ready to proceed?")
    assert exc.value.code == 0


def test_proceed_handler_empty_response_exits_0():
    with patch("stop_router.subprocess.run", return_value=_make_proc("")):
        with pytest.raises(SystemExit) as exc:
            stop_router.proceed_handler("ready to proceed?")
    assert exc.value.code == 0
```

Also add `import pytest` near the top of the test file (after the existing imports).

- [ ] **Step 2: Run — verify new tests fail**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py::test_reviewer_decide_returns_proceed -v
```

Expected: `AttributeError: module 'stop_router' has no attribute '_reviewer_decide'`

- [ ] **Step 3: Implement `_reviewer_decide` and `proceed_handler` in `stop_router.py`**

Add after `classify_stop`:

```python
def _reviewer_decide(text: str) -> str:
    """Call Haiku to decide whether to proceed or return HUMAN_NEEDED."""
    prompt = f"""You are an autonomous decision agent for a developer's coding assistant.
Claude has stopped and is waiting for a response. Decide the best action.

Claude's last message:
{text[:3000]}

Is this a simple "proceed to next step" situation (e.g. spec review done, plan ready, asking to continue)?
If yes, reply with the exact text the developer would type (usually just: Proceed).
If this requires human judgment (destructive action, unclear, important decision), reply with exactly: HUMAN_NEEDED

Reply with ONLY the response text or HUMAN_NEEDED.
"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001"],
            capture_output=True, text=True, timeout=20,
        )
        return result.stdout.strip()
    except Exception as e:
        logger.debug("_reviewer_decide exception: %s", e)
        return "HUMAN_NEEDED"


def proceed_handler(text: str) -> None:
    decision = _reviewer_decide(text)
    if not decision or decision == "HUMAN_NEEDED":
        logger.info("proceed_handler: human needed")
        sys.exit(0)
    context = (
        f'[stop_router] The developer\'s AI reviewer read your last message and responds: '
        f'"{decision}". Please continue accordingly.'
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }))
    sys.exit(2)
```

- [ ] **Step 4: Run — verify all tests pass**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py -v
```

Expected: all 23 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/stop_router.py .claude/hooks/tests/test_stop_router.py
git commit -m "feat: add proceed_handler with reviewer_decide and tests"
```

---

## Task 4: Question Handler

**Files:**
- Modify: `.claude/hooks/tests/test_stop_router.py` (add tests)
- Modify: `.claude/hooks/stop_router.py` (add `_parse_confidence_answer`, `question_handler`)

- [ ] **Step 1: Add failing tests for question handler**

Append to `test_stop_router.py`:

```python
# ── _parse_confidence_answer ─────────────────────────────────────────────────

def test_parse_high_confidence_with_answer():
    conf, ans = stop_router._parse_confidence_answer("CONFIDENCE: 90\nANSWER: Use option B.")
    assert conf == 90
    assert ans == "Use option B."


def test_parse_low_confidence_blank_answer():
    conf, ans = stop_router._parse_confidence_answer("CONFIDENCE: 60\nANSWER: ")
    assert conf == 60
    assert ans == ""


def test_parse_missing_confidence_line():
    assert stop_router._parse_confidence_answer("ANSWER: something") is None


def test_parse_non_integer_confidence():
    assert stop_router._parse_confidence_answer("CONFIDENCE: high\nANSWER: foo") is None


def test_parse_out_of_range_confidence():
    assert stop_router._parse_confidence_answer("CONFIDENCE: 150\nANSWER: foo") is None


def test_parse_missing_answer_line():
    assert stop_router._parse_confidence_answer("CONFIDENCE: 90") is None


def test_parse_whitespace_only_answer():
    # High confidence but whitespace answer → returns (90, "") which caller treats as blank
    conf, ans = stop_router._parse_confidence_answer("CONFIDENCE: 90\nANSWER:    ")
    assert conf == 90
    assert ans == ""


# ── question_handler ─────────────────────────────────────────────────────────

def test_question_handler_auto_answers(capsys):
    output = "CONFIDENCE: 85\nANSWER: Use option A, it matches your original request."
    with patch("stop_router.subprocess.run", return_value=_make_proc(output)):
        with pytest.raises(SystemExit) as exc:
            stop_router.question_handler("Which option?", "Build a REST API")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-answered" in out["hookSpecificOutput"]["additionalContext"]


def test_question_handler_low_confidence_exits_0():
    output = "CONFIDENCE: 50\nANSWER: "
    with patch("stop_router.subprocess.run", return_value=_make_proc(output)):
        with pytest.raises(SystemExit) as exc:
            stop_router.question_handler("Which option?", "Build a REST API")
    assert exc.value.code == 0


def test_question_handler_parse_failure_exits_0():
    with patch("stop_router.subprocess.run", return_value=_make_proc("garbage output")):
        with pytest.raises(SystemExit) as exc:
            stop_router.question_handler("Which option?", "Build a REST API")
    assert exc.value.code == 0


def test_question_handler_subprocess_exception_exits_0():
    with patch("stop_router.subprocess.run", side_effect=Exception("timeout")):
        with pytest.raises(SystemExit) as exc:
            stop_router.question_handler("Which option?", "Build a REST API")
    assert exc.value.code == 0
```

- [ ] **Step 2: Run — verify new tests fail**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py::test_parse_high_confidence_with_answer -v
```

Expected: `AttributeError: module 'stop_router' has no attribute '_parse_confidence_answer'`

- [ ] **Step 3: Implement `_parse_confidence_answer` and `question_handler` in `stop_router.py`**

Add after `proceed_handler`:

```python
def _parse_confidence_answer(output: str) -> tuple[int, str] | None:
    """
    Parse AI output for CONFIDENCE and ANSWER lines.
    Returns (confidence_int, answer_str) or None on any parse failure.
    answer_str is stripped; may be empty string (caller checks for blank).
    """
    confidence = None
    answer = None
    for line in output.splitlines():
        if line.startswith("CONFIDENCE:"):
            val = line[len("CONFIDENCE:"):].strip()
            try:
                confidence = int(val)
            except ValueError:
                return None
            if not (0 <= confidence <= 100):
                return None
        elif line.startswith("ANSWER:"):
            answer = line[len("ANSWER:"):].strip()
    if confidence is None:
        return None
    if answer is None:
        return None
    return confidence, answer


def question_handler(question_text: str, original_request: str) -> None:
    prompt = f"""You are an autonomous assistant helping a developer.

Original user request:
{original_request[:1000]}

Claude is now asking:
{question_text[:2000]}

Based ONLY on the original request, can you answer this question confidently?

Reply in this exact format:
CONFIDENCE: <integer 0-100>
ANSWER: <your answer text, or leave blank if confidence is below 80>

Rules:
- If CONFIDENCE >= 80, write a clear direct answer on the ANSWER line
- If CONFIDENCE < 80, leave the ANSWER line blank
- Never invent details not implied by the original request
- Keep answers concise (1-3 sentences max)
"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001"],
            capture_output=True, text=True, timeout=20,
        )
        output = result.stdout.strip()
    except Exception as e:
        logger.debug("question_handler subprocess exception: %s", e)
        sys.exit(0)

    parsed = _parse_confidence_answer(output)
    if parsed is None:
        logger.info("question_handler: parse failed — human needed")
        sys.exit(0)

    confidence, answer = parsed
    logger.info("question_handler: confidence=%d answer=%r", confidence, answer[:80] if answer else "")

    if confidence < 80 or not answer:
        logger.info("question_handler: low confidence or blank answer — human needed")
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": f'[stop_router] Auto-answered: "{answer}". Please continue accordingly.',
        }
    }))
    sys.exit(2)
```

- [ ] **Step 4: Run — verify all tests pass**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py -v
```

Expected: all 35 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/stop_router.py .claude/hooks/tests/test_stop_router.py
git commit -m "feat: add question_handler with confidence parsing and tests"
```

---

## Task 5: Main Router + Wiring

**Files:**
- Modify: `.claude/hooks/tests/test_stop_router.py` (add integration tests)
- Modify: `.claude/hooks/stop_router.py` (implement `main()`)

- [ ] **Step 1: Add failing integration tests for `main()`**

Append to `test_stop_router.py`:

```python
# ── main() integration ───────────────────────────────────────────────────────

def _run_main(tmp_path, hook_input: dict, transcript_lines: list[dict]):
    """Helper: write transcript, patch glob, run main() with hook_input on stdin."""
    import io
    sid = hook_input.get("session_id", "test-session-xyz")
    _write_transcript(tmp_path, transcript_lines)
    hook_input["session_id"] = sid
    with patch("sys.stdin", io.StringIO(json.dumps(hook_input))):
        stop_router.main()


def test_main_stop_hook_active_exits_0(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_main(tmp_path, {"stop_hook_active": True}, [_msg("assistant", "ready to proceed?")])
    assert exc.value.code == 0


def test_main_danger_signal_exits_0(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_main(tmp_path, {}, [_msg("assistant", "This will permanently delete all records. Shall we proceed?")])
    assert exc.value.code == 0


def test_main_other_classification_exits_0(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_main(tmp_path, {}, [_msg("assistant", "Here is a summary of what I did.")])
    assert exc.value.code == 0


def test_main_proceed_calls_proceed_handler(tmp_path, capsys):
    with patch("stop_router.subprocess.run", return_value=_make_proc("Proceed")):
        with pytest.raises(SystemExit) as exc:
            _run_main(tmp_path, {}, [_msg("assistant", "ready to proceed with the plan?")])
    assert exc.value.code == 2


def test_main_question_with_context_calls_question_handler(tmp_path, capsys):
    ai_output = "CONFIDENCE: 90\nANSWER: Go with option B."
    transcript = [
        _msg("user", "Build a CLI tool"),
        _msg("assistant", "Which option would you prefer, A or B?"),
    ]
    with patch("stop_router.subprocess.run", return_value=_make_proc(ai_output)):
        with pytest.raises(SystemExit) as exc:
            _run_main(tmp_path, {}, transcript)
    assert exc.value.code == 2


def test_main_question_without_original_request_exits_0(tmp_path):
    # Transcript has no user message → original_request is None → exit 0
    with pytest.raises(SystemExit) as exc:
        _run_main(tmp_path, {}, [_msg("assistant", "Which approach would you prefer?")])
    assert exc.value.code == 0
```

- [ ] **Step 2: Run — verify new tests fail**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py::test_main_stop_hook_active_exits_0 -v
```

Expected: the main() call returns without exiting (no SystemExit raised) — test fails.

- [ ] **Step 3: Implement `main()` in `stop_router.py`**

Replace the placeholder `main()`:

```python
def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Loop prevention
    if hook_input.get("stop_hook_active"):
        logger.debug("stop_hook_active=True, skipping")
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    if not session_id:
        sys.exit(0)

    last_text = get_last_assistant_text(session_id)
    if not last_text:
        logger.debug("No assistant text found")
        sys.exit(0)

    logger.debug("Last assistant text (first 200): %s", last_text[:200])

    # Danger check — before classification
    if has_danger_signal(last_text):
        logger.debug("Danger signal found — passing to human")
        sys.exit(0)

    stop_type = classify_stop(last_text)
    logger.info("stop_type=%s", stop_type)

    if stop_type == "PROCEED":
        proceed_handler(last_text)

    elif stop_type == "QUESTION":
        original_request = get_original_user_request(session_id)
        if original_request is None:
            logger.debug("No original request found — passing to human")
            sys.exit(0)
        question_handler(last_text, original_request)

    else:
        sys.exit(0)
```

- [ ] **Step 4: Run all tests — verify they all pass**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py -v
```

Expected: all 41 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/stop_router.py .claude/hooks/tests/test_stop_router.py
git commit -m "feat: implement main() router and integration tests"
```

---

## Task 6: Wire Up, Clean Up

**Files:**
- Modify: `.claude/settings.json`
- Delete: `.claude/hooks/stop_reviewer.py`

- [ ] **Step 1: Update `settings.json` hook command**

In `.claude/settings.json`, under `hooks → Stop → hooks[0]`, change the `command` value:

**Before:**
```json
"command": "zsh -c \"source ~/.env.zsh; ~/.claude/hooks/.venv/bin/python ~/.claude/hooks/stop_reviewer.py\""
```

**After:**
```json
"command": "zsh -c \"source ~/.env.zsh; ~/.claude/hooks/.venv/bin/python ~/.claude/hooks/stop_router.py\""
```

- [ ] **Step 2: Delete `stop_reviewer.py`**

```bash
rm .claude/hooks/stop_reviewer.py
```

- [ ] **Step 3: Run the full test suite one final time**

```bash
.claude/hooks/.venv/bin/python -m pytest .claude/hooks/tests/test_stop_router.py -v
```

Expected: all 41 tests PASS.

- [ ] **Step 4: Smoke-test that `stop_router.py` loads cleanly**

```bash
echo '{"session_id":"nosuchsession"}' | .claude/hooks/.venv/bin/python .claude/hooks/stop_router.py
echo "exit code: $?"
```

Expected: exit code 0 (no transcript found → safe fallback).

- [ ] **Step 5: Commit**

```bash
git add .claude/settings.json
git rm .claude/hooks/stop_reviewer.py
git add .claude/hooks/stop_router.py
git commit -m "feat: wire stop_router into settings.json and remove stop_reviewer"
```
