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
