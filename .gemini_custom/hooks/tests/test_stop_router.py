import json
import sys
from pathlib import Path
import io
import pytest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import stop_router
import common
from stop_router import StopDecision


def _write_transcript(tmp_path, lines: list[dict]) -> str:
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


def test_handle_stop_proceed(capsys):
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_agy", return_value=output):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("ready to proceed?", "build a tool")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-approved" in out["hookSpecificOutput"]["additionalContext"]


def test_handle_stop_answer(capsys):
    output = "ACTION: ANSWER\nANSWER: Yes, do it."
    with patch("stop_router.call_agy", return_value=output):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("Should I?", "build a tool")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-answered: \"Yes, do it.\"" in out["hookSpecificOutput"]["additionalContext"]


def test_handle_stop_human_needed():
    output = "ACTION: HUMAN_NEEDED\nANSWER: "
    with patch("stop_router.call_agy", return_value=output):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("What color?", "build a tool")
    assert exc.value.code == 0


def test_handle_stop_call_agy_error():
    with patch("stop_router.call_agy", side_effect=Exception("timeout")):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("...", "...")
    assert exc.value.code == 0


def _run_main(transcript_path: str, extra_hook_input: dict | None = None):
    hook_input = {"transcript_path": transcript_path}
    if extra_hook_input:
        hook_input.update(extra_hook_input)
    with patch("sys.stdin", io.StringIO(json.dumps(hook_input))):
        stop_router.main()


def test_main_no_transcript_path_exits_0():
    with pytest.raises(SystemExit) as exc:
        with patch("sys.stdin", io.StringIO(json.dumps({}))):
            stop_router.main()
    assert exc.value.code == 0


def test_main_nonexistent_transcript_exits_0():
    with pytest.raises(SystemExit) as exc:
        with patch("sys.stdin", io.StringIO(json.dumps({"transcript_path": "/no/such/file.jsonl"}))):
            stop_router.main()
    assert exc.value.code == 0


def test_main_proceeds_with_valid_transcript(tmp_path):
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", "Shall I proceed?"),
    ])
    with patch("stop_router.call_agy", return_value="ACTION: PROCEED\nANSWER: "):
        with pytest.raises(SystemExit) as exc:
            _run_main(path)
    assert exc.value.code == 2


def test_prompt_contains_decision_tree_steps():
    assert "STEP 1" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 2" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 3" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 4" in stop_router.STOP_PROMPT_TEMPLATE
    assert "STEP 5" in stop_router.STOP_PROMPT_TEMPLATE


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


def test_repeat_check_uses_payload_not_stale_transcript(tmp_path):
    stale_text = "All done — no further action needed."
    new_text = "(No further action needed — waiting for your next request.)"
    path = _write_transcript(tmp_path, [
        _msg("user", "build a tool"),
        _msg("assistant", stale_text),
    ])
    session_id = "test-race-session"

    with patch("stop_router.call_agy", return_value="ACTION: PROCEED\nANSWER: "):
        with pytest.raises(SystemExit):
            _run_main(path, {"session_id": session_id, "last_assistant_message": stale_text})

    with patch("stop_router.call_agy", return_value="ACTION: PROCEED\nANSWER: "):
        with pytest.raises(SystemExit) as exc:
            _run_main(path, {"session_id": session_id, "last_assistant_message": new_text})

    assert exc.value.code == 2, "False repeat detection: payload text differed but stale transcript matched"


def test_main_static_rule_exits_2_without_llm(tmp_path, capsys):
    path = _write_transcript(tmp_path, [
        _msg("user", "build something"),
        _msg("assistant", _PLAN_MSG),
    ])
    with patch("stop_router.call_agy") as mock_llm:
        with pytest.raises(SystemExit) as exc:
            _run_main(path)
    assert exc.value.code == 2
    mock_llm.assert_not_called()
    out = json.loads(capsys.readouterr().out)
    assert "Subagent-Driven" in out["hookSpecificOutput"]["additionalContext"]
