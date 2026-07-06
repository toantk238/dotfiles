import json
import sys
from pathlib import Path
import pytest
from unittest.mock import patch
import io

# Put hooks dir on path so we can import stop_router
sys.path.insert(0, str(Path(__file__).parent.parent))

import stop_router
import common
from stop_router import StopDecision


# ── Fixtures ────────────────────────────────────────────────────────────────

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


# ── get_original_user_request ────────────────────────────────────────────────

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


# ── get_last_assistant_message ──────────────────────────────────────────────

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


# ── parse_llm_output ───────────────────────────────────────────────────────

def test_parse_llm_output_proceed():
    decision = stop_router.parse_llm_output("ACTION: PROCEED\nANSWER: ")
    assert decision.action == "PROCEED"
    assert decision.answer == ""


def test_parse_llm_output_answer():
    decision = stop_router.parse_llm_output("ACTION: ANSWER\nANSWER: Use option B.")
    assert decision.action == "ANSWER"
    assert decision.answer == "Use option B."


def test_parse_llm_output_answer_next_line():
    decision = stop_router.parse_llm_output("ACTION: ANSWER\nANSWER:\nUse option B.")
    assert decision.action == "ANSWER"
    assert decision.answer == "Use option B."


def test_parse_llm_output_answer_multiline():
    decision = stop_router.parse_llm_output("ACTION: ANSWER\nANSWER:\nOption A for Issue 1.\nOption A for Issue 2.")
    assert decision.action == "ANSWER"
    assert decision.answer == "Option A for Issue 1. Option A for Issue 2."


def test_parse_llm_output_human_needed():
    decision = stop_router.parse_llm_output("ACTION: HUMAN_NEEDED\nANSWER: ")
    assert decision.action == "HUMAN_NEEDED"
    assert decision.answer == ""


def test_parse_llm_output_garbage():
    decision = stop_router.parse_llm_output("random text")
    assert decision.action == "HUMAN_NEEDED"
    assert decision.answer == ""


# ── handle_stop ─────────────────────────────────────────────────────────────

def test_handle_stop_proceed(capsys):
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("ready to proceed?", "build a tool")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-approved" in out["hookSpecificOutput"]["additionalContext"]


def test_handle_stop_answer(capsys):
    output = "ACTION: ANSWER\nANSWER: Yes, do it."
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("Should I?", "build a tool")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-answered: \"Yes, do it.\"" in out["hookSpecificOutput"]["additionalContext"]


def test_handle_stop_human_needed():
    output = "ACTION: HUMAN_NEEDED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("What color?", "build a tool")
    assert exc.value.code == 0


def test_handle_stop_call_claude_error():
    with patch("stop_router.call_claude", side_effect=Exception("timeout")):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("...", "...")
    assert exc.value.code == 0


# ── main() integration ────────────────────────────────────────────────────────

def _run_main(transcript_path: str, extra_hook_input: dict | None = None):
    """Run stop_router.main() with the given transcript_path in hook input."""
    hook_input = {"transcript_path": transcript_path}
    if extra_hook_input:
        hook_input.update(extra_hook_input)
    with patch("sys.stdin", io.StringIO(json.dumps(hook_input))):
        stop_router.main()


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


def test_main_proceeds_with_valid_transcript(tmp_path):
    """Valid transcript with PROCEED-worthy last message → exits 2."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", "Shall I proceed?"),
    ])
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            _run_main(path)
    assert exc.value.code == 2


def test_main_uses_transcript_message_not_payload_field(tmp_path):
    """Full message from transcript is used even when payload has a truncated version."""
    full_text = "FULL_SENTINEL: Shall I proceed with the implementation?"
    truncated = "TRUNCATED_SENTINEL: cut off here"
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


def test_main_falls_back_to_payload_when_transcript_has_no_assistant_turn(tmp_path):
    """If transcript has no assistant turn, fall back to last_assistant_message payload field."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        # no assistant turn written yet
    ])
    payload_text = "Shall I proceed with the plan?"
    captured_prompt = []

    def fake_claude(prompt, **kwargs):
        captured_prompt.append(prompt)
        return "ACTION: PROCEED\nANSWER: "

    with patch("stop_router.call_claude", side_effect=fake_claude):
        with pytest.raises(SystemExit) as exc:
            _run_main(path, {"last_assistant_message": payload_text})

    assert exc.value.code == 2
    assert payload_text in captured_prompt[0]


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


