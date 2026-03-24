import json
import sys
from pathlib import Path

# Put hooks dir on path so we can import stop_router
sys.path.insert(0, str(Path(__file__).parent.parent))

import stop_router
import pytest
from unittest.mock import patch, MagicMock
import io


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


def test_reviewer_decide_nonzero_exit_returns_human_needed():
    with patch("stop_router.subprocess.run", return_value=_make_proc("", returncode=1)):
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


def test_question_handler_nonzero_exit_exits_0():
    with patch("stop_router.subprocess.run", return_value=_make_proc("", returncode=1)):
        with pytest.raises(SystemExit) as exc:
            stop_router.question_handler("Which option?", "Build a REST API")
    assert exc.value.code == 0


# ── main() integration ───────────────────────────────────────────────────────

def _run_main(tmp_path, hook_input: dict, transcript_lines: list[dict]):
    """Helper: write transcript, patch glob, run main() with hook_input on stdin."""
    sid = _write_transcript(tmp_path, transcript_lines)
    hook_input["session_id"] = hook_input.get("session_id", sid)
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
