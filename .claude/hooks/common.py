"""Common utilities for hooks."""
from dataclasses import dataclass
import json
import os
import subprocess
import sys
from typing import Any, Iterator

from logger import get_logger

logger = get_logger("common")


@dataclass(frozen=True)
class HookInput:
    """Standard input for hooks."""
    data: dict[str, Any]

    @classmethod
    def from_stdin(cls) -> "HookInput":
        try:
            return cls(json.load(sys.stdin))
        except (json.JSONDecodeError, EOFError):
            return cls({})

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


def call_claude(prompt: str, model: str = "claude-haiku-4-5-20251001", timeout: int = 60) -> str:
    """Call the claude CLI with a prompt and return the stdout."""
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", model, "--no-session-persistence"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Claude CLI error (exit {e.returncode}): {e.stderr}")
        raise
    except subprocess.TimeoutExpired:
        logger.error(f"Claude CLI timed out after {timeout}s")
        raise
    except Exception as e:
        logger.error(f"Failed to call Claude CLI: {e}")
        raise


def extract_text(content: Any) -> str:
    """Extract text from a content field that may be a list of blocks or a plain string."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts).strip()
    return ""


def read_transcript(transcript_path: str) -> Iterator[dict[str, Any]]:
    """Read transcript from a given file path, yielding parsed JSONL entries."""
    if not transcript_path or not os.path.exists(transcript_path):
        return
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Could not read transcript: {e}")
        return


def get_original_user_request(transcript_path: str) -> str | None:
    """Find the first user message in the transcript at the given path."""
    for entry in read_transcript(transcript_path):
        msg = entry.get("message", {})
        if msg.get("role") == "user":
            text = extract_text(msg.get("content", ""))
            if text:
                return text
    return None