# ── Prompt content checks ────────────────────────────────────────────────────

def test_prompt_contains_decision_tree_steps():
    """New prompt must contain explicit STEP labels for the decision tree."""
    assert "STEP 1" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 2" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 3" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 4" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 5" in stop_router.STOP_PROMPT_TEMPLATE


def test_prompt_contains_human_needed_preference_guard():
    """Prompt must explicitly guard preference/approval questions → HUMAN_NEEDED."""
    assert "preference" in stop_router.STOP_PROMPT_TEMPLATE.lower() or \
           "does this look right" in stop_router.STOP_PROMPT_TEMPLATE.lower()


def test_handle_stop_multi_choice_clear_winner(capsys):
    """Multi-choice where LLM confidently picks an option → ANSWER."""
    llm_response = "ACTION: ANSWER\nANSWER: Option 2 (Subagent-Driven)"
    with patch("stop_router.call_claude", return_value=llm_response):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop(
                "Which approach?\n1. Inline\n2. Subagent-Driven\n3. Manual",
                "I want subagent-driven execution for isolation"
            )
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Option 2" in out["hookSpecificOutput"]["additionalContext"]


def test_handle_stop_human_directed_approval_question():
    """'Does this look right?' type question → LLM returns HUMAN_NEEDED → exit 0."""
    llm_response = "ACTION: HUMAN_NEEDED\nANSWER: "
    with patch("stop_router.call_claude", return_value=llm_response):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop(
                "Here is the design. Does this look right to you?",
                "design a system"
            )
    assert exc.value.code == 0


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
    assert "Option 1" in result
    assert "Subagent-Driven" in result


@pytest.mark.parametrize("missing_term", [
    "Plan complete and saved",
    "Subagent-Driven",
    "Inline Execution",
    "Which approach?",
])
def test_static_rule_missing_term_returns_none(missing_term):
    msg = _PLAN_MSG.replace(missing_term, "REMOVED")
    assert stop_router.check_static_rules(msg) is None


def test_repeat_check_uses_payload_not_stale_transcript(tmp_path):
    """Repeat detection must use payload last_assistant_message, not transcript.

    Scenario: hook fires twice for the same session. Between invocations Claude sent
    a new message, but the transcript hasn't been written yet. The transcript still
    returns the old message — if we use that for repeat detection we get a false positive.
    The payload field always reflects the current message and must be used instead.
    """
    stale_text = "All done — no further action needed."
    new_text = "(No further action needed — waiting for your next request.)"

    # Transcript only has the old (stale) message
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", stale_text),
    ])
    session_id = "test-race-session"

    # First invocation: stores stale_text in repeat-check state
    with patch("stop_router.call_claude", return_value="ACTION: PROCEED\nANSWER: "):
        with pytest.raises(SystemExit):
            _run_main(path, {"session_id": session_id, "last_assistant_message": stale_text})

    # Second invocation: transcript still returns stale_text, but payload has new_text.
    # Should NOT trigger repeat detection — must proceed, not exit 0.
    with patch("stop_router.call_claude", return_value="ACTION: PROCEED\nANSWER: "):
        with pytest.raises(SystemExit) as exc:
            _run_main(path, {"session_id": session_id, "last_assistant_message": new_text})

    assert exc.value.code == 2, "False repeat detection: payload text differed but stale transcript matched"


def test_main_static_rule_exits_2_without_llm(tmp_path, capsys):
    """Static rule in main() must short-circuit the LLM call and return Subagent-Driven."""
    path = _write_transcript(tmp_path, [
        _msg("user", "build something"),
        _msg("assistant", _PLAN_MSG),
    ])
    with patch("stop_router.call_claude") as mock_llm:
        with pytest.raises(SystemExit) as exc:
            _run_main(path)
    assert exc.value.code == 2
    mock_llm.assert_not_called()
    out = json.loads(capsys.readouterr().out)
    assert "Subagent-Driven" in out["hookSpecificOutput"]["additionalContext"]


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


