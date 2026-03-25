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


# ── get_original_user_request ────────────────────────────────────────────────

def test_get_original_user_request_basic(tmp_path):
    sid = _write_transcript(tmp_path, [
        _msg("user", "original request"),
        _msg("assistant", "sure"),
        _msg("user", "second user message"),
    ])
    assert stop_router.get_original_user_request(sid) == "original request"


# ── _parse_llm_output ───────────────────────────────────────────────────────

def test_parse_llm_output_proceed():
    action, answer = stop_router._parse_llm_output("ACTION: PROCEED\nANSWER: ")
    assert action == "PROCEED"
    assert answer == ""


def test_parse_llm_output_answer():
    action, answer = stop_router._parse_llm_output("ACTION: ANSWER\nANSWER: Use option B.")
    assert action == "ANSWER"
    assert answer == "Use option B."


def test_parse_llm_output_human_needed():
    action, answer = stop_router._parse_llm_output("ACTION: HUMAN_NEEDED\nANSWER: ")
    assert action == "HUMAN_NEEDED"
    assert answer == ""


def test_parse_llm_output_garbage():
    action, answer = stop_router._parse_llm_output("random text")
    assert action == "HUMAN_NEEDED"
    assert answer == ""


# ── handle_stop ─────────────────────────────────────────────────────────────

def _make_proc(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def test_handle_stop_proceed(capsys):
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.subprocess.run", return_value=_make_proc(output)):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("ready to proceed?", "build a tool")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-approved" in out["hookSpecificOutput"]["additionalContext"]


def test_handle_stop_answer(capsys):
    output = "ACTION: ANSWER\nANSWER: Yes, do it."
    with patch("stop_router.subprocess.run", return_value=_make_proc(output)):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("Should I?", "build a tool")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-answered: \"Yes, do it.\"" in out["hookSpecificOutput"]["additionalContext"]


def test_handle_stop_human_needed():
    output = "ACTION: HUMAN_NEEDED\nANSWER: "
    with patch("stop_router.subprocess.run", return_value=_make_proc(output)):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("What color?", "build a tool")
    assert exc.value.code == 0


def test_handle_stop_subprocess_error():
    with patch("stop_router.subprocess.run", side_effect=Exception("timeout")):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop("...", "...")
    assert exc.value.code == 0


def test_handle_stop_subagent_choice(capsys):
    last_text = "Two execution options:\n1. Subagent-Driven\n2. Inline Execution\nWhich approach?"
    output = "ACTION: ANSWER\nANSWER: 1"
    with patch("stop_router.subprocess.run", return_value=_make_proc(output)):
        with pytest.raises(SystemExit) as exc:
            stop_router.handle_stop(last_text, "build a tool")
    assert exc.value.code == 2
    out = json.loads(capsys.readouterr().out)
    assert "Auto-answered: \"1\"" in out["hookSpecificOutput"]["additionalContext"]


# ── main() integration ───────────────────────────────────────────────────────

def _run_main(tmp_path, hook_input: dict, transcript_lines: list[dict]):
    """Helper: write transcript, patch glob, run main() with hook_input on stdin."""
    sid = _write_transcript(tmp_path, transcript_lines)
    hook_input["session_id"] = hook_input.get("session_id", sid)
    hook_input["last_assistant_message"] = hook_input.get("last_assistant_message", "mock last message")
    with patch("sys.stdin", io.StringIO(json.dumps(hook_input))):
        stop_router.main()


def test_main_stop_hook_active_exits_0(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_main(tmp_path, {"stop_hook_active": True}, [_msg("user", "req")])
    assert exc.value.code == 0


def test_main_calls_handle_stop(tmp_path):
    output = "ACTION: PROCEED\nANSWER: "
    with patch("stop_router.subprocess.run", return_value=_make_proc(output)):
        with pytest.raises(SystemExit) as exc:
            _run_main(tmp_path, {}, [_msg("user", "original request")])
    assert exc.value.code == 2
