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
