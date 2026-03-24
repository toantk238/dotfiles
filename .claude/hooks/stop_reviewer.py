#!/usr/bin/env python3
"""
Stop hook — auto-review when Claude stops waiting for a "Proceed" type response.

If the last assistant message looks like a low-stakes "ready to continue?" prompt
(e.g. spec review complete, plan ready), an AI reviewer answers automatically.

Mechanism: asyncRewake=true. Exit code 2 + additionalContext wakes the model.
The stop_hook_active flag prevents infinite loops.
"""
import glob
import json
import os
import subprocess
import sys

from logger import get_logger

logger = get_logger("stop_reviewer")

# Patterns in the last assistant message that suggest a "proceed?" wait
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

# Patterns that require human judgment — do not auto-proceed
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


def get_last_assistant_text(session_id: str) -> str | None:
    """Find the session transcript and return the last assistant text."""
    pattern = os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl")
    files = glob.glob(pattern)
    if not files:
        logger.debug("No transcript found for session %s", session_id)
        return None

    try:
        with open(files[0]) as f:
            lines = f.readlines()
    except Exception as e:
        logger.debug("Could not read transcript: %s", e)
        return None

    for line in reversed(lines):
        try:
            entry = json.loads(line.strip())
        except Exception:
            continue

        message = entry.get("message", {})
        if message.get("role") == "assistant":
            text_parts = []
            for block in message.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            text = " ".join(text_parts).strip()
            if text:
                return text

    return None


def should_auto_proceed(text: str) -> bool:
    t = text.lower()
    if any(sig in t for sig in DANGER_SIGNALS):
        logger.debug("Danger signal found, skipping auto-proceed")
        return False
    return any(sig in t for sig in PROCEED_SIGNALS)


def reviewer_decide(text: str) -> str:
    prompt = f"""You are an autonomous decision agent for a developer's coding assistant.
Claude has stopped and is waiting for a response. Decide the best action.

Claude's last message:
{text[:3000]}

Is this a simple "proceed to next step" situation (e.g. spec review done, plan ready, asking to continue)?
If yes, reply with the exact text the developer would type (usually just: Proceed).
If this requires human judgment (destructive action, unclear, important decision), reply with exactly: HUMAN_NEEDED

Reply with ONLY the response text or HUMAN_NEEDED.
"""
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", "claude-haiku-4-5"],
        capture_output=True, text=True, timeout=20,
    )
    return result.stdout.strip()


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Prevent infinite loops — if we already auto-proceeded this stop cycle, skip
    if hook_input.get("stop_hook_active"):
        logger.debug("stop_hook_active=True, skipping to avoid loop")
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    if not session_id:
        sys.exit(0)

    last_text = get_last_assistant_text(session_id)
    if not last_text:
        logger.debug("No assistant text found")
        sys.exit(0)

    logger.debug("Last assistant text (first 200): %s", last_text[:200])

    if not should_auto_proceed(last_text):
        logger.debug("No proceed signals — human will answer")
        sys.exit(0)

    decision = reviewer_decide(last_text)
    logger.info("stop_reviewer decision=%r", decision[:100])

    if not decision or decision == "HUMAN_NEEDED":
        logger.info("Reviewer says human needed")
        sys.exit(0)

    context = (
        f"[stop_reviewer] The developer's AI reviewer read your last message and responds: "
        f'"{decision}". Please continue accordingly.'
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }))
    sys.exit(2)  # asyncRewake: exit code 2 wakes the model


if __name__ == "__main__":
    main()
