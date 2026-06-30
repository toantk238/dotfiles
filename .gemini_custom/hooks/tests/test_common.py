import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from common import (
    call_agy,
    extract_text,
    get_last_assistant_message,
    get_original_user_request,
    read_transcript,
)


def test_call_agy_returns_stripped_stdout():
    mock_result = MagicMock()
    mock_result.stdout = "  APPROVE\n"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = call_agy("some prompt")
    assert result == "APPROVE"
    args, kwargs = mock_run.call_args
    assert args[0][0] == "agy"
    assert "--print" in args[0]


def test_call_agy_timeout_raises():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=60)):
        with pytest.raises(subprocess.TimeoutExpired):
            call_agy("prompt", timeout=60)


def test_call_agy_error_raises():
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "agy", stderr="err")):
        with pytest.raises(subprocess.CalledProcessError):
            call_agy("prompt")


def test_extract_text_string():
    assert extract_text("hello") == "hello"


def test_extract_text_list_of_blocks():
    blocks = [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]
    assert extract_text(blocks) == "hello world"


def test_extract_text_skips_non_text_blocks():
    blocks = [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "answer"}]
    assert extract_text(blocks) == "answer"


def test_extract_text_empty_list():
    assert extract_text([]) == ""


def test_get_original_user_request_basic(tmp_path):
    import json
    transcript = tmp_path / "s.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(e) for e in [
            {"message": {"role": "user", "content": [{"type": "text", "text": "original request"}]}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "sure"}]}},
            {"message": {"role": "user", "content": [{"type": "text", "text": "second user message"}]}},
        ]),
        encoding="utf-8",
    )
    assert get_original_user_request(str(transcript)) == "original request"


def test_get_original_user_request_no_file():
    assert get_original_user_request("/nonexistent/path.jsonl") is None


def test_get_last_assistant_message_basic(tmp_path):
    import json
    transcript = tmp_path / "s.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(e) for e in [
            {"message": {"role": "user", "content": [{"type": "text", "text": "do something"}]}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "first"}]}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "final"}]}},
        ]),
        encoding="utf-8",
    )
    assert get_last_assistant_message(str(transcript)) == "final"


def test_get_last_assistant_message_skips_thinking_blocks(tmp_path):
    import json
    transcript = tmp_path / "s.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": "Here is my answer"},
        ]}}),
        encoding="utf-8",
    )
    assert get_last_assistant_message(str(transcript)) == "Here is my answer"


def test_get_last_assistant_message_no_file():
    assert get_last_assistant_message("/nonexistent.jsonl") is None
