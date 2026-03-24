#!/usr/bin/env python3
"""
Stop hook — unified router for proceed-detection and AI-assisted question answering.
Replaces stop_reviewer.py.
"""
import glob as _glob
import json
import os
import subprocess
import sys

from logger import get_logger

logger = get_logger("stop_router")

# Allows tests to patch the glob pattern
_TRANSCRIPT_GLOB_TEMPLATE = os.path.expanduser(
    "~/.claude/projects/*/{session_id}.jsonl"
)

PROCEED_SIGNALS = [
    "before i write the implementation plan",
    "before we move to the implementation plan",
    "let me know if you'd like any changes",
    "ready to proceed",
    "shall i proceed",
    "let me know if you want",
    "please review it before",
    "spec approved",
    "plan approved",
    "review complete",
    "would you like me to proceed",
    "let me know when you're ready",
    "if you'd like to proceed",
    "let me know if you want to make any changes",
    "let me know if you'd like to adjust",
    "any changes before i",
    "any adjustments before i",
]

DANGER_SIGNALS = [
    "delete",
    "remove",
    "drop table",
    "production",
    "deploy to",
    "are you sure",
    "irreversible",
    "cannot be undone",
    "permanently",
    "force push",
    "reset --hard",
]

QUESTION_SIGNALS = [
    "which option",
    "would you like",
    "do you want",
    "what would",
    "how would you",
    "which approach",
    "can you clarify",
]


def has_danger_signal(text: str) -> bool:
    t = text.lower()
    return any(sig in t for sig in DANGER_SIGNALS)


def classify_stop(text: str) -> str:
    """Return 'PROCEED', 'QUESTION', or 'OTHER'. Does not check danger signals."""
    t = text.lower()
    if any(sig in t for sig in PROCEED_SIGNALS):
        return "PROCEED"
    if text.rstrip().endswith("?") or any(sig in t for sig in QUESTION_SIGNALS):
        return "QUESTION"
    return "OTHER"


def _reviewer_decide(text: str) -> str:
    """Call Haiku to decide whether to proceed or return HUMAN_NEEDED."""
    prompt = f"""You are an autonomous decision agent for a developer's coding assistant.
Claude has stopped and is waiting for a response. Decide the best action.

Claude's last message:
{text[:3000]}

Is this a simple "proceed to next step" situation (e.g. spec review done, plan ready, asking to continue)?
If yes, reply with the exact text the developer would type (usually just: Proceed).
If this requires human judgment (destructive action, unclear, important decision), reply with exactly: HUMAN_NEEDED

Reply with ONLY the response text or HUMAN_NEEDED.
"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001"],
            capture_output=True, text=True, timeout=20,
        )
        return result.stdout.strip()
    except Exception as e:
        logger.debug("_reviewer_decide exception: %s", e)
        return "HUMAN_NEEDED"


def proceed_handler(text: str) -> None:
    decision = _reviewer_decide(text)
    if not decision or decision == "HUMAN_NEEDED":
        logger.info("proceed_handler: human needed")
        sys.exit(0)
    context = (
        f'[stop_router] The developer\'s AI reviewer read your last message and responds: '
        f'"{decision}". Please continue accordingly.'
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }))
    sys.exit(2)


def _extract_text(content) -> str:
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


def _read_transcript(session_id: str) -> list[dict] | None:
    pattern = _TRANSCRIPT_GLOB_TEMPLATE.format(session_id=session_id)
    files = _glob.glob(pattern)
    if not files:
        return None
    entries = []
    try:
        with open(files[0]) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        logger.debug("Could not read transcript: %s", e)
        return None
    return entries


def get_last_assistant_text(session_id: str) -> str | None:
    entries = _read_transcript(session_id)
    if entries is None:
        return None
    for entry in reversed(entries):
        msg = entry.get("message", {})
        if msg.get("role") == "assistant":
            text = _extract_text(msg.get("content", ""))
            if text:
                return text
    return None


def get_original_user_request(session_id: str) -> str | None:
    entries = _read_transcript(session_id)
    if entries is None:
        return None
    for entry in entries:
        msg = entry.get("message", {})
        if msg.get("role") == "user":
            text = _extract_text(msg.get("content", ""))
            if text:
                return text
    return None


def main():
    pass  # implemented in later tasks


if __name__ == "__main__":
    main()
