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


# Fast, cheap first pass for every hook decision.
HAIKU_MODEL = "claude-haiku-5-5"
# Escalation model, used with more context when Haiku defers to the human.
OPUS_MODEL = "claude-opus-5-5"


# A hook's model call needs no tools, MCP servers, skills or hooks; skipping them
# halves its start-up time and keeps the nested session from re-running these hooks.
# (--bare would be leaner still but skips the keychain, breaking claude.ai login.)
_LEAN_SESSION_ARGS = [
    "--settings", json.dumps({"disableAllHooks": True}),
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--tools", "",
]


def call_claude(prompt: str, model: str = HAIKU_MODEL, timeout: int = 60) -> str:
    """Call the claude CLI with a prompt and return the stdout."""
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", model, "--no-session-persistence",
             *_LEAN_SESSION_ARGS],
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
                    val = json.loads(line)
                    if isinstance(val, dict):
                        yield val
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Could not read transcript: {e}")
        return


def get_original_user_request(transcript_path: str) -> str | None:
    """The first message the human actually typed in the transcript.

    Skips slash-command plumbing such as the `/clear` caveat that otherwise opens
    a session as its first "user" entry.
    """
    for _ts, text in iter_human_user_turns(transcript_path):
        return text
    return None


_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

# Prefixes that mark a "user" transcript entry as machine-generated rather than
# something the human actually typed (slash-command plumbing, hook output, ...).
_SYNTHETIC_USER_PREFIXES = (
    "<local-command-caveat>",
    "<command-name>", "<command-message>", "<command-args>",
    "<local-command-stdout>", "<local-command-stderr>",
    "<bash-input>", "<bash-stdout>", "<bash-stderr>",
    "<user-prompt-submit-hook>", "<task-notification>",
    "Caveat:", "[Request interrupted", "Stop hook feedback:",
)


def _queued_human_prompt(entry: dict) -> str:
    """Text of a message the human typed while Claude was mid-turn, else "".

    Those land as `attachment` entries of type `queued_command`, not as user messages.
    """
    attachment = entry.get("attachment")
    if entry.get("type") != "attachment" or not isinstance(attachment, dict):
        return ""
    if attachment.get("type") != "queued_command":
        return ""
    origin = attachment.get("origin")
    if not isinstance(origin, dict) or origin.get("kind") != "human":
        return ""
    prompt = attachment.get("prompt")
    return prompt.strip() if isinstance(prompt, str) else ""


def _human_turn_text(entry: dict) -> str:
    """The text of a turn the human actually typed, or "" for anything else.

    Skips tool results, sidechain (subagent) entries, meta entries and the
    synthetic `<command-*>` / hook plumbing that also lands in the transcript
    with role="user".
    """
    if entry.get("isMeta") or entry.get("isSidechain"):
        return ""
    queued = _queued_human_prompt(entry)
    if queued:
        return queued
    msg = entry.get("message", {})
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return ""
    content = msg.get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return ""
    text = _SYSTEM_REMINDER_RE.sub("", extract_text(content)).strip()
    if not text or text.startswith(_SYNTHETIC_USER_PREFIXES):
        return ""
    return text


def iter_human_user_turns(transcript_path: str) -> Iterator[tuple[str, str]]:
    """Yield (timestamp, text) for transcript turns the human actually typed.
    Timestamps are the raw ISO strings from the transcript ("" when absent).
    """
    for entry in read_transcript(transcript_path):
        text = _human_turn_text(entry)
        if text:
            yield str(entry.get("timestamp", "")), text


def get_recent_user_turns(transcript_path: str, limit: int = 5) -> list[tuple[str, str]]:
    """The last `limit` human-typed turns, oldest first."""
    turns = list(iter_human_user_turns(transcript_path))
    return turns[-limit:] if limit > 0 else turns


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


def ignored_hook_feedback_streak(transcript_path: str) -> int:
    """How many "Stop hook feedback" replies in a row, up to the latest, Claude answered
    without a tool call (words only). 0 when Claude acted on the latest one, or none was sent
    since the human's last message."""
    streak = 0
    for entry in read_transcript(transcript_path):
        msg = entry.get("message") or {}
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if msg.get("role") == "user" and extract_text(content).startswith("Stop hook feedback:"):
            streak += 1
        elif _human_turn_text(entry) or (
                msg.get("role") == "assistant" and isinstance(content, list) and
                any(isinstance(c, dict) and c.get("type") == "tool_use" for c in content)):
            streak = 0
    return streak


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
        if not isinstance(entry, dict):
            continue
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
