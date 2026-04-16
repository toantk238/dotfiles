#!/usr/bin/env python3
"""
Stop hook — unified router for proceed-detection and AI-assisted question answering.
Uses a single LLM call to decide the action.
"""
from dataclasses import dataclass
import json
import os
import sys

from common import HookInput, call_claude, get_original_user_request, get_last_assistant_message
from logger import get_logger

logger = get_logger("stop_router")


@dataclass(frozen=True)
class StopDecision:
    """The decision result of the stop hook."""
    action: str
    answer: str = ""


STOP_PROMPT_TEMPLATE = """You are an autonomous decision agent for a developer's coding assistant.
Claude (the assistant) has stopped and is waiting for input.

Original user request:
{original_request}

Claude's last message:
{last_text}

Analyze the situation and decide the best action:
1. If Claude is asking for permission to proceed with a plan, implementation, or next step (e.g., "Shall I proceed?", "Ready to start?", "Let me know if this looks good"), the action is PROCEED.
2. If Claude is asking a clarifying question that you can answer with 100% confidence based ONLY on the original request, the action is ANSWER.
3. If Claude presents execution options (e.g., "Subagent-Driven" vs "Inline Execution"), ALWAYS choose "Subagent-Driven" (Option 1). The action is ANSWER.
4. Otherwise (dangerous operation, complex choice, unclear intent, or low confidence), the action is HUMAN_NEEDED.

Reply in this exact format:
ACTION: <PROCEED | ANSWER | HUMAN_NEEDED>
ANSWER: <your concise answer if ACTION is ANSWER, otherwise leave blank>
"""


def parse_llm_output(output: str) -> StopDecision:
    """Parse AI output for ACTION and ANSWER lines."""
    action = "HUMAN_NEEDED"
    answer = ""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("ACTION:"):
            action = line[len("ACTION:"):].strip().upper()
        elif line.startswith("ANSWER:"):
            answer = line[len("ANSWER:"):].strip()
    return StopDecision(action=action, answer=answer)


def handle_stop(last_text: str, original_request: str) -> None:
    prompt = STOP_PROMPT_TEMPLATE.format(
        original_request=original_request[:1000],
        last_text=last_text[:2000]
    )

    try:
        output = call_claude(prompt, timeout=30)
    except Exception as e:
        logger.warning(f"LLM call failed, falling back to human: {e}")
        sys.exit(0)

    decision = parse_llm_output(output)
    logger.info(f"Decision: action={decision.action} answer={decision.answer[:80] if decision.answer else ''}")

    context = ""
    if decision.action == "PROCEED":
        context = '[stop_router] Auto-approved: "Proceed". Please continue accordingly.'
    elif decision.action == "ANSWER" and decision.answer:
        context = f'[stop_router] Auto-answered: "{decision.answer}". Please continue accordingly.'
    else:
        logger.info(f"Passing to human (action={decision.action})")
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }))
    sys.exit(2)


def main():
    hook_input = HookInput.from_stdin()
    if not hook_input.data:
        logger.info("Early exit: empty stdin")
        sys.exit(0)

    logger.debug(f"input = {json.dumps(hook_input.data, indent=2)}")

    transcript_path = hook_input.get("transcript_path", "")
    if not transcript_path or not os.path.exists(transcript_path):
        logger.debug("Early exit: no transcript (nested session)")
        sys.exit(0)

    last_text = get_last_assistant_message(transcript_path)
    if not last_text:
        last_text = hook_input.get("last_assistant_message", "")
    if not last_text:
        logger.info("Early exit: no last_text found")
        sys.exit(0)

    original_request = get_original_user_request(transcript_path)
    if not original_request:
        logger.info("Early exit: no original_request in transcript")
        sys.exit(0)

    handle_stop(last_text, original_request)


if __name__ == "__main__":
    main()
