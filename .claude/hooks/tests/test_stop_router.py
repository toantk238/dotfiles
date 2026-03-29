import json
import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
import io

# Put hooks dir on path so we can import stop_router
sys.path.insert(0, str(Path(__file__).parent.parent))

import stop_router
import common
from stop_router import StopDecision


# ── Fixtures ────────────────────────────────────────────────────────────────

def _write_transcript(tmp_path, lines: list[dict]) -> str:
    """Write a fake JSONL transcript, return a session_id whose glob will match."""
    session_id = "test-session-abc123"
    project_dir = tmp_path / ".claude" / "projects" / "myproject"
    project_dir.mkdir(parents=True)
    transcript = project_dir / f"{session_id}.jsonl"
    transcript.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")
    
    # Patch the glob pattern in common
    patcher = patch("common.os.path.expanduser")
    mock_expand = patcher.start()
    mock_expand.return_value = str(
        tmp_path / ".claude" / "projects" / "*" / f"{session_id}.jsonl"
    )
    return session_id


def _msg(role: str, text: str | list) -> dict:
    if isinstance(text, str):
        content = [{"type": "text", "text": text}]
    else:
        content = text
    return {"message": {"role": role, "content": content}}


# ── get_original_user_request ────────────────────────────────────────────────

def test_get_original_user_request_basic(tmp_path):
    sid = _write_transcript(tmp_path, [
        _msg("user", "original request"),
        _msg("assistant", "sure"),
        _msg("user", "second user message"),
    ])
    # Need to patch common because that's where it's defined now
    with patch("common.os.path.expanduser", return_value=str(tmp_path / ".claude" / "projects" / "myproject" / f"{sid}.jsonl")):
        assert common.get_original_user_request(sid) == "original request"


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


# ── main() integration ───────────────────────────────────────────────────────

def _run_main(tmp_path, hook_input: dict, transcript_lines: list[dict]):
    """Helper: write transcript, patch glob, run main() with hook_input on stdin."""
    sid = _write_transcript(tmp_path, transcript_lines)
    hook_input["session_id"] = hook_input.get("session_id", sid)
    hook_input["last_assistant_message"] = hook_input.get("last_assistant_message", "mock last message")
    
    with patch("sys.stdin", io.StringIO(json.dumps(hook_input))):
        # We also need to patch get_original_user_request because it uses glob
        with patch("stop_router.get_original_user_request", return_value=transcript_lines[0]["message"]["content"][0]["text"]):
            stop_router.main()


def test_main_stop_hook_active_exits_0(tmp_path):
    with pytest.raises(SystemExit) as exc:
        with patch("sys.stdin", io.StringIO(json.dumps({"stop_hook_active": True}))):
            stop_router.main()
    assert exc.value.code == 0


def test_main_calls_handle_stop(tmp_path):
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.call_claude", return_value=output):
        with pytest.raises(SystemExit) as exc:
            _run_main(tmp_path, {}, [_msg("user", "original request")])
    assert exc.value.code == 2
