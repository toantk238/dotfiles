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
