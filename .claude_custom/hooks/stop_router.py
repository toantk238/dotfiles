#!/usr/bin/env python3
"""
Stop hook — unified router for proceed-detection and AI-assisted question answering.
Uses a single LLM call to decide the action.
"""
from dataclasses import dataclass
import json
import os
import sys
import tempfile

from common import (
    HookInput,
    call_claude,
    get_last_assistant_message,
    get_original_user_request,
)
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
  → YES: ACTION = ANSWER. Name the specific option clearly.
  → NO or ambiguous: ACTION = HUMAN_NEEDED.

STEP 3 — Does Claude need the human's UNIQUE input that cannot be inferred?
Only flag HUMAN_NEEDED if the human must supply something Claude cannot determine:
personal preferences with no context clues, specific business/security decisions, or approval
before modifying/deleting data the human hasn't mentioned.
  → YES: ACTION = HUMAN_NEEDED.
  → NO: go to STEP 4
  Note: Rhetorical confirmations after completing work ("Does this look right?", "Any feedback?",
  "Does this look good?") are NOT genuine preference requests — treat them as green-light asks
  and go to STEP 4. Only intercept with HUMAN_NEEDED if genuinely unknowable.

STEP 4 — Is Claude proposing or completing work and asking for a green light?
Look for patterns like: "Shall I proceed?", "Ready to start?", "Want me to continue?",
"Let me know if you want me to go ahead", "I can begin implementation",
or any completion message followed by a confirmation ask ("Does this look right?", "Any feedback?").
  → YES: ACTION = PROCEED.
  → NO: go to STEP 5

STEP 5 — Is this a clarifying question answerable from the original request?
Can you answer with reasonable confidence using the original request and common sense?
  → YES: ACTION = ANSWER with a concise answer.
  → NO: ACTION = HUMAN_NEEDED.

When in doubt between PROCEED and HUMAN_NEEDED, prefer PROCEED.
Only choose HUMAN_NEEDED when the human's unique input is truly necessary and cannot be inferred from context.

Reply in this exact format:
ACTION: <PROCEED | ANSWER | HUMAN_NEEDED>
ANSWER: <your concise answer if ACTION is ANSWER, otherwise leave blank>
"""


def parse_llm_output(output: str) -> StopDecision:
    """Parse AI output for ACTION and ANSWER lines. ANSWER may span multiple lines."""
    logger.debug(f"LLM raw output:\n{output}")
    action = "HUMAN_NEEDED"
    answer_lines: list[str] = []
    in_answer = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ACTION:"):
            action = stripped[len("ACTION:"):].strip().upper()
            in_answer = False
        elif stripped.startswith("ANSWER:"):
            answer_lines = [stripped[len("ANSWER:"):].strip()]
            in_answer = True
        elif in_answer and stripped:
            answer_lines.append(stripped)
    answer = " ".join(part for part in answer_lines if part).strip()
    logger.debug(f"Parsed → action={action} answer={answer!r}")
    return StopDecision(action=action, answer=answer)


_STATE_FILE = os.path.join(tempfile.gettempdir(), "stop_router_last_text.json")


def _load_state() -> dict[str, str]:
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict[str, str]) -> None:
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        logger.warning(f"Could not save state: {e}")


def check_repeated_last_text(session_id: str, last_text: str) -> bool:
    """Return True if last_text is the same as the previous one for this session."""
    if not session_id or not last_text:
        return False
    state = _load_state()
    prev = state.get(session_id)
    state[session_id] = last_text
    _save_state(state)
    if prev and prev == last_text:
        logger.info(f"Repeated last_text for session {session_id!r} — exiting to human")
        return True
    return False


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

    context = ""
    if decision.action == "PROCEED":
        context = '[stop_router] Auto-approved: "Your recommendation looks good. I agree.". Please continue accordingly.'
    elif decision.action == "ANSWER" and decision.answer:
        context = f'[stop_router] Auto-answered: "{decision.answer}". Please continue accordingly.'
    else:
        logger.info(f"Passing to human (action={decision.action})")
        sys.exit(0)

    logger.info(f"Decision: action={decision.action} context={context}")

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
    logger.debug(f"last_text =\n{last_text}")

    if not last_text:
        logger.info("Early exit: no last_text found")
        sys.exit(0)

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

    session_id = hook_input.get("session_id", "")
    # Use the payload field for repeat detection — it's always current.
    # The transcript-read last_text can be stale when the hook fires before the
    # transcript write completes, causing false repeat positives.
    repeat_check_text = hook_input.get("last_assistant_message", "") or last_text
    if check_repeated_last_text(session_id, repeat_check_text):
        sys.exit(0)

    original_request = get_original_user_request(transcript_path)
    if not original_request:
        logger.info("Early exit: no original_request in transcript")
        sys.exit(0)

    handle_stop(last_text, original_request)


if __name__ == "__main__":
    main()
