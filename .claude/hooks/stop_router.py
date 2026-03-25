#!/usr/bin/env python3
"""
Stop hook — unified router for proceed-detection and AI-assisted question answering.
Uses a single LLM call to decide the action.
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


def _parse_llm_output(output: str) -> tuple[str, str]:
    """
    Parse AI output for ACTION and ANSWER lines.
    Returns (action, answer).
    """
    action = "HUMAN_NEEDED"
    answer = ""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("ACTION:"):
            action = line[len("ACTION:"):].strip().upper()
        elif line.startswith("ANSWER:"):
            answer = line[len("ANSWER:"):].strip()
    return action, answer


def handle_stop(last_text: str, original_request: str) -> None:
    prompt = f"""You are an autonomous decision agent for a developer's coding assistant.
Claude (the assistant) has stopped and is waiting for input.

Original user request:
{original_request[:1000]}

Claude's last message:
{last_text[:2000]}

Analyze the situation and decide the best action:
1. If Claude is asking for permission to proceed with a plan, implementation, or next step (e.g., "Shall I proceed?", "Ready to start?", "Let me know if this looks good"), the action is PROCEED.
2. If Claude is asking a clarifying question that you can answer with 100% confidence based ONLY on the original request, the action is ANSWER.
3. If Claude presents execution options (e.g., "Subagent-Driven" vs "Inline Execution"), ALWAYS choose "Subagent-Driven" (Option 1). The action is ANSWER.
4. Otherwise (dangerous operation, complex choice, unclear intent, or low confidence), the action is HUMAN_NEEDED.

Reply in this exact format:
ACTION: <PROCEED | ANSWER | HUMAN_NEEDED>
ANSWER: <your concise answer if ACTION is ANSWER, otherwise leave blank>
"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001", "--no-session-persistence"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            logger.debug("LLM non-zero exit: %d stderr: %s", result.returncode, result.stderr)
            sys.exit(0)
        output = result.stdout.strip()
    except Exception as e:
        logger.debug("LLM subprocess exception: %s", e)
        sys.exit(0)

    action, answer = _parse_llm_output(output)
    logger.info("Decision: action=%s answer=%r", action, answer[:80] if answer else "")

    if action == "PROCEED":
        context = '[stop_router] Auto-approved: "Proceed". Please continue accordingly.'
    elif action == "ANSWER" and answer:
        context = f'[stop_router] Auto-answered: "{answer}". Please continue accordingly.'
    else:
        logger.info("Passing to human (action=%s)", action)
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }))
    sys.exit(2)


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    logger.debug(f"input = {json.dumps(hook_input, indent=2)}")

    if hook_input.get("stop_hook_active"):
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    last_text = hook_input.get("last_assistant_message")

    if not session_id or not last_text:
        sys.exit(0)

    original_request = get_original_user_request(session_id)
    if not original_request:
        sys.exit(0)

    handle_stop(last_text, original_request)


if __name__ == "__main__":
    main()
