"""Common utilities for hooks."""
from dataclasses import dataclass
import json
import os
import re
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
            encoding="utf-8",
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


def get_last_assistant_message(transcript_path: str) -> str | None:
    """Return the text content of the last assistant turn in the transcript."""
    last_text = None
    for entry in read_transcript(transcript_path):
        msg = entry.get("message", {})
        if msg.get("role") == "assistant":
            text = extract_text(msg.get("content", ""))
            if text:
                last_text = text
    return last_text


_TASK_CREATED_RE = re.compile(r"Task #(\d+) created successfully")
_INCOMPLETE_TASK_STATUSES = {"pending", "in_progress"}


def has_incomplete_tasks(transcript_path: str) -> bool:
    """True if any task created in this transcript hasn't reached completed/deleted.

    Replays TaskCreate/TaskUpdate tool calls in order. Task ids are assigned
    monotonically and never reused within a session, so a single forward pass
    is sufficient. Any parsing failure is treated as "no incomplete tasks"
    (fail open) rather than raising.
    """
    states: dict[str, str] = {}
    pending_create_ids: set[str] = set()

    for entry in read_transcript(transcript_path):
        msg = entry.get("message", {})
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        role = msg.get("role")
        if role == "assistant":
            for block in content:
                try:
                    if not isinstance(block, dict):
                        continue
                    name = block.get("name")
                    if name == "TaskCreate":
                        block_id = block.get("id")
                        if isinstance(block_id, str):
                            pending_create_ids.add(block_id)
                    elif name == "TaskUpdate":
                        task_input = block.get("input", {})
                        if not isinstance(task_input, dict):
                            continue
                        task_id = str(task_input.get("taskId", ""))
                        status = task_input.get("status", "")
                        if task_id:
                            states[task_id] = status
                except Exception:
                    # Structural backstop: one malformed block must never
                    # abort processing of its sibling blocks in the same
                    # entry/turn. Skip it and keep replaying the rest so
                    # well-formed tasks elsewhere are still found.
                    continue
        elif role == "user":
            for block in content:
                try:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    if block.get("tool_use_id") not in pending_create_ids:
                        continue
                    text = extract_text(block.get("content", ""))
                    m = _TASK_CREATED_RE.search(text)
                    if m:
                        states.setdefault(m.group(1), "pending")
                except Exception:
                    # Structural backstop: one malformed block must never
                    # abort processing of its sibling blocks in the same
                    # entry/turn. Skip it and keep replaying the rest so
                    # well-formed tasks elsewhere are still found.
                    continue

    # A stored status can itself be malformed (e.g. non-hashable) even though
    # the entry that set it parsed without error. Guard the membership check
    # per-value so one bad status doesn't hide a genuinely incomplete task
    # recorded elsewhere in states.
    for status in states.values():
        try:
            if status in _INCOMPLETE_TASK_STATUSES:
                return True
        except Exception:
            continue
    return False
