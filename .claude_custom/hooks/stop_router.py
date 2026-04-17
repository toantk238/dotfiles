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


_PLAN_SELECTION_TERMS = [
    "Plan complete and saved",
    "Subagent-Driven",
    "Inline Execution",
    "Which approach?",
]


def check_static_rules(last_text: str) -> str | None:
    """Return an inject-context string if a known deterministic pattern matches, else None."""
    if all(term in last_text for term in _PLAN_SELECTION_TERMS):
        return '[stop_router] Auto-answered: "Option 1: Subagent-Driven". Please continue accordingly.'
    return None


STOP_PROMPT_TEMPLATE = """You are an autonomous decision agent for a developer's coding assistant.
Claude (the assistant) has stopped and is waiting for input.

Original user request:
{original_request}

Claude's last message:
{last_text}

Follow these steps in order to decide the best action:

STEP 1 — Detect options:
Does Claude's message contain a numbered or lettered list of 2 or more distinct options for the human to choose from?
  → YES: go to STEP 2
  → NO: go to STEP 3

STEP 2 — Can you pick confidently from the original request alone?
Is one option clearly the best fit given ONLY the original user request, with high confidence?
  → YES: ACTION = ANSWER. Name the specific option clearly (e.g., "Option 2" or "Subagent-Driven").
  → NO or ambiguous: ACTION = HUMAN_NEEDED.

STEP 3 — Is Claude asking the human a preference or approval question?
Look for patterns like: "Does this look right?", "Which do you prefer?", "Shall I proceed with X or Y?",
"Please review", "Let me know if you want changes", "Does this sound right?", "Any feedback?",
"Does [X] look good?", "Is this what you had in mind?"
  → YES: ACTION = HUMAN_NEEDED. (Human review is explicitly requested — never auto-answer these.)
  → NO: go to STEP 4
  Note: "Shall I proceed?" with no alternatives is a green-light ask — it goes to STEP 4, not here.

STEP 4 — Is Claude proposing a plan and asking for a green light to continue?
Look for patterns like: "Shall I proceed?", "Ready to start?", "Want me to continue?",
"Let me know if you want me to go ahead", "I can begin implementation"
  → YES: ACTION = PROCEED.
  → NO: go to STEP 5

STEP 5 — Is this a clarifying question answerable from the original request?
Can you answer with 100% confidence using ONLY the original request, with no guessing?
  → YES: ACTION = ANSWER with a concise answer.
  → NO: ACTION = HUMAN_NEEDED.

When in doubt, always choose HUMAN_NEEDED. A wrong auto-answer that causes a loop is worse than an unnecessary interruption.

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
    static_context = check_static_rules(last_text)
    if static_context:
        logger.info("Static rule matched: subagent-driven plan selection")
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": static_context,
            }
        }))
        sys.exit(2)

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
    # Check existence here (not just inside read_transcript) so we can exit early
    # with a specific "nested session" log before making two file-open attempts.
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