def test_has_incomplete_tasks_malformed_update_input_not_dict(tmp_path):
    """A TaskUpdate block whose 'input' is present but not a dict must not raise.

    No well-formed TaskCreate/TaskUpdate is present, so once the malformed
    block is safely skipped there are no tracked task states at all.
    """
    path = _write_transcript(tmp_path, [
        {"message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_update_1", "name": "TaskUpdate",
             "input": "not-a-dict"},
        ]}},
    ])
    assert common.has_incomplete_tasks(path) is False


def test_has_incomplete_tasks_malformed_create_id_not_string(tmp_path):
    """A TaskCreate block whose 'id' is a non-string (unhashable) value must not raise."""
    path = _write_transcript(tmp_path, [
        {"message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": ["not", "a", "string"], "name": "TaskCreate",
             "input": {"subject": "Do the thing", "description": "Do the thing"}},
        ]}},
    ])
    assert common.has_incomplete_tasks(path) is False


def test_has_incomplete_tasks_malformed_update_status_unhashable(tmp_path):
    """A TaskUpdate block whose 'status' is a non-hashable value must not raise.

    The malformed entry is skipped in isolation; a genuinely incomplete task
    created afterward in a separate, well-formed entry must still be detected.
    """
    path = _write_transcript(tmp_path, [
        {"message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_update_1", "name": "TaskUpdate",
             "input": {"taskId": "1", "status": ["not", "hashable"]}},
        ]}},
        _task_create("toolu_2", "Task two"),
        _task_create_result("toolu_2", "2", "Task two"),
    ])
    assert common.has_incomplete_tasks(path) is True


def test_has_incomplete_tasks_malformed_tool_use_id_unhashable(tmp_path):
    """A tool_result block whose 'tool_use_id' is non-hashable must not raise.

    The malformed entry is skipped in isolation; a genuinely incomplete task
    created afterward in a separate, well-formed entry must still be detected.
    """
    path = _write_transcript(tmp_path, [
        {"message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": ["not", "hashable"],
             "content": "Task #99 created successfully: bogus"},
        ]}},
        _task_create("toolu_2", "Task two"),
        _task_create_result("toolu_2", "2", "Task two"),
    ])
    assert common.has_incomplete_tasks(path) is True


def test_has_incomplete_tasks_malformed_sibling_block_same_entry(tmp_path):
    """A malformed tool_result block must not shadow a valid sibling block
    in the SAME transcript entry (e.g. parallel tool calls produce one user
    turn with multiple tool_result blocks).

    The first block has a non-hashable 'tool_use_id' and would raise if
    processed; the second, well-formed block confirms a real TaskCreate for
    a task that is never updated, so it remains pending. Per-block (not
    per-entry) error isolation must still detect it.
    """
    path = _write_transcript(tmp_path, [
        _task_create("toolu_1", "Do the thing"),
        {"message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": ["not", "hashable"],
             "content": "Task #99 created successfully: bogus"},
            {"type": "tool_result", "tool_use_id": "toolu_1",
             "content": "Task #1 created successfully: Do the thing"},
        ]}},
    ])
    assert common.has_incomplete_tasks(path) is True


def test_has_incomplete_tasks_malformed_entry_not_dict(tmp_path):
    """A transcript line that parses to valid-but-non-dict JSON (e.g. a bare
    scalar) must not raise. The malformed entry is skipped in isolation; a
    genuinely incomplete task created afterward in a well-formed entry must
    still be detected.
    """
    transcript = tmp_path / "session.jsonl"
    lines = [
        "42",
        json.dumps(_task_create("toolu_1", "Do the thing")),
        json.dumps(_task_create_result("toolu_1", "1", "Do the thing")),
    ]
    transcript.write_text("\n".join(lines), encoding="utf-8")
    assert common.has_incomplete_tasks(str(transcript)) is True


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
