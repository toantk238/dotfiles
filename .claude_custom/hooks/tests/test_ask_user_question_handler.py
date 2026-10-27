import json
import sys
from pathlib import Path
from unittest.mock import patch

# Put hooks dir on path so we can import ask_user_question_handler
sys.path.insert(0, str(Path(__file__).parent.parent))

import ask_user_question_handler as handler
import common

QUESTIONS = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "SQLite"}]}]
GOOD = json.dumps({"answers": {"Which db?": "Postgres"}})


def test_ask_model_returns_complete_answers():
    with patch("ask_user_question_handler.call_claude", return_value=GOOD):
        assert handler.ask_model("p", QUESTIONS, common.HAIKU_MODEL, 30) == {"Which db?": "Postgres"}


def test_ask_model_missing_answer_returns_none():
    with patch("ask_user_question_handler.call_claude", return_value='{"answers": {}}'):
        assert handler.ask_model("p", QUESTIONS, common.HAIKU_MODEL, 30) is None


def test_ask_model_error_returns_none():
    with patch("ask_user_question_handler.call_claude", side_effect=Exception("timeout")):
        assert handler.ask_model("p", QUESTIONS, common.HAIKU_MODEL, 30) is None


def test_build_extra_context_includes_recent_turns_and_last_message(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in [
        {"timestamp": "t1", "message": {"role": "user", "content": "we use Postgres"}},
        {"message": {"role": "assistant", "content": [{"type": "text", "text": "Picking storage"}]}},
    ]))
    extra = handler.build_extra_context(str(transcript))
    assert "we use Postgres" in extra
    assert "Picking storage" in extra
